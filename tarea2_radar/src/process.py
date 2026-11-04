"""Phases 1-2: one row per contracting process, validation rules and territorial normalization.

OCDS model. A *release* is one publication about a process at one moment (planning, tender, award,
contract...). A *record* gathers every release of one process plus a `compiledRelease`: the current
state merged from them. The `ocid` identifies the contracting process across all its releases.
One row per process = one row per ocid, taken from the compiledRelease; if an ocid appears in more
than one monthly file, the most recent compiledRelease wins.

Validation rules (each counted in reports/data_quality.*):
  V1 duplicates      rows per release vs per ocid; the same ocid in several files -> keep the latest
  V2 amount          tender value missing or 0 -> recovered from award values, else from item totals;
                     unrecoverable -> kept with amount = NaN and flag (excluded from amount totals);
                     non-PEN amounts converted with the publisher's amount_PEN
  V3 description     empty description -> title / item descriptions / budget project; else flagged
  V4 territory       `region` holds provinces, not departments: flagged; the department comes from
                     `department`; if that is missing or not one of the 25, it is recovered from the
                     province through a province->department table built from the data itself
  V5 text encoding   accents and mojibake (JUNÍN vs JUNIN, "Ã") folded to one canonical form for
                     matching; variants counted
    python src/process.py  ->  data/processed/procesos.parquet + reports/data_quality.json|md
"""
import collections
import json
import re
import sys
import unicodedata
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from radar_config import cfg, path  # noqa: E402

DEPARTMENTS = {  # canonical key (no accents, upper) -> display name
    "AMAZONAS": "Amazonas", "ANCASH": "Áncash", "APURIMAC": "Apurímac", "AREQUIPA": "Arequipa",
    "AYACUCHO": "Ayacucho", "CAJAMARCA": "Cajamarca", "CALLAO": "Callao", "CUSCO": "Cusco",
    "HUANCAVELICA": "Huancavelica", "HUANUCO": "Huánuco", "ICA": "Ica", "JUNIN": "Junín",
    "LA LIBERTAD": "La Libertad", "LAMBAYEQUE": "Lambayeque", "LIMA": "Lima", "LORETO": "Loreto",
    "MADRE DE DIOS": "Madre de Dios", "MOQUEGUA": "Moquegua", "PASCO": "Pasco", "PIURA": "Piura",
    "PUNO": "Puno", "SAN MARTIN": "San Martín", "TACNA": "Tacna", "TUMBES": "Tumbes", "UCAYALI": "Ucayali"}
CATEGORY = {"goods": "Bienes", "services": "Servicios", "works": "Obras"}
MOJIBAKE = re.compile(r"Ã|Â|�")


def fold(text) -> str:
    """V5: one canonical form for matching: strip accents, upper case, single spaces."""
    if text is None or (isinstance(text, float) and np.isnan(text)):
        return ""
    t = unicodedata.normalize("NFKD", str(text))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip().upper()


def load_records() -> list:
    out = []
    for f in sorted(path("raw").glob("*_json.zip")):
        with zipfile.ZipFile(f) as z:
            data = json.loads(z.read(z.infolist()[0]))
        out += [(f.name[:7], r) for r in data["records"]]
    return out


def _buyer(cr):
    bid = (cr.get("buyer") or {}).get("id")
    return next((p for p in cr.get("parties", []) if p.get("id") == bid), {}) or {}


def _amount(v):
    if not v:
        return None, None
    a = v.get("amount_PEN", v.get("amount") if v.get("currency", "PEN") == "PEN" else None)
    return a, v.get("currency")


