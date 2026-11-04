"""Figures and tables for the README and the video.
    python eval/plots.py  ->  reports/figures/*.png, reports/chunk_stats.csv|md
"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

TASK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TASK / "src"))
from chunking import chunk_all  # noqa: E402
from config import cfg, path  # noqa: E402

FIG = path("reports") / "figures"
FIG.mkdir(exist_ok=True)


def threshold_figure() -> None:
    emb, ch = cfg()["embeddings"]["active"], cfg()["chunking"]["active"]
    per = pd.DataFrame(json.loads((path("reports") / f"eval_{emb}_{ch}.json").read_text(encoding="utf-8"))["per_question"])
    fig, ax = plt.subplots(figsize=(9, 3.6))
    for dom, color, label in ((True, "#2459C7", "en dominio (15)"), (False, "#C2521B", "fuera de dominio (5)")):
        d = per[per.en_dominio == dom]
        ax.scatter(d.top1_sim, [1 if dom else 0] * len(d), s=70, color=color, label=label, alpha=0.8)
        for _, r in d.iterrows():
            ax.annotate(r["id"], (r.top1_sim, 1 if dom else 0), xytext=(0, 8), textcoords="offset points",
                        fontsize=7, ha="center")
    t = cfg()["engine"]["threshold"]
    ax.axvline(t, color="black", ls="--", lw=1)
    ax.text(t, 0.5, f" umbral {t}", fontsize=9)
    ax.set(yticks=[0, 1], yticklabels=["fuera", "dentro"], xlabel="similitud del mejor fragmento (coseno)",
           title=f"Calibración del umbral ({cfg()['embeddings'][emb]['model']}, {ch})", ylim=(-0.6, 1.6))
    ax.legend(loc="lower right", fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG / "threshold_calibration.png", dpi=150)
    plt.close(fig)

    sw = pd.read_csv(path("reports") / f"threshold_sweep_{emb}_{ch}.csv")
    fig, ax = plt.subplots(figsize=(8, 3.6))
    ax.plot(sw.umbral, sw.en_dominio_abstenidas_mal, label="preguntas válidas rechazadas (de 15)", color="#2459C7")
    ax.plot(sw.umbral, sw.fuera_abstenidas_bien, label="preguntas fuera rechazadas (de 5)", color="#C2521B")
    ax.axvline(t, color="black", ls="--", lw=1)
    ax.set(xlabel="umbral", ylabel="preguntas", title="Barrido del umbral (decisión antes del LLM)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG / "threshold_sweep.png", dpi=150)
    plt.close(fig)


def chunk_stats() -> None:
    rows = []
    fig, ax = plt.subplots(figsize=(8, 3.6))
    for name, c in cfg()["chunking"]["configs"].items():
        ch = pd.DataFrame(chunk_all(c["size"], c["overlap"], c.get("header", False)))
        for doc, g in ch.groupby("documento"):
            rows.append({"config": name, "size": c["size"], "overlap": c["overlap"], "header": c.get("header", False),
                         "documento": doc, "fragmentos": len(g), "chars_p10": int(g.chars.quantile(.1)),
                         "chars_mediana": int(g.chars.median()), "chars_p90": int(g.chars.quantile(.9)), "chars_max": int(g.chars.max())})
        if name in ("small", "medium", "large"):
            ax.hist(ch.chars, bins=40, alpha=0.5, label=f"{name} ({c['size']}/{c['overlap']})")
    ax.set(xlabel="caracteres por fragmento", ylabel="fragmentos", title="Distribución del largo de los fragmentos")
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(FIG / "chunk_lengths.png", dpi=150)
    plt.close(fig)
    df = pd.DataFrame(rows)
    df.to_csv(path("reports") / "chunk_stats.csv", index=False)
    (path("reports") / "chunk_stats.md").write_text(df.to_markdown(index=False), encoding="utf-8")


if __name__ == "__main__":
    threshold_figure()
    chunk_stats()
    print("figures:", sorted(p.name for p in FIG.glob("*.png")))
