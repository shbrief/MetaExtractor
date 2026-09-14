#!/usr/bin/env python
"""Generate manuscript figures for MANUSCRIPT.md.

Static PNGs (portable across GitHub markdown + pandoc HTML). CVD-safe Okabe-Ito
palette: Sonnet 5 = blue #0072B2, Haiku 4.5 = orange #E69F00, gold = gray.

Figures 2 and 3 are generated from the scoring outputs of a run tree — no
numbers are transcribed by hand:

  TREE/aggregate_v2.json   (benchmarks/cmd_sonnet5/aggregate.py)
  TREE/harmonization.json  (benchmarks/cmd_sonnet5/bench.py harmonize)

  python figures/make_figures.py [--tree benchmarks/cmd_sonnet5/out_v2]
"""
from __future__ import annotations
import argparse
import json
import pathlib
import statistics as st
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

OUT = pathlib.Path(__file__).resolve().parent
OUT.mkdir(exist_ok=True)

SONNET = "#0072B2"
HAIKU = "#E69F00"
GOLD = "#6b6b6b"
INK = "#1a1a1a"
MUTED = "#6b6b6b"
GRID = "#e3e3e0"
DET = "#dbe7f3"      # deterministic step fill (pale blue)
DET_E = "#2b6ca3"
LLM = "#fbe6c2"      # LLM-call fill (pale orange)
LLM_E = "#c9821b"
IO = "#ececea"       # input/output fill (neutral)
IO_E = "#8a8a86"

mpl.rcParams.update({
    "font.family": "Helvetica",
    "font.size": 10,
    "axes.edgecolor": MUTED,
    "axes.linewidth": 0.8,
    "text.color": INK,
    "axes.labelcolor": INK,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "figure.dpi": 200,
    "savefig.dpi": 200,
    "savefig.bbox": "tight",
})


def _clean(ax, grid_axis="y"):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.grid(axis=grid_axis, color=GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)


# ---------------------------------------------------------------- Figure 1
def fig1_pipeline():
    # DejaVu Sans carries the → glyph that Helvetica lacks; use it for this diagram.
    prev_family = mpl.rcParams["font.family"]
    mpl.rcParams["font.family"] = "DejaVu Sans"
    fig, ax = plt.subplots(figsize=(8.6, 7.4))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 106)
    ax.axis("off")

    def box(x, y, w, h, text, fill, edge, fs=8.3, bold=False):
        ax.add_patch(FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0.6,rounding_size=1.6",
            linewidth=1.2, edgecolor=edge, facecolor=fill, zorder=2))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
                fontsize=fs, color=INK, zorder=3,
                fontweight="bold" if bold else "normal", linespacing=1.25)
        return {"top": (x + w / 2, y + h), "bot": (x + w / 2, y), "cx": x + w / 2,
                "left": (x, y + h / 2), "right": (x + w, y + h / 2)}

    def arrow(p_from, p_to):
        ax.add_patch(FancyArrowPatch(p_from, p_to, arrowstyle="-|>", mutation_scale=12,
                                     linewidth=1.2, color=MUTED, zorder=1,
                                     shrinkA=2, shrinkB=2))

    paper = box(4, 90, 40, 8, "Paper\n(PMID · PMCID · DOI · PDF · text)", IO, IO_E, bold=True)
    schema = box(56, 90, 40, 8, "Target schema\n(JSON · YAML · LinkML subset)", IO, IO_E, bold=True)
    fetch = box(4, 72, 40, 11,
                "Document retrieval (best-scoring text)\nPMC · Europe PMC · Europe PMC PDF ·\n"
                "Unpaywall PDF · abstract floor\n+ supplementary files · SRA/ENA run manifest",
                DET, DET_E, fs=7.9)
    adapt = box(56, 74, 40, 8, "Schema adaptation\ntyped fields · static enums · scope",
                DET, DET_E)
    gate = box(56, 58, 40, 7.5,
               "Table path: relevance gate · matrix reject\n(ENA manifest only if no own-table rows)",
               DET, DET_E, fs=7.8)
    plan = box(56, 45, 40, 7.5, "Bounded LLM plan per table\n(headers · id columns · melt recipe)",
               LLM, LLM_E, fs=8.0)
    execute = box(56, 32, 40, 7.5, "Python executor: copy cells by index\n· column map · join on key",
                  DET, DET_E, fs=8.0)
    disc = box(4, 52, 40, 8.5,
               "Optional LLM sample discovery\n(model-constructed sample IDs;\nonly when no table was parsed)",
               LLM, LLM_E, fs=7.9)
    llmx = box(4, 35, 40, 10,
               "LLM field-batch extraction\n≤30 fields/call · values + provenance\n"
               "JSON parsed · Pydantic structural check",
               LLM, LLM_E, fs=7.9)
    rules = box(22, 16, 56, 8.5,
                "Deterministic sample rules: scoped fan-out of study/subgroup values\n"
                "· opt-in age rules · per-cell source recorded",
                DET, DET_E, fs=7.9)
    out = box(22, 2, 56, 8, "Output: JSON (fields + provenance, sample rows + sources,\n"
                            "table-selection log, warnings) + CSV", IO, IO_E, fs=8.0, bold=True)

    arrow(paper["bot"], fetch["top"])
    arrow(schema["bot"], adapt["top"])
    arrow(fetch["bot"], disc["top"])
    arrow(disc["bot"], llmx["top"])
    arrow(adapt["bot"], gate["top"])
    arrow(fetch["right"], (gate["left"][0], gate["left"][1] + 2))
    arrow(adapt["left"], (llmx["right"][0] - 2, llmx["top"][1]))
    arrow(gate["bot"], plan["top"])
    arrow(plan["bot"], execute["top"])
    arrow(llmx["bot"], (rules["cx"] - 14, rules["top"][1]))
    arrow(execute["bot"], (rules["cx"] + 14, rules["top"][1]))
    arrow(rules["bot"], out["top"])

    for i, (fc, ec, lab) in enumerate([(DET, DET_E, "deterministic step"),
                                       (LLM, LLM_E, "LLM call"),
                                       (IO, IO_E, "input / output")]):
        x = 6 + i * 31
        ax.add_patch(FancyBboxPatch((x, 101.2), 2.6, 2.4, boxstyle="round,pad=0.1,rounding_size=0.5",
                                    linewidth=1.1, edgecolor=ec, facecolor=fc))
        ax.text(x + 3.6, 102.4, lab, fontsize=8.2, va="center", color=INK)

    fig.savefig(OUT / "fig1_pipeline.png")
    plt.close(fig)
    mpl.rcParams["font.family"] = prev_family


