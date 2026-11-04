"""Reuse of the Task 1 engine pieces: the same local embeddings model (same class, same prefixes),
the same LLM client and the same cost log. Task 1's modules read Task 1's config; Task 2 only
passes its own prompts and texts.
"""
import sys
from pathlib import Path

T1_SRC = Path(__file__).resolve().parents[2] / "tarea1_rag_normativo" / "src"
if str(T1_SRC) not in sys.path:
    sys.path.append(str(T1_SRC))

from embeddings import get_embedder  # noqa: E402,F401  (Task 1)
from llm import chat_json  # noqa: E402,F401  (Task 1)
