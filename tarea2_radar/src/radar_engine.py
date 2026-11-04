"""ONLINE process of Task 2: hybrid RAG over process descriptions. No UI imports.

responder(pregunta, filtros=None) -> {
    pregunta, respuesta, abstuvo, motivo_abstencion (None | sin_resultados | umbral | fuera_de_corpus | sin_citas),
    filtros_aplicados, consulta_semantica, n_candidatos (processes passing the filters),
    procesos: [{ocid, descripcion, departamento, monto, fecha, categoria, comprador, metodo, similitud}],
    mejor_similitud, umbral, llamo_llm, tokens, costo_usd, franja_precio, latencia_s, error
}
Same decision logic as Task 1: filters first (exact), then semantic top-k inside them, then a
similarity GATE before the LLM, then an LLM that may abstain and must cite every process by its ocid.
"""
import time

from query_parser import parse, to_where
from radar_config import cfg
from radar_index import count, search
from shared import chat_json


def _result(pregunta, **kw):
    base = {"pregunta": pregunta, "respuesta": None, "abstuvo": False, "motivo_abstencion": None, "filtros_aplicados": {},
            "consulta_semantica": "", "n_candidatos": None, "procesos": [], "mejor_similitud": None,
            "umbral": cfg()["engine"]["threshold"], "llamo_llm": False, "tokens": {"entrada": 0, "cache": 0, "salida": 0},
            "costo_usd": 0.0, "franja_precio": None, "latencia_s": 0.0, "error": None}
    base.update(kw)
    return base


def _context(procs):
    out = []
    for p in procs:
        monto = f"S/ {p['monto']:,.0f}" if p["monto"] >= 0 else "monto no publicado"
        out.append(f"[{p['ocid']}] {p['categoria']} · {p['departamento_nombre']} · {monto} · {p['mes']} · "
                   f"{p['comprador']} · {p['metodo']}\n{p['descripcion'][:600]}")
    return "\n\n".join(out)


def responder(pregunta: str, filtros: dict = None, umbral: float = None, k: int = None) -> dict:
    e, m = cfg()["engine"], cfg()["messages"]
    umbral = e["threshold"] if umbral is None else umbral
    k = k or e["top_k"]
    t0 = time.perf_counter()
    pregunta = (pregunta or "").strip()
    if not pregunta:
        return _result(pregunta, error=m["empty_question"])
    parsed = parse(pregunta)
    f = {**{k2: v for k2, v in parsed.items() if k2 != "consulta_semantica"}, **(filtros or {})}  # sidebar overrides
    where = to_where(f)
    try:
        n = count(where)
        if n == 0:
            return _result(pregunta, respuesta=m["no_results"], abstuvo=True, motivo_abstencion="sin_resultados",
                           filtros_aplicados=f, consulta_semantica=parsed["consulta_semantica"], n_candidatos=0,
                           latencia_s=round(time.perf_counter() - t0, 3))
        procs = search(parsed["consulta_semantica"], min(k, n), where)
    except Exception as ex:
        return _result(pregunta, error=f"{m['retrieval_error']} ({type(ex).__name__}: {ex})", filtros_aplicados=f)
    best = procs[0]["similitud"] if procs else 0.0
    common = dict(filtros_aplicados=f, consulta_semantica=parsed["consulta_semantica"], n_candidatos=n,
                  procesos=procs, mejor_similitud=best, umbral=umbral)
    if best < umbral:  # decided before calling the LLM
        return _result(pregunta, respuesta=m["abstain_threshold"], abstuvo=True, motivo_abstencion="umbral",
                       latencia_s=round(time.perf_counter() - t0, 3), **common)
    p = cfg()["prompts"]
    try:
        out = chat_json(p["system"], p["user"].format(pregunta=pregunta, n=n, filtros=f or "ninguno",
                                                      contexto=_context(procs)))
    except Exception as ex:
        return _result(pregunta, error=f"{m['llm_error']} ({type(ex).__name__}: {str(ex)[:200]})", llamo_llm=True, **common)
    d = out["data"]
    cost = dict(llamo_llm=True, tokens={"entrada": out["tokens_in"], "cache": out["tokens_cached"], "salida": out["tokens_out"]},
                costo_usd=out["cost_usd"], franja_precio=out["price_window"], latencia_s=round(time.perf_counter() - t0, 3))
    if d.get("abstener"):
        return _result(pregunta, respuesta=m["abstain_out_of_corpus"], abstuvo=True, motivo_abstencion="fuera_de_corpus",
                       **common, **cost)
    known = {x["ocid"] for x in procs}
    cited = [c for c in d.get("citas", []) if c in known]
    if not cited:
        return _result(pregunta, respuesta=m["abstain_no_citations"], abstuvo=True, motivo_abstencion="sin_citas",
                       **common, **cost)
    return _result(pregunta, respuesta=d.get("respuesta", "").strip(), **{**common, **cost},
                   citados=cited)
