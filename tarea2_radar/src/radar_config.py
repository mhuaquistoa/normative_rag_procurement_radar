"""Load tarea2_radar/config.yaml (settings) and the repo .env (secrets).
Named radar_config so Task 2 can import the Task 1 modules (embeddings, llm, costs), whose own
settings module is called config."""
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
