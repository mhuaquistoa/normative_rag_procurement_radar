"""Download the official PDFs to data/raw/. Re-runnable: a file already on disk is never fetched again.

Writes data/raw/sources.json with, per file: URL, official page, download date, size and sha256.
Usage: python src/download.py
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import cfg, path, sources  # noqa: E402


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> None:
    raw = path("raw")
    manifest_file = raw / "sources.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8")) if manifest_file.exists() else {}
    d = cfg()["download"]
    for s in sources():
        target = raw / s["file"]
        if target.exists() and s["id"] in manifest:
            print(f"{s['id']}: already downloaded on {manifest[s['id']]['descargado']}, skipped")
            continue
        r = requests.get(s["url"], headers={"User-Agent": d["user_agent"]}, timeout=d["timeout_s"])
        r.raise_for_status()
        if not r.content.startswith(b"%PDF"):
            raise ValueError(f"{s['id']}: the URL did not return a PDF")
        target.write_bytes(r.content)
        manifest[s["id"]] = {"archivo": s["file"], "url": s["url"], "pagina_oficial": s["pagina_oficial"],
                             "descargado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                             "bytes": target.stat().st_size, "sha256": sha256(target)}
        print(f"{s['id']}: {target.stat().st_size / 1e6:.2f} MB")
    manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