def flatten(month: str, record: dict) -> dict:
    cr = record["compiledRelease"]
    t = cr.get("tender") or {}
    b = _buyer(cr)
    a = b.get("address") or {}
    awards = cr.get("awards") or []
    amount, currency = _amount(t.get("value"))
    award_total = sum((_amount(x.get("value"))[0] or 0) for x in awards)
    item_total = sum(((i.get("totalValue") or {}).get("amount") or 0) for i in t.get("items", []))
    ruc = next((x["id"] for x in b.get("additionalIdentifiers", []) if x.get("scheme") == "PE-RUC"), None)
    return {
        "ocid": record["ocid"], "tender_id": t.get("id"), "archivo_mes": month, "n_releases": len(record.get("releases", [])),
        "fecha_compilado": cr.get("date"), "fecha_publicacion": t.get("datePublished"),
        "titulo": t.get("title"), "descripcion_raw": t.get("description"),
        "items_texto": " | ".join(dict.fromkeys(i.get("description", "") for i in t.get("items", [])))[:1000],
        "proyecto": ((cr.get("planning") or {}).get("budget") or {}).get("project"),
        "comprador_id": b.get("id"), "comprador": b.get("name"), "comprador_ruc": ruc,
        "dep_raw": a.get("department"), "region_raw": a.get("region"), "localidad_raw": a.get("locality"),
        "categoria_raw": t.get("mainProcurementCategory"), "metodo": t.get("procurementMethodDetails"),
        "monto_convocado_raw": amount, "moneda": currency, "monto_adjudicado": award_total or None,
        "monto_items": item_total or None, "n_postores": t.get("numberOfTenderers"),
        "n_adjudicaciones": len(awards), "adjudicado": len(awards) > 0}