# ---------------------------------------------------------------- helpers
MODEL_STYLE = {"sonnet": ("Sonnet 5", SONNET, "#07507c"), "haiku": ("Haiku 4.5", HAIKU, "#a9720f")}


def _metrics(c):
    tp = c["tp_correct"] + c["tp_wrong"]
    vp = c["tp_correct"] / (tp + c["fp"]) if tp + c["fp"] else None
    vr = c["tp_correct"] / (tp + c["fn"]) if tp + c["fn"] else None
    f1 = 2 * vp * vr / (vp + vr) if vp is not None and vr is not None and vp + vr else None
    return f1


# ---------------------------------------------------------------- Figure 2
def fig2_model_compare(agg: dict):
    import numpy as np
    models = [m for m in ("sonnet", "haiku") if m in agg["models"]]
    keys = [("value_precision", "value\nprecision"), ("value_recall", "value\nrecall"),
            ("value_f1", "value\nF1"), ("presence_precision", "presence\nprecision"),
            ("presence_recall", "presence\nrecall")]
    fig = plt.figure(figsize=(9.0, 6.6))
    gs = fig.add_gridspec(2, 2, width_ratios=[3.4, 1], height_ratios=[1, 1.05],
                          hspace=0.55, wspace=0.28)
    ax, axfp, axs = fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1]), fig.add_subplot(gs[1, :])

    _clean(ax)
    x = np.arange(len(keys))
    w = 0.36
    for j, m in enumerate(models):
        label, color, dark = MODEL_STYLE[m]
        h = agg["models"][m]["headline"]["end_to_end"]
        med = [h[k][0] for k, _ in keys]
        lo = [h[k][0] - h[k][1] for k, _ in keys]
        hi = [h[k][2] - h[k][0] for k, _ in keys]
        xs = x + (j - 0.5) * w
        ax.bar(xs, med, w, color=color, edgecolor="white", linewidth=1.2, zorder=2, label=label,
               yerr=[lo, hi], capsize=3, error_kw=dict(ecolor=INK, lw=1, capthick=1))
        for xi, v, e in zip(xs, med, hi):
            ax.text(xi, v + e + 0.025, f"{v:.2f}", ha="center", fontsize=7.2, color=dark,
                    fontweight="bold")
    ax.axvline(2.5, color=GRID, lw=1.2, zorder=0)
    ax.set_xticks(x)
    ax.set_xticklabels([k[1] for k in keys], fontsize=8.2)
    ax.set_ylim(0, 1.12)
    ax.set_ylabel("end-to-end score\n(median; whiskers = min–max, 3 repeats)", fontsize=8.4)
    ax.set_title("a  Content fields, identity-aligned end-to-end", loc="left", fontsize=9.2)
    ax.legend(loc="upper left", bbox_to_anchor=(0.0, -0.2), frameon=False, fontsize=8.4, ncol=2)

    _clean(axfp)
    for j, m in enumerate(models):
        label, color, dark = MODEL_STYLE[m]
        med, lo, hi = agg["models"][m]["headline"]["end_to_end"]["fp"]
        axfp.bar([j], [med], 0.6, color=color, edgecolor="white", zorder=2,
                 yerr=[[med - lo], [hi - med]], capsize=3, error_kw=dict(ecolor=INK, lw=1))
        axfp.text(j, hi * 1.04 + 1, f"{med:.0f}", ha="center", fontsize=8, color=dark,
                  fontweight="bold")
    axfp.set_xticks(range(len(models)))
    axfp.set_xticklabels([MODEL_STYLE[m][0] for m in models], fontsize=8.2)
    top = max(agg["models"][m]["headline"]["end_to_end"]["fp"][2] for m in models)
    axfp.set_ylim(0, top * 1.25 + 5)
    axfp.set_title("b  False-positive cells", loc="left", fontsize=9.2)

    _clean(axs)
    studies = list(agg["models"][models[0]]["per_study"])
    for j, m in enumerate(models):
        label, color, dark = MODEL_STYLE[m]
        for i, study in enumerate(studies):
            runs = agg["models"][m]["per_study"].get(study, {}).get("runs", {})
            vals = [_metrics(r["end_to_end"]) for r in runs.values() if "end_to_end" in r]
            vals = [0.0 if v is None else v for v in vals]
            if not vals:
                continue
            xi = i + (j - 0.5) * 0.3
            axs.plot([xi, xi], [min(vals), max(vals)], color=color, lw=1.6, zorder=2)
            axs.scatter([xi], [st.median(vals)], s=34, color=color, edgecolor="white", zorder=3)
    axs.set_xticks(range(len(studies)))
    axs.set_xticklabels([s.replace("_", "\n", 1) for s in studies], fontsize=7.4)
    axs.set_ylim(-0.03, 1.0)
    axs.set_ylabel("end-to-end value F1", fontsize=8.4)
    axs.set_title("c  Per study (dot = median, line = min–max over repeats)", loc="left",
                  fontsize=9.2)
    fig.savefig(OUT / "fig2_model_compare.png")
    plt.close(fig)


