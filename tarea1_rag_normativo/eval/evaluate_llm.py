"""End-to-end check through the engine (calls the LLM, so it costs money: about USD 0.006 for the
20 questions). Complements the free retrieval evaluation with what only the full pipeline shows:
whether the final decision (answer / abstain) is right and whether the cited pages are the expected.

    python eval/evaluate_llm.py   ->  reports/eval_end_to_end.csv + .json
"""
import json
import sys
from pathlib import Path

import pandas as pd

TASK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TASK / "src"))
sys.path.insert(0, str(TASK / "eval"))
from config import path  # noqa: E402
from engine import responder  # noqa: E402
from evaluate import load_questions  # noqa: E402


def main() -> None:
    rows = []
    for _, q in load_questions().iterrows():
        r = responder(q["pregunta"])
        cited = {(s["documento"], str(s["pagina"])) for s in r["fuentes"]} if not r["abstuvo"] else set()
        in_domain = q["en_dominio"] == "1"
        rows.append({"id": q["id"], "en_dominio": in_domain, "estilo": q["estilo"], "abstuvo": r["abstuvo"],
                     "motivo": r["motivo_abstencion"], "llamo_llm": r["llamo_llm"], "mejor_similitud": r["mejor_similitud"],
                     "cita_pagina_esperada": bool(cited & q["esperadas"]) if in_domain and not r["abstuvo"] else None,
                     "decision_correcta": (not r["abstuvo"]) if in_domain else r["abstuvo"],
                     "costo_usd": r["costo_usd"], "franja": r["franja_precio"], "error": r["error"],
                     "respuesta": r["respuesta"]})
        print(rows[-1]["id"], rows[-1]["decision_correcta"], r["motivo_abstencion"], rows[-1]["cita_pagina_esperada"], flush=True)
    df = pd.DataFrame(rows)
    ind, out = df[df.en_dominio], df[~df.en_dominio]
    summary = {"preguntas": len(df), "decisiones_correctas": int(df.decision_correcta.sum()),
               "en_dominio_respondidas": int((~ind.abstuvo).sum()), "en_dominio_abstenidas_mal": int(ind.abstuvo.sum()),
               "fuera_abstenidas_bien": int(out.abstuvo.sum()), "fuera_respondidas_mal": int((~out.abstuvo).sum()),
               "abstenciones_por_umbral_sin_llm": int((df.motivo == "umbral").sum()),
               "citas_con_pagina_esperada": f"{int(ind.cita_pagina_esperada.fillna(False).sum())}/{int((~ind.abstuvo).sum())}",
               "costo_total_usd": round(float(df.costo_usd.sum()), 6),
               "costo_medio_por_pregunta_con_llm": round(float(df[df.llamo_llm].costo_usd.mean()), 6),
               "errores": int(df.error.notna().sum())}
    df.to_csv(path("reports") / "eval_end_to_end.csv", index=False)
    (path("reports") / "eval_end_to_end.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
