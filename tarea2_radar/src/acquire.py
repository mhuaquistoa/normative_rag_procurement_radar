"""Phase 1 - data acquisition. Two access methods, each for what it is good at:

  bulk   monthly ZIP files (OCDS JSON) = the corpus. One request per month, complete and reproducible.
         Re-runnable: a file already on disk whose sha matches the published one is never fetched again.
  api    paginated /releases endpoint = recent updates only (what changed after the last monthly file).
         Throttled, retried with backoff, and cached one file per request: a failed request never loses
         the pages already saved, and a re-run resumes from the cache.

Every run appends to logs/acquisition.csv: step, item, requests, bytes, seconds, status.
    python src/acquire.py            # bulk months from config
    python src/acquire.py --api 3    # also fetch the 3 most recent pages of releases from the API
"""
import argparse
import csv
import hashlib
import json
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from radar_config import cfg, path  # noqa: E402

SESSION = requests.Session()


def log(step, item, n_requests, n_bytes, seconds, status) -> None:
    f = path("logs") / "acquisition.csv"
    new = not f.exists()
    with open(f, "a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(["timestamp_utc", "step", "item", "requests", "bytes", "seconds", "status"])
        w.writerow([datetime.now(timezone.utc).isoformat(timespec="seconds"), step, item, n_requests, n_bytes,
                    round(seconds, 2), status])


def get(url: str, **kw) -> requests.Response:
    c = cfg()["oece"]
    for attempt in range(c["retries"]):
        try:
            r = SESSION.get(url, headers={"User-Agent": c["user_agent"]}, timeout=c["timeout_s"], **kw)
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {r.status_code}")
            r.raise_for_status()
            return r
        except requests.RequestException:
            if attempt == c["retries"] - 1:
                raise
            time.sleep(c["backoff_s"] * (attempt + 1))


def inner_sha256(zip_path: Path) -> str:
    """The published .sha is the sha256 of the JSON inside the ZIP, not of the ZIP itself."""
    with zipfile.ZipFile(zip_path) as z:
        h = hashlib.sha256()
        with z.open(z.infolist()[0]) as f:
            for block in iter(lambda: f.read(1 << 20), b""):
                h.update(block)
    return h.hexdigest()


def bulk_month(month: str) -> Path:
    c = cfg()["oece"]
    y, m = month.split("-")
    base = f"{c['base_url']}/file/{c['source']}"
    target = path("raw") / f"{month}_{c['source']}_{c['format']}.zip"
    t0, n = time.perf_counter(), 0
    published_sha = get(f"{base}/sha/{y}/{m}/").text.strip().split()[0].lower(); n += 1
    if target.exists() and inner_sha256(target) == published_sha:
        log("bulk", month, n, 0, time.perf_counter() - t0, "skipped: already downloaded, sha ok")
        return target
    r = get(f"{base}/{c['format']}/{y}/{m}/"); n += 1
    target.write_bytes(r.content)
    digest = inner_sha256(target)
    status = "ok, sha matches" if digest == published_sha else f"sha MISMATCH (published {published_sha[:12]}, got {digest[:12]})"
    log("bulk", month, n, len(r.content), time.perf_counter() - t0, status)
    return target


def api_recent(pages: int) -> list:
    """Most recent releases, page by page, each page cached; resumes from the cache."""
    c = cfg()["oece"]
    cache = path("api_cache")
    saved = []
    for page in range(1, pages + 1):
        f = cache / f"releases_page{page:03d}_{datetime.now(timezone.utc):%Y%m%d}.json"
        if f.exists():
            saved.append(f)
            continue
        t0 = time.perf_counter()
        try:
            r = get(f"{c['base_url']}/releases", params={"page": page})
        except requests.RequestException as e:
            log("api", f"releases page {page}", 1, 0, time.perf_counter() - t0, f"failed: {e}")
            break  # pages already cached stay on disk; the next run resumes here
        f.write_bytes(r.content)
        saved.append(f)
        log("api", f"releases page {page}", 1, len(r.content), time.perf_counter() - t0, "ok")
        time.sleep(c["throttle_s"])
    return saved


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", type=int, default=0, help="also fetch N recent pages of releases from the API")
    a = ap.parse_args()
    for month in cfg()["oece"]["months"]:
        f = bulk_month(month)
        print(f"{month}: {f.name} {f.stat().st_size / 1e6:.1f} MB")
    if a.api:
        files = api_recent(a.api)
        print(f"api: {len(files)} pages cached")
    with open(path("logs") / "acquisition.csv", encoding="utf-8") as fh:
        print(fh.read().splitlines()[-1])


if __name__ == "__main__":
    main()
