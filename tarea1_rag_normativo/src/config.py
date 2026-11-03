"""Load config.yaml (settings) and .env (secrets). No path, model or threshold is written in code."""
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

TASK = Path(__file__).resolve().parents[1]
REPO = TASK.parent
load_dotenv(REPO / ".env")


@lru_cache(maxsize=1)
def cfg() -> dict:
    return yaml.safe_load((TASK / "config.yaml").read_text(encoding="utf-8"))


def path(key: str) -> Path:
    p = TASK / cfg()["paths"][key]
    p.mkdir(parents=True, exist_ok=True)
    return p


def sources() -> list:
    return cfg()["sources"]
