"""Source check (Phase 1, before anything else): can each PDF be used as it is?

Per file: pages, characters per page, pages without extractable text, and a reading-order test.
Reading order: the article headings ("Artículo 66.") found page by page must appear in ascending
order; a two-column page read in the wrong order breaks that sequence.
Usage: python src/source_check.py  ->  reports/source_check.md + reports/source_check.csv
"""
import re
import sys
from pathlib import Path

import pandas as pd
from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import cfg, path, sources  # noqa: E402

ARTICLE = re.compile(r"(?m)^\W{0,3}Art[ií]culo\s+(\d{1,3})\s*\.")


def check(source: dict) -> dict:
    reader = PdfReader(path("raw") / source["file"])
    texts = [p.extract_text() or "" for p in reader.pages]
    chars = pd.Series([len(t) for t in texts])
    min_chars = cfg()["source_check"]["min_chars_per_page"]
    articles = [int(n) for t in texts for n in ARTICLE.findall(t)]
    steps = list(zip(articles, articles[1:]))
    in_order = sum(b >= a for a, b in steps) / len(steps) if steps else None
    empty = int((chars < min_chars).sum())
    usable = empty == 0 and (in_order is None or in_order >= cfg()["source_check"]["min_reading_order"])
    return {"documento": source["id"], "paginas": len(texts), "caracteres": int(chars.sum()),
            "caracteres_por_pagina_mediana": int(chars.median()), "caracteres_por_pagina_min": int(chars.min()),
            "caracteres_por_pagina_max": int(chars.max()), "paginas_sin_texto": empty,
            "titulos_de_articulo": len(articles), "orden_de_lectura": round(in_order, 3) if in_order is not None else None,
            "utilizable_tal_cual": "sí" if usable else "no"}


def main() -> None:
    df = pd.DataFrame([check(s) for s in sources()])
    out = path("reports")
    df.to_csv(out / "source_check.csv", index=False)
    (out / "source_check.md").write_text(df.to_markdown(index=False), encoding="utf-8")
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