def build() -> tuple:
    q = collections.OrderedDict()
    records = load_records()
    df = pd.DataFrame([flatten(m, r) for m, r in records])

    # V1 duplicates: release-level rows vs process-level rows, and the same ocid across monthly files
    n_releases = int(df["n_releases"].sum())
    before = len(df)
    df = df.sort_values("fecha_compilado").drop_duplicates("ocid", keep="last")
    q["V1_duplicados"] = {"filas_si_se_usan_releases": n_releases, "records_en_archivos": before,
                          "procesos_unicos_ocid": len(df), "ocid_repetidos_entre_meses_descartados": before - len(df),
                          "accion": "una fila por ocid desde el compiledRelease; si se repite entre meses, gana el más reciente"}

    # V2 amount
    missing = df["monto_convocado_raw"].isna() | (df["monto_convocado_raw"] <= 0)
    df["monto"] = df["monto_convocado_raw"].where(~missing)
    df["monto_fuente"] = np.where(~missing, "convocado", None)
    rec_award = missing & df["monto_adjudicado"].fillna(0).gt(0)
    df.loc[rec_award, ["monto", "monto_fuente"]] = df.loc[rec_award, "monto_adjudicado"].to_frame().assign(f="adjudicado").values
    rec_items = missing & ~rec_award & df["monto_items"].fillna(0).gt(0)
    df.loc[rec_items, ["monto", "monto_fuente"]] = df.loc[rec_items, "monto_items"].to_frame().assign(f="items").values
    df["monto"] = pd.to_numeric(df["monto"])
    df["flag_monto"] = df["monto"].isna()
    q["V2_monto"] = {"faltante_o_cero": int(missing.sum()), "recuperado_de_adjudicacion": int(rec_award.sum()),
                     "recuperado_de_items": int(rec_items.sum()), "sin_monto_conservado_con_advertencia": int(df.flag_monto.sum()),
                     "tasa_recuperacion": round(float((rec_award | rec_items).sum() / max(missing.sum(), 1)), 4),
                     "en_otra_moneda_convertidos_a_PEN": int((df["moneda"].fillna("PEN") != "PEN").sum()),
                     "accion": "recuperar de adjudicación o ítems; si no, NaN con advertencia (fuera de las sumas)"}

    # V3 description
    empty = df["descripcion_raw"].fillna("").str.strip().eq("")
    df["descripcion"] = df["descripcion_raw"].where(~empty, df["items_texto"].where(df["items_texto"].str.strip().ne(""), df["proyecto"]))
    df["descripcion"] = df["descripcion"].fillna(df["titulo"])
    df["flag_descripcion"] = df["descripcion"].fillna("").str.strip().eq("")
    q["V3_descripcion"] = {"sin_descripcion": int(empty.sum()), "recuperadas": int((empty & ~df.flag_descripcion).sum()),
                           "sin_texto_conservadas_con_advertencia": int(df.flag_descripcion.sum()),
                           "accion": "usar ítems, proyecto o título; si nada, advertencia (no se indexa)"}

    # V4 territory
    df["dep_key"] = df["dep_raw"].map(fold)
    df["region_key"] = df["region_raw"].map(fold)
    region_not_dep = ~df["region_key"].isin(DEPARTMENTS)
    valid_dep = df["dep_key"].isin(DEPARTMENTS)
    prov_map = (df[valid_dep].groupby("region_key")["dep_key"].agg(lambda s: s.value_counts().index[0]).to_dict())
    inconsistent = df[valid_dep & df["region_key"].isin(prov_map)]
    n_inconsistent = int((inconsistent["region_key"].map(prov_map) != inconsistent["dep_key"]).sum())
    recover = ~valid_dep & df["region_key"].isin(prov_map)
    df["departamento_key"] = df["dep_key"].where(valid_dep)
    df.loc[recover, "departamento_key"] = df.loc[recover, "region_key"].map(prov_map)
    df.loc[~valid_dep & df["region_key"].isin(DEPARTMENTS), "departamento_key"] = df["region_key"]
    df["departamento"] = df["departamento_key"].map(DEPARTMENTS)
    df["flag_sin_departamento"] = df["departamento"].isna()
    q["V4_territorio"] = {"campo_region_con_provincia_no_departamento": int(region_not_dep.sum()),
                          "valores_distintos_en_region": int(df["region_key"].nunique()),
                          "departamento_vacio_o_invalido": int((~valid_dep).sum()),
                          "recuperados_por_provincia": int(recover.sum()),
                          "provincia_y_departamento_inconsistentes": n_inconsistent,
                          "sin_ubicar": int(df.flag_sin_departamento.sum()),
                          "accion": "departamento desde `department` (25 + Callao); `region` es provincia; recuperar por tabla provincia->departamento construida con los propios datos"}

    # V5 encoding / accents
    variants = {}
    for col in ("comprador", "dep_raw", "region_raw", "localidad_raw"):
        g = df[[col]].dropna().assign(k=lambda d: d[col].map(fold)).groupby("k")[col].nunique()
        variants[col] = int((g > 1).sum())
    moj = int(df["descripcion"].fillna("").str.contains(MOJIBAKE).sum() + df["comprador"].fillna("").str.contains(MOJIBAKE).sum())
    df["comprador_key"] = df["comprador"].map(fold)
    q["V5_codificacion"] = {"nombres_con_variantes_de_tilde_o_espacios": variants, "textos_con_mojibake": moj,
                            "accion": "forma canónica sin tildes y en mayúsculas para agrupar; se muestra el nombre con tildes"}

    df["categoria"] = df["categoria_raw"].map(CATEGORY).fillna("Otra")
    df["fecha"] = pd.to_datetime(df["fecha_publicacion"], errors="coerce", utc=True).dt.tz_convert("America/Lima").dt.tz_localize(None)
    df["mes"] = df["fecha"].dt.to_period("M").astype(str)
    df["un_solo_postor"] = df["adjudicado"] & df["n_postores"].eq(1)
    keep = ["ocid", "tender_id", "archivo_mes", "fecha", "mes", "titulo", "descripcion", "comprador", "comprador_key",
            "comprador_ruc", "departamento", "departamento_key", "region_raw", "localidad_raw", "categoria", "metodo",
            "monto", "monto_fuente", "moneda", "monto_adjudicado", "n_postores", "n_adjudicaciones", "adjudicado",
            "un_solo_postor", "n_releases", "flag_monto", "flag_descripcion", "flag_sin_departamento"]
    return df[keep].reset_index(drop=True), q


def main() -> None:
    df, q = build()
    df.to_parquet(path("processed") / "procesos.parquet", index=False)
    (path("reports") / "data_quality.json").write_text(json.dumps(q, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Data quality report (Task 2)", "", f"Processes: {len(df):,}", ""]
    for rule, v in q.items():
        lines += [f"## {rule}", ""] + [f"- **{k}**: {val}" for k, val in v.items()] + [""]
    (path("reports") / "data_quality.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(q, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
