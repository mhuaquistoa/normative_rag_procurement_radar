"""Phase 1 - extraction quality report per document, with a before/after cleaning example.
Usage: python src/quality.py  ->  reports/extraction_quality.md + reports/extraction_quality.json
"""
import json
import sys
from pathlib import Path

from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import path, sources  # noqa: E402
from extract import extract  # noqa: E402


def block(text: str, n: int) -> str:
    return "```text\n" + text[:n].rstrip() + "\n```"


def main() -> None:
    lines, summary = ["# Extraction quality report", ""], {}
    for s in sources():
        recs = extract(s)
        kept = [r for r in recs if not r["descartada"]]
        middle = kept[len(kept) // 2]
        summary[s["id"]] = {
            "paginas": len(recs), "paginas_conservadas": len(kept),
            "paginas_descartadas": [{"pagina": r["pagina"], "motivo": r["motivo"]} for r in recs if r["descartada"]],
            "caracteres_raw": sum(r["chars_raw"] for r in recs), "caracteres_limpios": sum(r["chars_clean"] for r in recs),
            "R1_encabezados_quitados": sum(r["R1_header_chars"] > 0 for r in recs),
            "R1_caracteres": sum(r["R1_header_chars"] for r in recs),
            "R2_caracteres_de_otra_norma": sum(r["R2_other_norm_chars"] for r in recs)}
        x = summary[s["id"]]
        lines += [f"## {s['titulo']}", "",
                  f"- Version: {s['version']} · file `{s['file']}`",
                  f"- Pages: {x['paginas']} · kept: {x['paginas_conservadas']} · discarded: "
                  f"{len(x['paginas_descartadas'])} {x['paginas_descartadas'] or ''}",
                  f"- Characters: {x['caracteres_raw']:,} raw → {x['caracteres_limpios']:,} clean",
                  f"- R1 gazette headers removed: {x['R1_encabezados_quitados']} pages ({x['R1_caracteres']:,} chars)",
                  f"- R2 text of another norm dropped: {x['R2_caracteres_de_otra_norma']:,} chars", "",
                  f"Sample from the middle of the document (page {middle['pagina']}):", "", block(middle["texto"], 700), ""]
    # before/after on the page where all rules act: first page of the decree, last page for R2
    ds = next(s for s in sources() if s.get("fin_norma"))
    reader = PdfReader(path("raw") / ds["file"])
    recs = extract(ds)
    lines += ["## Before and after cleaning (DS 001-2026-EF)", "",
              "Page 1, raw (header glued to the body, one PDF line per column line):", "",
              block(reader.pages[0].extract_text(), 420), "", "Page 1, clean (R1 header removed and kept as "
              f"`pagina_diario = {recs[0]['pagina_diario']}`, R3 lines joined into paragraphs):", "",
              block(recs[0]["texto"], 420), "",
              f"Page {recs[-1]['pagina']}, raw end (another norm starts after the code `{ds['fin_norma']}`):", "",
              "```text\n" + reader.pages[-1].extract_text()[200:620] + "\n```", "",
              f"Page {recs[-1]['pagina']}, clean (R2 cut at the code):", "", "```text\n" + recs[-1]["texto"][-260:] + "\n```", ""]
    out = path("reports")
    (out / "extraction_quality.md").write_text("\n".join(lines), encoding="utf-8")
    (out / "extraction_quality.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
