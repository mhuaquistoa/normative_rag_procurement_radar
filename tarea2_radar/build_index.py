"""OFFLINE process of Task 2: bulk files -> one row per process -> validation -> vector index.
The dashboard only reads data/processed, data/outputs and data/index.
    python build_index.py              # process + index (+ dashboard outputs)
    python build_index.py --download   # also (re)check the monthly files first
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
import acquire  # noqa: E402
import metrics  # noqa: E402
import process  # noqa: E402
from radar_index import build  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--download", action="store_true")
    a = ap.parse_args()
    if a.download:
        for m in acquire.cfg()["oece"]["months"]:
            acquire.bulk_month(m)
    process.main()
    t0 = time.perf_counter()
    r = build()
    r["segundos"] = round(time.perf_counter() - t0, 1)
    print(json.dumps(r, ensure_ascii=False))
    metrics.main()


if __name__ == "__main__":
    main()
