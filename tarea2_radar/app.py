"""Task 2 dashboard - Procurement Radar. Reads precomputed files only: it never downloads the bulk
files nor rebuilds the index. Run: streamlit run app.py
"""
import json
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

TASK = Path(__file__).resolve().parent
sys.path.insert(0, str(TASK / "src"))
from metrics import competitive, single_bidder  # noqa: E402
from radar_config import cfg, path  # noqa: E402

st.set_page_config(page_title="Radar de Compras Públicas", page_icon="🗺️", layout="wide")
RED_FLAG_NOTE = ("**Un solo postor es una señal para mirar más de cerca, no evidencia de irregularidad.** "
                 "Hay métodos y mercados donde es normal recibir una sola oferta. Solo se nombran entidades públicas.")


@st.cache_data
def load_processes() -> pd.DataFrame:
    return pd.read_parquet(path("processed") / "procesos.parquet")


@st.cache_data
def load_geojson() -> dict:
    return json.loads((path("raw") / "geo" / "peru_departamental.geojson").read_text(encoding="utf-8"))


@st.cache_data
def load_quality() -> dict:
    return json.loads((path("reports") / "data_quality.json").read_text(encoding="utf-8"))


@st.cache_resource(show_spinner="Cargando el modelo de embeddings…")
def engine():
    import radar_engine  # loads the local embeddings model once per server
    from shared import get_embedder
    get_embedder(cfg()["index"]["embedder"])
    return radar_engine


df = load_processes()
with st.sidebar:
    st.header("Filtros")
    deps = sorted(df["departamento"].dropna().unique())
    sel_dep = st.multiselect("Departamento", deps)
    sel_cat = st.multiselect("Categoría", sorted(df["categoria"].unique()))
    max_amount = float(df["monto"].max())
    amt = st.slider("Monto (S/ millones)", 0.0, round(max_amount / 1e6, 1), (0.0, round(max_amount / 1e6, 1)), 0.1)
    include_no_amount = st.checkbox("Incluir procesos sin monto publicado", value=True)
    dmin, dmax = df["fecha"].min().date(), df["fecha"].max().date()
    dates = st.date_input("Fecha de publicación", (dmin, dmax), min_value=dmin, max_value=dmax)
    umbral = st.slider("Umbral de similitud (preguntas)", 0.70, 0.95, float(cfg()["engine"]["threshold"]), 0.005)

f = df.copy()
if sel_dep:
    f = f[f["departamento"].isin(sel_dep)]
if sel_cat:
    f = f[f["categoria"].isin(sel_cat)]
in_range = f["monto"].between(amt[0] * 1e6, amt[1] * 1e6)
f = f[in_range | (f["monto"].isna() & include_no_amount)]
if isinstance(dates, tuple) and len(dates) == 2:
    f = f[(f["fecha"].dt.date >= dates[0]) & (f["fecha"].dt.date <= dates[1])]

st.title("🗺️ Radar de Compras Públicas")
st.caption(f"OECE · datos abiertos OCDS · {', '.join(cfg()['oece']['months'])} · una fila por proceso (ocid)")
if f.empty:
    st.warning("Ningún proceso cumple los filtros elegidos. Amplía la selección en la barra lateral.")
    st.stop()

fc = competitive(f)
aw = fc[fc["adjudicado"] & fc["n_postores"].notna()]
share = aw["un_solo_postor"].mean() if len(aw) else float("nan")
k1, k2, k3, k4 = st.columns(4)
k1.metric("Procesos", f"{len(f):,}")
k2.metric("Monto total (con monto publicado)", f"S/ {f['monto'].sum() / 1e6:,.1f} M", help=f"{f['monto'].isna().sum():,} procesos sin monto")
k3.metric("Departamentos", f"{f['departamento'].nunique()}")
k4.metric("Un solo postor (métodos competitivos)", "—" if pd.isna(share) else f"{share:.1%}",
          help=f"sobre {len(aw):,} adjudicados con número de postores publicado, sin contratación directa ni regímenes especiales")

tab_map, tab_q, tab_table, tab_dist, tab_risk, tab_quality = st.tabs(
    ["Mapa", "Preguntar", "Ranking", "Distribución", "Riesgo: un solo postor", "Calidad de datos"])

with tab_map:
    metric = st.radio("Colorear por", ["Número de procesos", "Monto total (S/)"], horizontal=True)
    by = f.groupby("departamento_key").agg(departamento=("departamento", "first"), procesos=("ocid", "size"),
                                           monto=("monto", "sum")).reset_index()
    col = "procesos" if metric.startswith("Número") else "monto"
    fig = px.choropleth(by, geojson=load_geojson(), locations="departamento_key", featureidkey="properties.NOMBDEP",
                        color=col, hover_name="departamento", hover_data={"procesos": ":,", "monto": ":,.0f", "departamento_key": False},
                        color_continuous_scale="Blues", labels={"procesos": "procesos", "monto": "monto S/"})
    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_layout(height=560, margin=dict(l=0, r=0, t=0, b=0))
    st.plotly_chart(fig, width="stretch")

