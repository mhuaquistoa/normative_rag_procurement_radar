"""Phase 2-4 evaluation without calling the generation model (it costs nothing, so it can run on
every change, and every chunking/threshold/embedder choice is made with the same yardstick).

  Recall@k            retrieval stage: share of in-domain questions with at least one expected
                      (document, page) among the top-k fragments.
  abstention sweep    decision stage: for each threshold t on the best fragment's similarity,
                      in-domain questions wrongly abstained and out-of-domain questions correctly
                      abstained. The engine abstains before calling the LLM when top-1 < t.

    python eval/evaluate.py                          # active embedder and chunking config
    python eval/evaluate.py --chunking all           # every chunking config (each index must be built)
    python eval/evaluate.py --embedder api --chunking medium
Output: reports/eval_<embedder>_<chunking>.json, reports/eval_summary.csv, reports/threshold_sweep_<..>.csv
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

TASK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TASK / "src"))
from config import cfg, path  # noqa: E402
from embeddings import get_embedder  # noqa: E402
from index import search  # noqa: E402

KS = (1, 3, 5)


def load_questions() -> pd.DataFrame:
    q = pd.read_csv(TASK / "eval" / "preguntas.csv", dtype=str).fillna("")
    q["esperadas"] = q["paginas_esperadas"].apply(lambda s: {tuple(x.split(":")) for x in s.split(";") if x})
    return q


def evaluate(embedder_key: str, chunking: str, k_max: int = 10) -> dict:
    q = load_questions()
    emb = get_embedder(embedder_key)
    rows, latencies = [], []
    for _, r in q.iterrows():
        t0 = time.perf_counter()
        vec = emb.embed_query(r["pregunta"])
        latencies.append(time.perf_counter() - t0)
        hits = search(r["pregunta"], k_max, embedder_key, chunking, query_vector=vec)
        ranks = [i + 1 for i, h in enumerate(hits) if (h["documento"], str(h["pagina"])) in r["esperadas"]]
        rows.append({"id": r["id"], "en_dominio": r["en_dominio"] == "1", "estilo": r["estilo"],
                     "top1_sim": hits[0]["similitud"], "rank": ranks[0] if ranks else None,
                     "top1": f"{hits[0]['documento']}:p{hits[0]['pagina']}"})
    df = pd.DataFrame(rows)
    ind = df[df.en_dominio]
    recall = {f"recall@{k}": round(float((ind["rank"].fillna(99) <= k).mean()), 3) for k in KS}
    recall_mype = {f"recall@{k}_mype": round(float((ind[ind.estilo == "mype"]["rank"].fillna(99) <= k).mean()), 3) for k in KS}
    sweep = []
    for t in np.round(np.arange(0.70, 0.951, 0.005), 3):
        wrong_abstain = int((ind["top1_sim"] < t).sum())
        right_abstain = int((df[~df.en_dominio]["top1_sim"] < t).sum())
        sweep.append({"umbral": t, "en_dominio_abstenidas_mal": wrong_abstain,
                      "fuera_abstenidas_bien": right_abstain,
                      "errores_totales": wrong_abstain + (int((~df.en_dominio).sum()) - right_abstain)})
    sweep = pd.DataFrame(sweep)
    out = {"embedder": embedder_key, "model": cfg()["embeddings"][embedder_key]["model"], "chunking": chunking,
           **recall, **recall_mype, "query_latency_ms": round(1000 * float(np.mean(latencies)), 1),
           "in_domain_top1_sim_min": float(ind["top1_sim"].min()),
           "out_domain_top1_sim_max": float(df[~df.en_dominio]["top1_sim"].max()),
           "per_question": rows}
    name = f"{embedder_key}_{chunking}"
    sweep.to_csv(path("reports") / f"threshold_sweep_{name}.csv", index=False)
    (path("reports") / f"eval_{name}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--embedder", default=cfg()["embeddings"]["active"])
    ap.add_argument("--chunking", default=cfg()["chunking"]["active"], help="a config name, or 'all'")
    a = ap.parse_args()
    configs = list(cfg()["chunking"]["configs"]) if a.chunking == "all" else [a.chunking]
    summary_file = path("reports") / "eval_summary.csv"
    old = pd.read_csv(summary_file) if summary_file.exists() else pd.DataFrame()
    new = []
    for ch in configs:
        r = evaluate(a.embedder, ch)
        new.append({k: v for k, v in r.items() if k != "per_question"})
        print(json.dumps(new[-1], ensure_ascii=False))
    new = pd.DataFrame(new)
    if len(old):
        old = old[~old.set_index(["embedder", "chunking"]).index.isin(new.set_index(["embedder", "chunking"]).index)]
    pd.concat([old, new], ignore_index=True).to_csv(summary_file, index=False)


if __name__ == "__main__":
    main()
