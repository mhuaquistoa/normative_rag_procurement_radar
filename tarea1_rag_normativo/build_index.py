"""OFFLINE process: PDFs -> pages -> fragments -> vectors -> persistent index. Run once, or when
documents change. The online engine only reads the index.

    python build_index.py                         # active embedder + active chunking from config.yaml
    python build_index.py --embedder api          # same fragments, Gemini embeddings (Phase 4)
    python build_index.py --chunking all          # every chunking config (Phase 2 comparison)
    python build_index.py --skip-extract          # reuse data/processed
"""
import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
import extract  # noqa: E402
from config import cfg, path  # noqa: E402
from index import build  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--embedder", default=cfg()["embeddings"]["active"], choices=["local", "api"])
    ap.add_argument("--chunking", default=cfg()["chunking"]["active"])
    ap.add_argument("--skip-extract", action="store_true")
    a = ap.parse_args()
    if not a.skip_extract:
        extract.main()
    configs = list(cfg()["chunking"]["configs"]) if a.chunking == "all" else [a.chunking]
    log = path("logs") / "index_builds.csv"
    for ch in configs:
        r = build(a.embedder, ch)
        r = {"timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "embedder": a.embedder,
             "model": cfg()["embeddings"][a.embedder]["model"], "chunking": ch, **r}
        print(json.dumps(r, ensure_ascii=False))
        new = not log.exists()
        with open(log, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(r))
            if new:
                w.writeheader()
            w.writerow(r)


if __name__ == "__main__":
    main()
