"""Phase 1 - extraction and cleaning, page by page.

The page number is attached at the very first step: each PDF page becomes one record and is cleaned
on its own, so no later step can lose track of where a sentence came from. (Joining the whole document
into one string and splitting it later forces you to recover page boundaries from character offsets,
and a fragment that straddles two pages silently gets only one of them.)

Cleaning rules (each one counted in the quality report):
  R1 gazette header  El Peruano prints "33NORMAS LEGALESJueves 8 de enero de 2026 El Peruano /"
                     (glued on odd pages, spaced on even ones) at the top of every page. Removed; its
                     page number is kept as `pagina_diario`.
  R2 end of norm     El Peruano closes every norm with its publication code ("2474920-3"); whatever
                     follows on that page belongs to the next, unrelated norm and is dropped. Pages
                     wholly after the code are discarded.
  R3 line breaks     PDF lines are joined into paragraphs, except before a structural marker
                     (Artículo, numeral "66.1.", literal "a)", roman "ii)", CAPÍTULO/TÍTULO, "(*)" note);
                     a line ending in "-" is joined without a space ("009-2025-" + "EF"), and a word
                     split as "contra-" + "taciones" loses the hyphen.
  R4 whitespace      blank lines made of spaces collapse to one paragraph break; runs of spaces to one.
Usage: python src/extract.py  ->  data/processed/<doc>.jsonl  (one JSON record per page)
"""
import json
import re
import sys
from pathlib import Path

from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import cfg, path, sources  # noqa: E402

HEADER = re.compile(r"^\s*(\d{1,4})\s*NORMAS LEGALES\s*\w+\s+\d{1,2}\s+de\s+\w+\s+de\s+\d{4}\s+El Peruano\s*/\s*")
MARKER = re.compile(r"^(?:[\"“]?Art[ií]culo\s+\d|\d+\.\d+(?:\.\d+)*\.?\s|[a-z]\)\s|[ivxlc]+\)\s|"
                    r"(?:CAP[IÍ]TULO|T[IÍ]TULO|SUBCAP[IÍ]TULO|DISPOSICI|ANEXO)\b|\(\*\)|\(…\)|\(\.\.\.\)|[A-ZÁÉÍÓÚÑ ]{8,}$)")
ENDS_SENTENCE = re.compile(r"[.:;”\"]$|\(\*\)$")


def join_lines(text: str) -> str:
    """R3 + R4: rebuild paragraphs from PDF lines."""
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    out = []
    for ln in lines:
        if not ln:
            if out and out[-1] != "":
                out.append("")
            continue
        if out and out[-1] and not MARKER.match(ln) and not ENDS_SENTENCE.search(out[-1]):
            prev = out[-1]
            if prev.endswith("-"):
                hyphenated_word = re.search(r"[a-záéíóúñ]-$", prev) and ln[:1].islower()
                out[-1] = (prev[:-1] if hyphenated_word else prev) + ln
            else:
                out[-1] = prev + " " + ln
        else:
            out.append(ln)
    return "\n".join(out).strip()


def clean_page(raw: str, source: dict, state: dict):
    """Returns (clean text, gazette page or None, discard reason or None, rule counts)."""
    counts = {"R1_header_chars": 0, "R2_other_norm_chars": 0}
    if state.get("ended"):
        counts["R2_other_norm_chars"] = len(raw)
        return "", None, "después del fin de la norma (otra norma del diario)", counts
    text, gazette = raw, None
    m = HEADER.match(text)
    if m:
        gazette = int(m.group(1))
        counts["R1_header_chars"] = m.end()
        text = text[m.end():]
    end_code = source.get("fin_norma")
    if end_code:
        m = re.search(rf"(?m)^\s*{re.escape(end_code)}\s*$", text)
        if m:
            counts["R2_other_norm_chars"] = len(text) - m.start()
            text = text[:m.start()]
            state["ended"] = True
    return join_lines(text), gazette, None, counts


def extract(source: dict) -> list:
    reader = PdfReader(path("raw") / source["file"])
    state, records = {}, []
    for i, page in enumerate(reader.pages, start=1):
        raw = page.extract_text() or ""
        text, gazette, reason, counts = clean_page(raw, source, state)
        if not reason and len(text) < cfg()["source_check"]["min_chars_per_page"]:
            reason = "sin texto suficiente tras la limpieza"
        records.append({"documento": source["id"], "titulo": source["titulo"], "tipo": source["tipo"],
                         "version": source["version"], "fecha_version": source["fecha_version"],
                         "pagina": i, "pagina_diario": gazette, "texto": "" if reason else text,
                         "chars_raw": len(raw), "chars_clean": 0 if reason else len(text),
                         "descartada": bool(reason), "motivo": reason, **counts, "raw": raw})
    return records


def main() -> None:
    out = path("processed")
    for s in sources():
        records = extract(s)
        with open(out / f"{s['id']}.jsonl", "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps({k: v for k, v in r.items() if k != "raw"}, ensure_ascii=False) + "\n")
        kept = [r for r in records if not r["descartada"]]
        print(f"{s['id']}: {len(kept)}/{len(records)} pages kept, "
              f"{sum(r['chars_raw'] for r in records):,} -> {sum(r['chars_clean'] for r in records):,} chars")


if __name__ == "__main__":
    main()
