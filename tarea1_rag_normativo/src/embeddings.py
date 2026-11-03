"""One interface, two implementations: switching models is a config change (embeddings.active).

    emb = get_embedder()            # or get_embedder("api")
    emb.embed_documents(texts) -> list[list[float]]      (passages)
    emb.embed_query(text)      -> list[float]            (questions)

Some model families are trained with different inputs for queries and passages:
  - multilingual-e5 expects the prefixes "query: " and "passage: " (without them recall drops);
  - Gemini embeddings take a task type, RETRIEVAL_QUERY vs RETRIEVAL_DOCUMENT.
Both are applied here, so no caller has to remember them. Vectors are L2-normalized, so the
vector store's cosine similarity is comparable across models.
"""
import os
import time

import numpy as np

from config import cfg
from costs import log_call


class Embedder:
    name: str
    dim: int
    max_tokens: int

    def embed_documents(self, texts: list) -> list:
        raise NotImplementedError

    def embed_query(self, text: str) -> list:
        raise NotImplementedError


class LocalEmbedder(Embedder):
    def __init__(self, c: dict):
        from sentence_transformers import SentenceTransformer
        self.name, self.c = c["model"], c
        self.model = SentenceTransformer(c["model"], device=c.get("device") or None)
        self.dim = self.model.get_sentence_embedding_dimension()
        self.max_tokens = self.model.max_seq_length

    def _encode(self, texts):
        return self.model.encode(texts, batch_size=self.c.get("batch_size", 32), normalize_embeddings=True,
                                 show_progress_bar=False).tolist()

    def embed_documents(self, texts):
        return self._encode([self.c["passage_prefix"] + t for t in texts])

    def embed_query(self, text):
        return self._encode([self.c["query_prefix"] + text])[0]

    def count_tokens(self, text: str) -> int:
        return len(self.model.tokenizer(self.c["passage_prefix"] + text)["input_ids"])


class GeminiEmbedder(Embedder):
    def __init__(self, c: dict):
        from google import genai
        self.name, self.c = c["model"], c
        self.client = genai.Client(api_key=os.environ[c["api_key_env"]])
        self.dim, self.max_tokens = c["dimension"], c["max_tokens"]

    def _embed(self, texts, task):
        from google.genai import types
        out = []
        for i in range(0, len(texts), self.c["batch_size"]):
            batch = texts[i:i + self.c["batch_size"]]
            for attempt in range(self.c["retries"]):
                t0 = time.perf_counter()
                try:
                    r = self.client.models.embed_content(
                        model=self.name, contents=batch,
                        config=types.EmbedContentConfig(task_type=task, output_dimensionality=self.dim))
                    log_call("embedding", self.name, tokens_in=sum(len(t) for t in batch) // 4, tokens_out=0,
                             latency_s=time.perf_counter() - t0, ok=True, note=f"{task}, {len(batch)} texts (tokens estimated)")
                    out += [list(np.array(e.values) / np.linalg.norm(e.values)) for e in r.embeddings]
                    break
                except Exception as e:  # rate limit or transient error: back off, log, retry
                    log_call("embedding", self.name, 0, 0, time.perf_counter() - t0, ok=False, note=str(e)[:200])
                    if attempt == self.c["retries"] - 1:
                        raise
                    time.sleep(self.c["backoff_s"] * (attempt + 1))
            time.sleep(self.c.get("pause_s", 0))
        return out

    def embed_documents(self, texts):
        return self._embed(texts, "RETRIEVAL_DOCUMENT")

    def embed_query(self, text):
        return self._embed([text], "RETRIEVAL_QUERY")[0]


_CACHE = {}


def get_embedder(which: str = None) -> Embedder:
    which = which or cfg()["embeddings"]["active"]
    if which not in _CACHE:
        c = cfg()["embeddings"][which]
        _CACHE[which] = {"sentence_transformers": LocalEmbedder, "gemini": GeminiEmbedder}[c["kind"]](c)
    return _CACHE[which]
