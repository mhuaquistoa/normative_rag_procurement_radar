"""ONLINE process: the single RAG engine. Interfaces (Streamlit, CLI, evaluation) only call
`responder()`. This module imports no UI library and never reads the PDFs, only the index.

responder(pregunta) -> {
    pregunta, respuesta, abstuvo (bool), motivo_abstencion (None | umbral | fuera_de_corpus | reglamento | sin_citas),
    fuentes: [{ref, documento, titulo, version, pagina, pagina_diario, articulo, similitud, fragmento}],
    nota_version, mejor_similitud, umbral, llamo_llm (bool),
    tokens: {entrada, cache, salida}, costo_usd, franja_precio, modelo, latencia_s, error (None | str)
}

Decision flow
  1 retrieve top-k fragments (local embeddings, persistent index)
  2 GATE: best similarity < threshold -> abstain WITHOUT calling the LLM (cost 0)
  3 LLM answers only from the numbered fragments, in JSON, and may itself abstain:
      fuera_de_corpus (the fragments do not answer) or reglamento (it needs the Reglamento text)
  4 every claim must cite a fragment; an answer that cites none is turned into an abstention
  5 version note: built from metadata, not left to the model (see `version_note`)
"""
import time

from config import cfg
from index import search
from llm import chat_json

MOTIVOS_LLM = {"fuera_de_corpus", "reglamento"}


def _context(frags: list) -> str:
    blocks = []
    for i, f in enumerate(frags, start=1):
        art = f"Artículo {f['articulo']}" if f["articulo"] else "sin artículo"
        where = (f"Reglamento de la Ley 32069 (texto modificado por el DS 001-2026-EF)"
                 if f["ambito"] == "reglamento" else "Ley N.° 32069")
        blocks.append(f"[F{i}] {where} · {art} · {f['version']} · página {f['pagina']}\n{f['texto']}")
    return "\n\n".join(blocks)


def version_note(cited: list) -> str:
    """Deterministic note on which version the answer stands on, from fragment metadata."""
    m = cfg()["messages"]
    kinds = {f["ambito"] for f in cited}
    notes = []
    if "ley" in kinds:
        notes.append(m["version_ley"])
    if "reglamento" in kinds:
        notes.append(m["version_reglamento_ds"])
    return " ".join(notes)


def _result(pregunta: str, **kw) -> dict:
    base = {"pregunta": pregunta, "respuesta": None, "abstuvo": False, "motivo_abstencion": None, "fuentes": [],
            "nota_version": "", "mejor_similitud": None, "umbral": cfg()["engine"]["threshold"], "llamo_llm": False,
            "tokens": {"entrada": 0, "cache": 0, "salida": 0}, "costo_usd": 0.0, "franja_precio": None,
            "modelo": None, "latencia_s": 0.0, "error": None}
    base.update(kw)
    return base


def _source(ref: str, f: dict) -> dict:
    return {"ref": ref, "documento": f["documento"], "titulo": f["titulo"], "version": f["version"],
            "pagina": f["pagina"], "pagina_diario": f["pagina_diario"] or None, "articulo": f["articulo"],
            "ambito": f["ambito"], "similitud": f["similitud"], "fragmento": f["texto"]}


def responder(pregunta: str, umbral: float = None, k: int = None) -> dict:
    e, m = cfg()["engine"], cfg()["messages"]
    umbral = e["threshold"] if umbral is None else umbral
    k = k or e["top_k"]
    t0 = time.perf_counter()
    pregunta = (pregunta or "").strip()
    if not pregunta:
        return _result(pregunta, error=m["empty_question"], umbral=umbral)
    try:
        frags = search(pregunta, k)
    except Exception as ex:  # index missing or embeddings failure: an error, not an answer
        return _result(pregunta, error=f"{m['retrieval_error']} ({type(ex).__name__}: {ex})", umbral=umbral,
                       latencia_s=round(time.perf_counter() - t0, 3))
    best = frags[0]["similitud"] if frags else 0.0
    shown = [_source(f"F{i}", f) for i, f in enumerate(frags, start=1)]
    if best < umbral:  # decided BEFORE calling the LLM
        return _result(pregunta, respuesta=m["abstain_threshold"], abstuvo=True, motivo_abstencion="umbral",
                       fuentes=shown, mejor_similitud=best, umbral=umbral, latencia_s=round(time.perf_counter() - t0, 3))
    p = cfg()["prompts"]
    try:
        out = chat_json(p["system"], p["user"].format(pregunta=pregunta, contexto=_context(frags)))
    except Exception as ex:
        return _result(pregunta, error=f"{m['llm_error']} ({type(ex).__name__}: {str(ex)[:200]})", fuentes=shown,
                       mejor_similitud=best, umbral=umbral, llamo_llm=True, latencia_s=round(time.perf_counter() - t0, 3))
    d = out["data"]
    common = dict(mejor_similitud=best, umbral=umbral, llamo_llm=True, modelo=out["model"],
                  tokens={"entrada": out["tokens_in"], "cache": out["tokens_cached"], "salida": out["tokens_out"]},
                  costo_usd=out["cost_usd"], franja_precio=out["price_window"],
                  latencia_s=round(time.perf_counter() - t0, 3))
    if d.get("abstener"):
        motivo = d.get("motivo") if d.get("motivo") in MOTIVOS_LLM else "fuera_de_corpus"
        msg = m["abstain_reglamento"] if motivo == "reglamento" else m["abstain_out_of_corpus"]
        return _result(pregunta, respuesta=msg, abstuvo=True, motivo_abstencion=motivo, fuentes=shown, **common)
    cited_refs = [r for r in d.get("citas", []) if isinstance(r, str) and r.upper() in {s["ref"] for s in shown}]
    if not cited_refs:  # an answer without valid citations is not shown as an answer
        return _result(pregunta, respuesta=m["abstain_no_citations"], abstuvo=True, motivo_abstencion="sin_citas",
                       fuentes=shown, **common)
    cited = [s for s in shown if s["ref"] in {r.upper() for r in cited_refs}]
    return _result(pregunta, respuesta=d.get("respuesta", "").strip(), fuentes=cited,
                   nota_version=version_note(cited), **common)
