"""Phase 2 - persistent vector index (ChromaDB) and retrieval.

ChromaDB: persistent on disk, stores each vector with its metadata (document, version, page, article)
and filters on that metadata at query time; no server to run, which suits a local Streamlit app.

Build guarantees
  idempotent   fragments are upserted by their stable ID; an ID already stored with the same text
               hash is skipped, so a second run embeds nothing and duplicates nothing.
  resumable    vectors are written batch by batch; after an interruption the next run only embeds
               what is missing.
  isolated     stale fragments are deleted per document (IDs of that document no longer produced),
               so adding or re-chunking one document never touches another.
"""
import time

import chromadb

from chunking import chunk_all
from config import cfg, path
from embeddings import get_embedder

META_KEYS = ["documento", "titulo", "tipo", "version", "fecha_version", "pagina", "pagina_diario",
             "articulo", "articulos_en_fragmento", "ambito", "chars", "hash"]
_CLIENT = None


def client():
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = chromadb.PersistentClient(path=str(path("index")))
    return _CLIENT


def collection_name(embedder_key: str, chunking: str) -> str:
    return f"{cfg()['index']['collection_prefix']}_{embedder_key}_{chunking}"


def get_collection(embedder_key: str = None, chunking: str = None):
    embedder_key = embedder_key or cfg()["embeddings"]["active"]
    chunking = chunking or cfg()["chunking"]["active"]
    return client().get_or_create_collection(collection_name(embedder_key, chunking),
                                             metadata={"hnsw:space": cfg()["index"]["distance"]})


def build(embedder_key: str, chunking: str, batch: int = 64) -> dict:
    c = cfg()["chunking"]["configs"][chunking]
    chunks = chunk_all(c["size"], c["overlap"], c.get("header", False))
    col = get_collection(embedder_key, chunking)
    stored = col.get(ids=[x["id"] for x in chunks], include=["metadatas"])
    have = {i: m["hash"] for i, m in zip(stored["ids"], stored["metadatas"])}
    todo = [x for x in chunks if have.get(x["id"]) != x["hash"]]
    emb = get_embedder(embedder_key) if todo else None
    t0 = time.perf_counter()
    for i in range(0, len(todo), batch):
        part = todo[i:i + batch]
        col.upsert(ids=[x["id"] for x in part], documents=[x["texto"] for x in part],
                   embeddings=emb.embed_documents([x["embed_text"] for x in part]),
                   metadatas=[{k: x[k] for k in META_KEYS} for x in part])
    seconds = time.perf_counter() - t0
    stale = []
    for doc in {x["documento"] for x in chunks}:
        current = {x["id"] for x in chunks if x["documento"] == doc}
        ids = col.get(where={"documento": doc}, include=[])["ids"]
        stale += [i for i in ids if i not in current]
    if stale:
        col.delete(ids=stale)
    return {"collection": col.name, "fragments": len(chunks), "embedded_now": len(todo),
            "skipped_unchanged": len(chunks) - len(todo), "stale_deleted": len(stale),
            "embed_seconds": round(seconds, 2), "count_in_collection": col.count()}


def search(question: str, k: int, embedder_key: str = None, chunking: str = None, where: dict = None,
           query_vector: list = None) -> list:
    """Top-k fragments with cosine similarity (1 - cosine distance). Never re-reads the PDFs."""
    col = get_collection(embedder_key, chunking)
    qv = query_vector or get_embedder(embedder_key).embed_query(question)
    r = col.query(query_embeddings=[qv], n_results=k, where=where,
                  include=["documents", "metadatas", "distances"])
    return [{"id": i, "texto": d, "similitud": round(1 - dist, 4), **m}
            for i, d, m, dist in zip(r["ids"][0], r["documents"][0], r["metadatas"][0], r["distances"][0])]
