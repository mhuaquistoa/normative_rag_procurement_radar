"""Phase 3 - vector index of process descriptions, with the structured fields as metadata.

The text that is embedded is the description (what is being bought). Department, amount, date,
category, buyer and ocid are stored as METADATA, not text: they are filtered exactly at query time
(`where`), because an embedding cannot tell 900,000 from 1,200,000 soles, or Cusco from Puno, with
any reliability - nearby numbers and nearby places look alike to it.
Same guarantees as Task 1: ID = ocid (stable), upsert, skip unchanged hashes, batch writes.
"""
import hashlib
import math

import chromadb
import pandas as pd

from radar_config import cfg, path
from shared import get_embedder

_CLIENT = None


def collection():
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = chromadb.PersistentClient(path=str(path("index")))
    return _CLIENT.get_or_create_collection(cfg()["index"]["collection"], metadata={"hnsw:space": "cosine"})


def embed_text(r) -> str:
    return f"{r['categoria']}: {r['descripcion']}"[: cfg()["index"]["max_chars"]]


def metadata(r) -> dict:
    fecha = r["fecha"]
    return {"ocid": r["ocid"], "departamento": r["departamento_key"] or "", "departamento_nombre": r["departamento"] or "",
            "monto": float(r["monto"]) if r["monto"] == r["monto"] else -1.0,  # NaN -> -1: excluded by amount filters
            "fecha": int(fecha.strftime("%Y%m%d")) if not pd.isna(fecha) else 0, "mes": r["mes"] or "",
            "categoria": r["categoria"], "comprador": r["comprador"] or "", "metodo": r["metodo"] or "",
            "adjudicado": bool(r["adjudicado"]), "n_postores": int(r["n_postores"]) if r["n_postores"] == r["n_postores"] else -1}


def build(batch: int = 256) -> dict:
    df = pd.read_parquet(path("processed") / "procesos.parquet")
    df = df[~df["flag_descripcion"]]
    texts = df.apply(embed_text, axis=1)
    hashes = texts.map(lambda t: hashlib.sha1(t.encode("utf-8")).hexdigest()[:12])
    col = collection()
    have = {}
    for i in range(0, len(df), 5000):
        got = col.get(ids=df["ocid"].iloc[i:i + 5000].tolist(), include=["metadatas"])
        have.update({k: m.get("hash") for k, m in zip(got["ids"], got["metadatas"])})
    todo = [i for i, (o, h) in enumerate(zip(df["ocid"], hashes)) if have.get(o) != h]
    emb = get_embedder(cfg()["index"]["embedder"])
    for s in range(0, len(todo), batch):
        idx = todo[s:s + batch]
        rows = df.iloc[idx]
        col.upsert(ids=rows["ocid"].tolist(), documents=rows["descripcion"].tolist(),
                   embeddings=emb.embed_documents(texts.iloc[idx].tolist()),
                   metadatas=[{**metadata(r), "hash": h} for (_, r), h in zip(rows.iterrows(), hashes.iloc[idx])])
    return {"procesos": len(df), "embebidos_ahora": len(todo), "en_coleccion": col.count()}


def search(query: str, k: int, where: dict = None) -> list:
    qv = get_embedder(cfg()["index"]["embedder"]).embed_query(query)
    r = collection().query(query_embeddings=[qv], n_results=k, where=where or None,
                           include=["documents", "metadatas", "distances"])
    return [{"descripcion": d, "similitud": round(1 - dist, 4), **m}
            for d, m, dist in zip(r["documents"][0], r["metadatas"][0], r["distances"][0])]


def count(where: dict = None) -> int:
    if not where:
        return collection().count()
    return len(collection().get(where=where, include=[])["ids"])
