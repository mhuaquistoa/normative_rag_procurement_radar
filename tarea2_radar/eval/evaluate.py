"""Task 2 retrieval evaluation (no LLM, free).

Relevance is defined by a rule per question (department, category, minimum amount and a keyword
pattern on the description), so the "known relevant processes" are reproducible, not hand-picked.
  hit@k        at least one relevant process among the top k
  precision@k  share of the top k that is relevant
Each question is run twice: hybrid (parsed filters + semantic) and semantic only (no filters),
which measures what the filters add. The top-1 similarities also show whether the Task 1
threshold transfers to this corpus.
    python eval/evaluate.py  ->  reports/eval_radar.json, reports/eval_radar_questions.csv
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

TASK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TASK / "src"))
from process import fold  # noqa: E402
from query_parser import parse, to_where  # noqa: E402
from radar_config import cfg, path  # noqa: E402
from radar_index import count, search  # noqa: E402

KS = (1, 5, 10)


def relevant_ids(df: pd.DataFrame, q) -> set:
    m = pd.Series(True, index=df.index)
    if q["departamento"]:
        m &= df["departamento_key"].eq(q["departamento"])
    if q["categoria"]:
        m &= df["categoria"].eq(q["categoria"])
    if q["monto_min"]:
        m &= df["monto"].ge(float(q["monto_min"]))
    m &= df["texto_fold"].str.contains(q["patron"], regex=True)
    return set(df.loc[m, "ocid"])


def main() -> None:
    df = pd.read_parquet(path("processed") / "procesos.parquet")
    df["texto_fold"] = df["descripcion"].map(fold)
    qs = pd.read_csv(TASK / "eval" / "preguntas.csv", dtype=str).fillna("")
    rows = []
    for _, q in qs.iterrows():
        p = parse(q["pregunta"])
        where = to_where(p)
        n = count(where) if where else count()
        for mode, w in (("hibrido", where), ("solo_semantico", {})):
            hits = search(p["consulta_semantica"] if mode == "hibrido" else q["pregunta"], max(KS), w) if n else []
            row = {"id": q["id"], "en_dominio": q["en_dominio"] == "1", "modo": mode, "candidatos": n,
                   "top1_sim": hits[0]["similitud"] if hits else None, "filtros": json.dumps({k: v for k, v in p.items() if k != "consulta_semantica"}, ensure_ascii=False)}
            if q["en_dominio"] == "1":
                rel = relevant_ids(df, q)
                flags = [h["ocid"] in rel for h in hits]
                row["relevantes_en_corpus"] = len(rel)
                for k in KS:
                    row[f"hit@{k}"] = float(any(flags[:k]))
                    row[f"precision@{k}"] = float(np.mean(flags[:k])) if flags[:k] else 0.0
            rows.append(row)
    r = pd.DataFrame(rows)
    r.to_csv(path("reports") / "eval_radar_questions.csv", index=False)
    ind = r[r.en_dominio]
    summary = {mode: {c: round(float(g[c].mean()), 3) for c in [f"hit@{k}" for k in KS] + [f"precision@{k}" for k in KS]}
               for mode, g in ind.groupby("modo")}
    hyb = r[r.modo == "hibrido"]
    summary["top1_en_dominio_min"] = float(hyb[hyb.en_dominio].top1_sim.min())
    summary["top1_fuera_max"] = float(hyb[~hyb.en_dominio].top1_sim.max())
    summary["umbral_tarea1"] = cfg()["engine"]["threshold"]
    (path("reports") / "eval_radar.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print(hyb[["id", "candidatos", "top1_sim", "relevantes_en_corpus", "hit@1", "precision@5", "precision@10"]].to_string(index=False))


if __name__ == "__main__":
    main()