with tab_q:
    st.caption("Las condiciones de lugar, monto, categoría y mes se aplican como **filtros exactos**; el tema se busca por significado.")
    q = st.text_input("Pregunta", "obras de agua y saneamiento en Cusco por más de un millón de soles")
    if st.button("Buscar", type="primary"):
        side = {}
        if sel_dep:
            from process import fold
            side["departamentos"] = [fold(d) for d in sel_dep]
        if sel_cat and len(sel_cat) == 1:
            side["categoria"] = sel_cat[0]
        with st.spinner("Buscando procesos…"):
            st.session_state["r2"] = engine().responder(q, filtros=side, umbral=umbral)
    r = st.session_state.get("r2")
    if r:
        st.write("**Filtros aplicados:**", r["filtros_aplicados"] or "ninguno", "· **búsqueda semántica:**", f"`{r['consulta_semantica']}`",
                 f"· candidatos: {r['n_candidatos']}")
        if r["error"]:
            st.error(r["error"])
        elif r["abstuvo"]:
            st.warning(f"Se abstuvo (`{r['motivo_abstencion']}`): {r['respuesta']}")
        else:
            st.success(r["respuesta"])
        if r["procesos"]:
            t = pd.DataFrame(r["procesos"])[["ocid", "similitud", "departamento_nombre", "categoria", "monto", "mes", "comprador", "descripcion"]]
            t["monto"] = t["monto"].where(t["monto"] >= 0)
            st.dataframe(t, hide_index=True, width="stretch")
        st.caption(f"Costo de la consulta: US$ {r['costo_usd']:.6f} · ¿llamó al LLM? {'sí' if r['llamo_llm'] else 'no'} · "
                   f"mejor similitud {r['mejor_similitud']}")

with tab_table:
    show = f[["ocid", "fecha", "departamento", "categoria", "monto", "comprador", "metodo", "n_postores", "descripcion"]]
    show = show.sort_values("monto", ascending=False)
    st.dataframe(show, hide_index=True, width="stretch", height=480)
    st.download_button("Descargar CSV", show.to_csv(index=False).encode("utf-8-sig"), "procesos_filtrados.csv", "text/csv")

with tab_dist:
    c1, c2 = st.columns(2)
    by_cat = f.groupby(["mes", "categoria"]).size().reset_index(name="procesos")
    c1.plotly_chart(px.bar(by_cat, x="mes", y="procesos", color="categoria", title="Procesos por mes y categoría",
                           color_discrete_sequence=["#2459C7", "#E8692C", "#7A8B99"]), width="stretch")
    top_dep = f.groupby("departamento")["monto"].sum().sort_values(ascending=True).tail(15).reset_index()
    c2.plotly_chart(px.bar(top_dep, x="monto", y="departamento", orientation="h", title="Monto total por departamento (S/)",
                           color_discrete_sequence=["#2459C7"]), width="stretch")

with tab_risk:
    st.info(RED_FLAG_NOTE)
    only_comp = st.checkbox("Solo métodos competitivos", value=True,
                            help="Excluye " + ", ".join(cfg()["risk"]["non_competitive_methods"]) +
                                 ": en ellos un solo proveedor es lo esperado (80-99 % de un solo postor), no una alerta.")
    base = fc if only_comp else f
    with st.expander("¿Por qué separar los métodos? Proporción de un solo postor por método"):
        st.dataframe(single_bidder(f, ["metodo"]).sort_values("adjudicados_con_postores", ascending=False), hide_index=True, width="stretch")
    m = cfg()["risk"]["min_awarded"]
    dep_r = single_bidder(base, ["departamento"]).sort_values("proporcion_un_solo_postor", ascending=False)
    st.subheader("Por departamento")
    st.dataframe(dep_r, hide_index=True, width="stretch")
    st.subheader(f"Top 10 entidades compradoras (mínimo {m} adjudicaciones con número de postores)")
    buy = single_bidder(base, ["comprador_key", "comprador", "departamento"])
    top = buy[buy["adjudicados_con_postores"] >= m].sort_values(["proporcion_un_solo_postor", "adjudicados_con_postores"],
                                                                ascending=[False, False]).head(10)
    if top.empty:
        st.caption("Ninguna entidad alcanza el mínimo con los filtros actuales.")
    else:
        st.dataframe(top.drop(columns="comprador_key"), hide_index=True, width="stretch")
    st.caption("Proporción = adjudicados con exactamente un postor / adjudicados con número de postores publicado; "
               "IC95 = intervalo de Wilson. Referencias: Open Contracting Partnership, Red Flags in Public Procurement (2024); "
               "Ojo Público, Funes.")

with tab_quality:
    st.subheader("Reglas de validación (sobre el total descargado)")
    for rule, vals in load_quality().items():
        with st.expander(rule, expanded=True):
            st.json(vals)
