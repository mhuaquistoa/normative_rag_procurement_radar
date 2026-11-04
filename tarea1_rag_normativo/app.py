"""Streamlit interface for Task 1. Interface only: every answer comes from engine.responder().
It loads the existing index and never rebuilds it.  Run: streamlit run app.py
"""
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

TASK = Path(__file__).resolve().parent
sys.path.insert(0, str(TASK / "src"))
from config import cfg, path  # noqa: E402
from embeddings import get_embedder  # noqa: E402
from engine import responder  # noqa: E402

st.set_page_config(page_title="Asistente de Contrataciones Públicas", page_icon="⚖️", layout="wide")
REPORTS = path("reports")
EJEMPLOS = ["Soy una pequeña empresa, ¿pueden retenerme parte del pago en vez de pedirme una carta fianza?",
            "¿Es necesario suscribir una adenda para aprobar una prestación adicional de obra?",
            "¿Quiénes están impedidos de contratar con el Estado?",
            "¿Cómo se calcula la penalidad diaria por mora según el Reglamento?",
            "¿Cómo preparo un ceviche?"]


@st.cache_resource(show_spinner="Cargando el modelo de embeddings…")
def warm_up():
    return get_embedder().name  # loads the local model once per server, not per question


def read_csv(name):
    f = REPORTS / name
    return pd.read_csv(f) if f.exists() else None


warm_up()
with st.sidebar:
    st.header("Ajustes")
    umbral = st.slider("Umbral de similitud", 0.70, 0.95, float(cfg()["engine"]["threshold"]), 0.005,
                       help="Si el mejor fragmento queda por debajo, el asistente se abstiene sin llamar al LLM.")
    k = st.slider("Fragmentos recuperados (k)", 1, 10, int(cfg()["engine"]["top_k"]))
    st.caption(f"Embeddings: {cfg()['embeddings'][cfg()['embeddings']['active']]['model']} · "
               f"LLM: {cfg()['llm']['model']} · fragmentos: {cfg()['chunking']['active']}")
    st.caption("Corpus: Ley N.° 32069 (texto hasta 19-07-2026) y DS N.° 001-2026-EF (modifica el Reglamento).")

st.title("⚖️ Asistente de Contrataciones Públicas")
st.caption("Responde solo con la Ley 32069 y el DS 001-2026-EF, cita documento y página, y se abstiene cuando no sabe.")
tab_q, tab_calidad, tab_eval, tab_costos = st.tabs(["Preguntar", "Calidad de extracción", "Evaluación", "Costos"])

with tab_q:
    ejemplo = st.selectbox("Ejemplos", [""] + EJEMPLOS)
    pregunta = st.text_area("Tu pregunta", value=ejemplo, height=80)
    if st.button("Preguntar", type="primary", disabled=not pregunta.strip()):
        with st.spinner("Buscando en las normas…"):
            st.session_state["r"] = responder(pregunta, umbral=umbral, k=k)
    r = st.session_state.get("r")
    if r:
        if r["error"]:
            st.error(f"Error: {r['error']}")
        elif r["abstuvo"]:
            st.warning(f"**Se abstuvo** (motivo: `{r['motivo_abstencion']}`)\n\n{r['respuesta']}")
        else:
            st.success(r["respuesta"])
            if r["nota_version"]:
                st.info(f"Versión: {r['nota_version']}")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Mejor similitud", f"{r['mejor_similitud']:.3f}" if r["mejor_similitud"] is not None else "—",
                  help=f"umbral {r['umbral']}")
        c2.metric("¿Llamó al LLM?", "sí" if r["llamo_llm"] else "no")
        c3.metric("Costo de la consulta", f"US$ {r['costo_usd']:.6f}", help=f"franja de precio: {r['franja_precio']}")
        c4.metric("Tokens entrada / salida", f"{r['tokens']['entrada']} / {r['tokens']['salida']}",
                  help=f"en caché: {r['tokens']['cache']}")
        if r["fuentes"]:
            st.subheader("Fuentes citadas" if not r["abstuvo"] else "Fragmentos recuperados (no usados)")
            for s in r["fuentes"]:
                pag = f"pág. {s['pagina']}" + (f" (El Peruano p. {s['pagina_diario']})" if s["pagina_diario"] else "")
                with st.expander(f"[{s['ref']}] {s['titulo']} · Art. {s['articulo'] or '—'} · {pag} · similitud {s['similitud']:.3f}"):
                    st.caption(s["version"])
                    st.write(s["fragmento"])

with tab_calidad:
    st.subheader("Chequeo de fuentes")
    sc = read_csv("source_check.csv")
    if sc is not None:
        st.dataframe(sc, hide_index=True, width="stretch")
    q = REPORTS / "extraction_quality.json"
    if q.exists():
        st.subheader("Reporte de extracción")
        st.dataframe(pd.DataFrame(json.loads(q.read_text(encoding="utf-8"))).T, width="stretch")
    md = REPORTS / "extraction_quality.md"
    if md.exists():
        with st.expander("Antes y después de la limpieza, y muestras"):
            st.markdown(md.read_text(encoding="utf-8"))

with tab_eval:
    st.subheader("Recuperación (sin llamar al LLM)")
    ev = read_csv("eval_summary.csv")
    if ev is not None:
        st.dataframe(ev.sort_values("recall@3", ascending=False), hide_index=True, width="stretch")
    sw = read_csv(f"threshold_sweep_{cfg()['embeddings']['active']}_{cfg()['chunking']['active']}.csv")
    if sw is not None:
        st.subheader("Barrido del umbral")
        st.line_chart(sw.set_index("umbral")[["en_dominio_abstenidas_mal", "fuera_abstenidas_bien", "errores_totales"]])
    e2e = REPORTS / "eval_end_to_end.json"
    if e2e.exists():
        st.subheader("De punta a punta (con LLM)")
        st.json(json.loads(e2e.read_text(encoding="utf-8")))

with tab_costos:
    calls = pd.read_csv(path("logs") / "calls.csv") if (path("logs") / "calls.csv").exists() else None
    if calls is None:
        st.info("Aún no hay llamadas registradas.")
    else:
        st.dataframe(calls.groupby(["kind", "model", "price_window", "ok"]).agg(
            llamadas=("ok", "size"), tokens_entrada=("tokens_in", "sum"), tokens_salida=("tokens_out", "sum"),
            costo_usd=("cost_usd", "sum"), latencia_media_s=("latency_s", "mean")).reset_index(), hide_index=True, width="stretch")
        st.caption("Precios: " + "; ".join(f"{m} ({p['source']}, verificado {p['verified']})" for m, p in cfg()["pricing"].items()))
        with st.expander("Registro completo de llamadas"):
            st.dataframe(calls, hide_index=True, width="stretch")
