"""Phase 5 - risk indicator (single-bidder awards) and the precomputed tables the dashboard reads.

Single-bidder share = awarded processes with exactly one tenderer / awarded processes whose number
of tenderers is published, computed over COMPETITIVE methods only: in direct contracting, special
regimes, international contracting and agreements one supplier is the design, not a flag (their
share is 0.80-0.99 against 0.00-0.02 in competitive methods; riesgo_por_metodo.csv). Without this
cut the indicator mostly measures each buyer's mix of methods. Processes without that number are left out of the denominator and
counted separately (a missing count is not "one bidder").
Buyers enter the top-10 only with at least `risk.min_awarded` such processes: below that a single
case swings the share (1 of 2 = 50 %). Each share comes with its 95 % Wilson interval.
A red flag is a reason to look closer, not evidence of wrongdoing. Only public entities (buyers)
are ranked; no supplier or person is named.
    python src/metrics.py  ->  data/outputs/*.csv
"""
import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from radar_config import cfg, path  # noqa: E402


def wilson(k: int, n: int, z: float = 1.96) -> tuple:
    if n == 0:
        return (None, None)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return round(c - h, 4), round(c + h, 4)


def single_bidder(df: pd.DataFrame, by: list) -> pd.DataFrame:
    aw = df[df["adjudicado"]]
    known = aw[aw["n_postores"].notna()]
    g = known.groupby(by).agg(adjudicados_con_postores=("ocid", "size"), un_solo_postor=("un_solo_postor", "sum"))
    g["adjudicados_sin_dato_postores"] = aw[aw["n_postores"].isna()].groupby(by).size().reindex(g.index).fillna(0).astype(int)
    g["proporcion_un_solo_postor"] = (g["un_solo_postor"] / g["adjudicados_con_postores"]).round(4)
    ci = [wilson(int(k), int(n)) for k, n in zip(g["un_solo_postor"], g["adjudicados_con_postores"])]
    g["ic95_bajo"], g["ic95_alto"] = zip(*ci) if ci else ([], [])
    return g.reset_index()


def competitive(df: pd.DataFrame) -> pd.DataFrame:
    """Processes whose method is competitive (config risk.non_competitive_methods excluded)."""
    return df[~df["metodo"].isin(cfg()["risk"]["non_competitive_methods"])]


def main() -> None:
    raw_df = pd.read_parquet(path("processed") / "procesos.parquet")
    df = competitive(raw_df)
    out = path("outputs")
    single_bidder(raw_df, ["metodo"]).to_csv(out / "riesgo_por_metodo.csv", index=False)
    dep = raw_df.groupby("departamento").agg(procesos=("ocid", "size"), monto_total=("monto", "sum"),
                                             procesos_con_monto=("monto", "count")).reset_index()
    dep = dep.merge(single_bidder(df, ["departamento"]), on="departamento", how="left")
    dep.to_csv(out / "por_departamento.csv", index=False)
    buyers = single_bidder(df, ["comprador_key", "comprador", "departamento"])
    m = cfg()["risk"]["min_awarded"]
    top = buyers[buyers["adjudicados_con_postores"] >= m].sort_values(
        ["proporcion_un_solo_postor", "adjudicados_con_postores"], ascending=[False, False]).head(10)
    buyers.to_csv(out / "riesgo_compradores.csv", index=False)
    top.to_csv(out / "riesgo_top10_compradores.csv", index=False)
    df.groupby(["mes", "categoria"]).agg(procesos=("ocid", "size"), monto_total=("monto", "sum")).reset_index().to_csv(
        out / "por_mes_categoria.csv", index=False)
    nat = {"minimo": m, "compradores_elegibles": int((buyers["adjudicados_con_postores"] >= m).sum())}
    for name, d in (("competitivos", df), ("todos_los_metodos", raw_df)):
        aw = d[d["adjudicado"] & d["n_postores"].notna()]
        nat[name] = {"adjudicados_con_postores": int(len(aw)), "un_solo_postor": int(aw["un_solo_postor"].sum()),
                     "proporcion": round(float(aw["un_solo_postor"].mean()), 4)}
    pd.Series(nat).to_json(out / "riesgo_nacional.json", force_ascii=False, indent=1)
    print(nat)
    print(top[["comprador", "departamento", "adjudicados_con_postores", "un_solo_postor", "proporcion_un_solo_postor", "ic95_bajo"]].to_string(index=False))


if __name__ == "__main__":
    main()
