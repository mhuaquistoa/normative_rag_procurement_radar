"""Split a question into STRUCTURED conditions (applied as exact filters) and a SEMANTIC remainder.

"obras de agua y saneamiento en Cusco por más de un millón de soles"
  -> filters  {departamento: CUSCO, categoria: Obras, monto >= 1,000,000}
  -> semantic "agua y saneamiento"
Rules, not an LLM: deterministic, free, testable, and they never invent a condition.
"""
import re

from process import DEPARTMENTS, fold

NUM_WORDS = {"un": 1, "uno": 1, "una": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
             "ocho": 8, "nueve": 9, "diez": 10, "veinte": 20, "cincuenta": 50, "cien": 100, "medio": 0.5}
SCALE = {"MIL": 1e3, "MILLON": 1e6, "MILLONES": 1e6, "M": 1e6}
NUMBER = r"(?:\d+(?:[.,]\d+)*|" + "|".join(k.upper() for k in NUM_WORDS) + r")"
AMOUNT = rf"(?:S/\.?\s*)?({NUMBER})\s*(MIL(?:LONES|LON)?|MILLONES|M\b)?(?:\s+DE)?(?:\s+SOLES)?"
LOWER = r"(?:MAS DE|MAYOR(?:ES)? (?:A|DE|QUE)|SUPERIOR(?:ES)? A|POR ENCIMA DE|SOBRE|DESDE|ARRIBA DE|AL MENOS)"
UPPER = r"(?:MENOS DE|MENOR(?:ES)? (?:A|DE|QUE)|INFERIOR(?:ES)? A|POR DEBAJO DE|HASTA|DEBAJO DE|MAXIMO)"
CATEGORIES = [(r"\bOBRAS?\b|\bCONSTRUCCION(?:ES)?\b", "Obras"), (r"\bSERVICIOS?\b|\bCONSULTORIAS?\b", "Servicios"),
              (r"\bBIENES\b|\bADQUISICION(?:ES)? DE BIENES\b", "Bienes")]
MONTHS = {"AGOSTO": "2026-08", "SEPTIEMBRE": "2026-09", "SETIEMBRE": "2026-09", "OCTUBRE": "2026-10"}


def _value(num: str, scale: str) -> float:
    n = num.upper()
    if n.lower() in NUM_WORDS:
        v = NUM_WORDS[n.lower()]
    else:
        n = n.replace(" ", "")
        if re.fullmatch(r"\d{1,3}([.,]\d{3})+", n):  # 1.000.000 or 1,000,000
            v = float(re.sub(r"[.,]", "", n))
        else:
            v = float(n.replace(",", "."))
    return v * SCALE.get((scale or "").upper().replace("Ó", "O"), 1)


def parse(question: str) -> dict:
    q = fold(question)
    spans, f = [], {}
    deps = [d for d in sorted(DEPARTMENTS, key=len, reverse=True) if re.search(rf"\b{d}\b", q)]
    deps = [d for d in deps if not any(d != o and d in o for o in deps)]  # "LIMA" inside nothing else
    if deps:
        f["departamentos"] = deps
        spans += [m.span() for d in deps for m in re.finditer(rf"\b(?:EN |DE |DEL )?{d}\b", q)]
    for pat, cat in CATEGORIES:
        m = re.search(pat, q)
        if m:
            f["categoria"] = cat
            break
    m = re.search(rf"ENTRE {AMOUNT} Y {AMOUNT}", q)
    if m:
        lo, hi = _value(m.group(1), m.group(2) or m.group(4)), _value(m.group(3), m.group(4))
        f["monto_min"], f["monto_max"] = min(lo, hi), max(lo, hi)
        spans.append(m.span())
    else:
        for key, pat in (("monto_min", LOWER), ("monto_max", UPPER)):
            m = re.search(rf"{pat}\s+{AMOUNT}", q)
            if m:
                f[key] = _value(m.group(1), m.group(2))
                spans.append(m.span())
    months = [v for k, v in MONTHS.items() if re.search(rf"\b{k}\b", q)]
    if months:
        f["meses"] = sorted(set(months))
        spans += [m.span() for k in MONTHS for m in re.finditer(rf"\b(?:EN |DE )?{k}(?: DE 2026| 2026)?\b", q)]
    sem = q
    for a, b in sorted(spans, reverse=True):
        sem = sem[:a] + " " + sem[b:]
    sem = re.sub(r"\b(?:QUE|CUALES|CUANTOS|HAY|PROCESOS|CONTRATACIONES|COMPRAS|LICITACIONES|SOLES|"
                 r"(?:ESTA )?COMPRANDO|EL ESTADO|DEL ESTADO)\b", " ", sem)
    sem = re.sub(r"[¿?¡!,.]", " ", sem).split()
    while sem and sem[-1] in {"POR", "DE", "Y", "EN", "EL", "LA", "CON", "A"}:  # connectors left dangling
        sem.pop()
    while sem and sem[0] in {"POR", "DE", "Y", "EN", "EL", "LA", "CON", "A"}:
        sem.pop(0)
    f["consulta_semantica"] = " ".join(sem).lower() or question
    return f


def to_where(f: dict) -> dict:
    """Chroma metadata filter from parsed (or sidebar) conditions."""
    c = []
    if f.get("departamentos"):
        c.append({"departamento": {"$in": f["departamentos"]}} if len(f["departamentos"]) > 1 else {"departamento": f["departamentos"][0]})
    if f.get("categoria"):
        c.append({"categoria": f["categoria"]})
    if f.get("monto_min") is not None:
        c.append({"monto": {"$gte": float(f["monto_min"])}})
    if f.get("monto_max") is not None:
        c.append({"monto": {"$lte": float(f["monto_max"])}})
        c.append({"monto": {"$gte": 0.0}})  # unknown amounts (-1) never pass an amount filter
    if f.get("meses"):
        c.append({"mes": {"$in": f["meses"]}} if len(f["meses"]) > 1 else {"mes": f["meses"][0]})
    if f.get("fecha_desde"):
        c.append({"fecha": {"$gte": int(f["fecha_desde"])}})
    if f.get("fecha_hasta"):
        c.append({"fecha": {"$lte": int(f["fecha_hasta"])}})
    return {} if not c else c[0] if len(c) == 1 else {"$and": c}