# ---------------------------------------------------------------- Figure 3
def fig3_harmonization(harm: dict):
    from matplotlib.lines import Line2D
    rows = []
    for field in ("disease", "body_site", "treatment"):
        fd = harm["fields"].get(field)
        if not fd:
            continue
        for m in ("sonnet", "haiku"):
            md = fd["models"].get(m) or {}
            s = md.get("summary") or {}
            if md.get("runs_with_coded"):
                rows.append((field, m, {**s, "_runs": f"{md['runs_with_coded']}/{md['runs']}",
                                        "_coded_total": sum(pr["coded"] for pr in md["per_run"].values())}))
    fig, ax = plt.subplots(figsize=(8.0, 0.62 * len(rows) + 1.6))
    _clean(ax, grid_axis="x")
    for i, (field, m, s) in enumerate(reversed(rows)):
        label, color, dark = MODEL_STYLE[m]
        raw, exact, anyhit = s["raw_acc_coded"], s["exact_correct"], s["any_hit"]
        ax.plot([raw[0], exact[0]], [i, i], color=color, lw=2.2, alpha=0.4, zorder=1)
        for v, wc, kw in ((anyhit, MUTED, dict(s=52, marker="D", color="white", edgecolor=MUTED,
                                                linewidth=1.2)),
                          (raw, color, dict(s=62, color="white", edgecolor=color, linewidth=2)),
                          (exact, dark, dict(s=80, color=color, edgecolor="white", linewidth=1.2))):
            ax.plot([v[1], v[2]], [i + 0.12, i + 0.12], color=wc, lw=1.1, alpha=0.8, zorder=2)
            ax.scatter([v[0]], [i], zorder=3, **kw)
        ax.text(1.05, i, f"exact {exact[0]:.2f} · raw {raw[0]:.2f} · "
                         f"{s['_coded_total']} cells, {s['_runs']} runs",
                va="center", fontsize=7.6, color=dark)
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([f"{f} · {MODEL_STYLE[m][0]}" for f, m, _ in reversed(rows)], fontsize=8.6)
    ax.set_xlim(-0.03, 1.03)
    ax.set_ylim(-0.6, len(rows) - 0.4)
    ax.set_xlabel("fraction of coded cells (identity-matched; median over runs with coded cells, "
                  "lines = range)", fontsize=8.4)
    ax.legend(handles=[
        Line2D([0], [0], marker="o", color="none", markerfacecolor="white", markeredgecolor=INK,
               markersize=8, label="raw string match"),
        Line2D([0], [0], marker="o", color="none", markerfacecolor=INK, markeredgecolor="white",
               markersize=9, label="exact code-set match to curated ID"),
        Line2D([0], [0], marker="D", color="none", markerfacecolor="white", markeredgecolor=MUTED,
               markersize=7, label="any shared code (supplementary)"),
    ], loc="upper center", bbox_to_anchor=(0.45, -0.22), frameon=False, fontsize=8, ncol=3)
    fig.savefig(OUT / "fig3_harmonization.png")
    plt.close(fig)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", default=str(OUT.parent / "benchmarks/cmd_sonnet5/out_v2"))
    a = ap.parse_args()
    tree = pathlib.Path(a.tree)
    fig1_pipeline()
    fig2_model_compare(json.loads((tree / "aggregate_v2.json").read_text()))
    fig3_harmonization(json.loads((tree / "harmonization.json").read_text()))
    print("wrote:", *[p.name for p in sorted(OUT.glob("*.png"))])
