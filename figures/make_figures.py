#!/usr/bin/env python
"""Generate manuscript figures for MANUSCRIPT.md.

Static PNGs (portable across GitHub markdown + pandoc HTML). CVD-safe Okabe-Ito
palette: Sonnet 5 = blue #0072B2, Haiku 4.5 = orange #E69F00, gold = gray.

Figures 2 and 3 are generated from the scoring outputs of a run tree — no
numbers are transcribed by hand:

  TREE/aggregate_v2.json   (benchmarks/cmd_sonnet5/aggregate.py)

All scores are post-harmonization (values compared after MetaHarmonizer mapping).

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


def _f1(c):
    tp = c["tp_correct"] + c["tp_wrong"]
    p = c["tp_correct"] / (tp + c["fp"]) if tp + c["fp"] else None
    r = c["tp_correct"] / (tp + c["fn"]) if tp + c["fn"] else None
    return 2 * p * r / (p + r) if p is not None and r is not None and p + r else None


SCORES = (("end_to_end", "Score all curated"), ("conditional", "Score matched"))
KEYS = (("precision", "precision"), ("recall", "recall"), ("f1", "F1"))


def _bars(ax, agg, models, join, title):
    import numpy as np
    _clean(ax)
    x = np.arange(len(KEYS))
    w = 0.36
    for j, m in enumerate(models):
        label, color, dark = MODEL_STYLE[m]
        h = agg["models"][m]["headline"][join]
        med = [h[k][0] or 0.0 for k, _ in KEYS]
        lo = [(h[k][0] or 0.0) - (h[k][1] or 0.0) for k, _ in KEYS]
        hi = [(h[k][2] or 0.0) - (h[k][0] or 0.0) for k, _ in KEYS]
        xs = x + (j - 0.5) * w
        ax.bar(xs, med, w, color=color, edgecolor="white", linewidth=1.2, zorder=2, label=label,
               yerr=[lo, hi], capsize=3, error_kw=dict(ecolor=INK, lw=1, capthick=1))
        for xi, v, e in zip(xs, med, hi):
            ax.text(xi, v + e + 0.025, f"{v:.2f}", ha="center", fontsize=7.2, color=dark,
                    fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels([k[1] for k in KEYS], fontsize=8.4)
    ax.set_ylim(0, 1.12)
    ax.set_title(title, loc="left", fontsize=9.2)


# ---------------------------------------------------------------- Figure 2
def fig2_model_compare(agg: dict):
    models = [m for m in ("sonnet", "haiku") if m in agg["models"]]
    fig = plt.figure(figsize=(9.0, 6.6))
    gs = fig.add_gridspec(2, 2, height_ratios=[1, 1.05], hspace=0.55, wspace=0.22)
    ax_all, ax_m, axs = fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1]), fig.add_subplot(gs[1, :])
    _bars(ax_all, agg, models, "end_to_end", "a  Score all curated (1,089 samples)")
    _bars(ax_m, agg, models, "conditional", "b  Score matched (identifier-linked samples)")
    ax_all.set_ylabel("post-harmonization score\n(median; whiskers = min–max, 3 repeats)",
                      fontsize=8.4)
    ax_all.legend(loc="upper left", bbox_to_anchor=(0.0, -0.14), frameon=False, fontsize=8.4, ncol=2)

    _clean(axs)
    studies = list(agg["models"][models[0]]["per_study"])
    for j, m in enumerate(models):
        label, color, dark = MODEL_STYLE[m]
        for i, study in enumerate(studies):
            runs = agg["models"][m]["per_study"].get(study, {}).get("runs", {})
            vals = [_f1(r["end_to_end"]) for r in runs.values() if "end_to_end" in r]
            vals = [0.0 if v is None else v for v in vals]
            if not vals:
                continue
            xi = i + (j - 0.5) * 0.3
            axs.plot([xi, xi], [min(vals), max(vals)], color=color, lw=1.6, zorder=2)
            axs.scatter([xi], [st.median(vals)], s=34, color=color, edgecolor="white", zorder=3)
    axs.set_xticks(range(len(studies)))
    axs.set_xticklabels([s.replace("_", "\n", 1) for s in studies], fontsize=7.4)
    axs.set_ylim(-0.03, 1.0)
    axs.set_ylabel("F1, all curated samples", fontsize=8.4)
    axs.set_title("c  Per study (dot = median, line = min–max over repeats)", loc="left",
                  fontsize=9.2)
    fig.savefig(OUT / "fig2_model_compare.png")
    plt.close(fig)


# ---------------------------------------------------------------- Figure 3
def fig3_harmonization(agg: dict):
    """F1 of the harmonized fields, both scores."""
    models = [m for m in ("sonnet", "haiku") if m in agg["models"]]
    fields = sorted({f for m in models for f in agg["models"][m].get("per_field", {})})
    if not fields:
        return
    fig, axes = plt.subplots(1, 2, figsize=(9.0, 0.7 * len(fields) * len(models) + 1.8),
                             sharey=True)
    for ax, (join, title) in zip(axes, SCORES):
        _clean(ax, grid_axis="x")
        labels, i = [], 0
        for f in fields:
            for m in models:
                label, color, dark = MODEL_STYLE[m]
                h = agg["models"][m].get("per_field", {}).get(f, {}).get(join)
                labels.append(f"{f} · {label}")
                if h and h["f1"]:
                    med, lo, hi = h["f1"]
                    ax.plot([lo, hi], [i, i], color=color, lw=2, alpha=0.6, zorder=2)
                    ax.scatter([med], [i], s=70, color=color, edgecolor="white", zorder=3)
                    ax.text(1.04, i, f"{med:.2f}", va="center", fontsize=7.8, color=dark)
                else:
                    ax.text(0.01, i, "no correct cells", va="center", fontsize=7.6, color=MUTED)
                i += 1
        ax.set_yticks(range(len(labels)))
        ax.set_yticklabels(labels, fontsize=8.2)
        ax.set_xlim(-0.03, 1.03)
        ax.set_ylim(len(labels) - 0.4, -0.6)
        ax.set_xlabel("F1 (median; line = min–max over repeats)", fontsize=8.4)
        ax.set_title(title, loc="left", fontsize=9.2)
    fig.savefig(OUT / "fig3_harmonization.png")
    plt.close(fig)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", default=str(OUT.parent / "benchmarks/cmd_sonnet5/out_v2"))
    a = ap.parse_args()
    tree = pathlib.Path(a.tree)
    fig1_pipeline()
    fig2_model_compare(json.loads((tree / "aggregate_v2.json").read_text()))
    fig3_harmonization(json.loads((tree / "aggregate_v2.json").read_text()))
    print("wrote:", *[p.name for p in sorted(OUT.glob("*.png"))])
