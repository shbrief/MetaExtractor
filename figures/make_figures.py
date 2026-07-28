#!/usr/bin/env python
"""Generate manuscript figures for MANUSCRIPT.md.

Static PNGs (portable across GitHub markdown + pandoc HTML). CVD-safe Okabe-Ito
palette: Sonnet 5 = blue #0072B2, Haiku 4.5 = orange #E69F00, gold = gray.
All numbers are transcribed from the manuscript's own result tables.
"""
from __future__ import annotations
import pathlib
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
    fig, ax = plt.subplots(figsize=(8.4, 6.4))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")

    def box(x, y, w, h, text, fill, edge, fs=8.6, bold=False):
        ax.add_patch(FancyBboxPatch(
            (x, y), w, h, boxstyle="round,pad=0.6,rounding_size=1.6",
            linewidth=1.2, edgecolor=edge, facecolor=fill, zorder=2))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
                fontsize=fs, color=INK, zorder=3,
                fontweight="bold" if bold else "normal", linespacing=1.25)
        return (x + w / 2, y, x + w / 2, y + h)  # cx, ybot, cx, ytop

    def arrow(p_from, p_to, color=MUTED, style="-|>"):
        ax.add_patch(FancyArrowPatch(
            p_from, p_to, arrowstyle=style, mutation_scale=13,
            linewidth=1.3, color=color, zorder=1,
            shrinkA=1, shrinkB=1))

    # Inputs
    b_paper = box(4, 88, 40, 9, "Paper\n(PMID · DOI · PDF · text)", IO, IO_E, bold=True)
    b_schema = box(56, 88, 40, 9, "Target schema\n(JSON · YAML · LinkML)", IO, IO_E, bold=True)

    # Deterministic spine
    b_fetch = box(4, 73, 40, 9,
                  "Document retrieval\nPMC→EuropePMC→abstract + supp.\n(retry · S3 fallback)",
                  DET, DET_E)
    b_adapt = box(56, 73, 40, 9,
                  "Schema adaptation\ntyped fields · enum downgrade\n(dynamic ontology→free text)",
                  DET, DET_E)

    # Merge bar (conceptual): both feed the extraction stage
    y_split = 60
    # Route A — LLM batch extraction
    b_llmx = box(4, y_split, 40, 9,
                 "LLM field-batch extraction\n≤30 fields/call · cached prompt\nextraction contract + provenance",
                 LLM, LLM_E)
    # Route B — deterministic table path with one bounded LLM plan
    b_gate = box(56, y_split, 40, 8,
                 "Supp.-table path: relevance gate\n· feature-matrix reject", DET, DET_E, fs=8.2)
    b_plan = box(56, 48.5, 40, 8,
                 "Bounded LLM plan (structure only:\nheaders · id cols · melt indices)", LLM, LLM_E, fs=8.2)
    b_exec = box(56, 37, 40, 8,
                 "Python execute (verbatim cells)\n· column map · join on shared key", DET, DET_E, fs=8.2)

    # optional discovery
    b_disc = box(4, 47.5, 40, 8,
                 "opt. LLM sample-discovery\n(enumerate stable sample IDs)", LLM, LLM_E, fs=8.2)

    # Validation + output
    b_valid = box(30, 23, 40, 8,
                  "Pydantic validation\n(faithfulness · schema conformance)", DET, DET_E)
    b_out = box(30, 8, 40, 9,
                "Output: JSON (per-sample rows,\nprovenance, table log, cost) + CSV", IO, IO_E, bold=True)

    # arrows
    arrow((b_paper[0], b_paper[1]), (b_fetch[0], b_fetch[3]))
    arrow((b_schema[0], b_schema[1]), (b_adapt[0], b_adapt[3]))
    # fetch + adapt into both routes
    arrow((b_fetch[0], b_fetch[1]), (b_llmx[0], b_llmx[3]))
    arrow((b_adapt[0], b_adapt[1]), (b_gate[0], b_gate[3]))
    arrow((b_llmx[0], b_llmx[1]), (b_disc[0], b_disc[3]))
    # table path chain
    arrow((b_gate[0], b_gate[1]), (b_plan[0], b_plan[3]))
    arrow((b_plan[0], b_plan[1]), (b_exec[0], b_exec[3]))
    # into validation
    arrow((b_disc[0], b_disc[1]), (b_valid[0] - 6, b_valid[3]))
    arrow((b_exec[0], b_exec[1]), (b_valid[0] + 6, b_valid[3]))
    arrow((b_valid[0], b_valid[1]), (b_out[0], b_out[3]))

    # legend
    leg_y = 99.4
    for i, (fc, ec, lab) in enumerate([
        (DET, DET_E, "deterministic step"),
        (LLM, LLM_E, "constrained LLM call"),
        (IO, IO_E, "input / output")]):
        x = 4 + i * 30
        ax.add_patch(FancyBboxPatch((x, leg_y - 1.4), 2.6, 2.4,
                     boxstyle="round,pad=0.1,rounding_size=0.5",
                     linewidth=1.1, edgecolor=ec, facecolor=fc))
        ax.text(x + 3.4, leg_y - 0.2, lab, fontsize=8.2, va="center", color=INK)

    fig.savefig(OUT / "fig1_pipeline.png")
    plt.close(fig)
    mpl.rcParams["font.family"] = prev_family


# ---------------------------------------------------------------- Figure 2
def fig3_model_compare():
    # Refined pipeline, positional scoring (out_ms_refined), median [min-max] / 3 repeats.
    metrics = ["Precision", "Recall", "F1", "value-acc"]
    son_med = [0.990, 0.591, 0.741, 0.609]
    son_lo = [0.960, 0.569, 0.715, 0.593]
    son_hi = [0.993, 0.593, 0.741, 0.623]
    hai_med = [0.901, 0.660, 0.762, 0.512]
    hai_lo = [0.898, 0.640, 0.748, 0.480]
    hai_hi = [0.905, 0.688, 0.782, 0.527]

    fig, (ax, axfp) = plt.subplots(
        1, 2, figsize=(8.4, 4.0), gridspec_kw={"width_ratios": [3.3, 1]})

    _clean(ax, grid_axis="y")
    import numpy as np
    x = np.arange(len(metrics))
    w = 0.36

    def err(lo, med, hi):
        return [[m - l for m, l in zip(med, lo)], [h - m for m, h in zip(med, hi)]]

    ax.bar(x - w / 2, son_med, w, color=SONNET, edgecolor="white", linewidth=1.5,
           zorder=2, label="Sonnet 5",
           yerr=err(son_lo, son_med, son_hi), capsize=3,
           error_kw=dict(ecolor=INK, lw=1, capthick=1))
    ax.bar(x + w / 2, hai_med, w, color=HAIKU, edgecolor="white", linewidth=1.5,
           zorder=2, label="Haiku 4.5",
           yerr=err(hai_lo, hai_med, hai_hi), capsize=3,
           error_kw=dict(ecolor=INK, lw=1, capthick=1))
    for xi, v in zip(x - w / 2, son_med):
        ax.text(xi, v + 0.03, f"{v:.2f}", ha="center", fontsize=7.6, color=SONNET, fontweight="bold")
    for xi, v in zip(x + w / 2, hai_med):
        ax.text(xi, v + 0.03, f"{v:.2f}", ha="center", fontsize=7.6, color="#a9720f", fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(metrics)
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("score  (median · whiskers = min–max of 3 repeats)")
    ax.legend(loc="upper right", frameon=False, fontsize=8.6, ncol=2,
              columnspacing=1.0, handlelength=1.1)

    # FP panel — log scale, cannot share the 0–1 axis
    _clean(axfp, grid_axis="y")
    axfp.bar([0], [51], 0.6, color=SONNET, edgecolor="white", linewidth=1.5, zorder=2)
    axfp.bar([1], [784], 0.6, color=HAIKU, edgecolor="white", linewidth=1.5, zorder=2)
    axfp.set_yscale("log")
    axfp.set_ylim(1, 2000)
    axfp.text(0, 51 * 1.3, "51", ha="center", fontsize=8.2, color=SONNET, fontweight="bold")
    axfp.text(1, 784 * 1.3, "784", ha="center", fontsize=8.2, color="#a9720f", fontweight="bold")
    axfp.set_xticks([0, 1])
    axfp.set_xticklabels(["Sonnet", "Haiku"], fontsize=8.4)
    axfp.set_title("False positives\n(log scale)", fontsize=9)
    fig.savefig(OUT / "fig2_model_compare.png")
    plt.close(fig)


# ---------------------------------------------------------------- Figure 3
def fig4_harmonization():
    # dumbbell: raw value-acc -> correct_acc (=1.00) per model/field
    rows = [
        ("body_site · Haiku 4.5", 0.758, 1.00, HAIKU),
        ("body_site · Sonnet 5", 0.638, 1.00, SONNET),
        ("disease · Haiku 4.5", 0.310, 1.00, HAIKU),
        ("disease · Sonnet 5", 0.505, 1.00, SONNET),
    ]
    fig, ax = plt.subplots(figsize=(7.8, 3.7))
    _clean(ax, grid_axis="x")
    for i, (lab, raw, corr, col) in enumerate(rows):
        ax.plot([raw, corr], [i, i], color=col, lw=2.4, alpha=0.45, zorder=1)
        ax.scatter([raw], [i], s=70, color="white", edgecolor=col, linewidth=2, zorder=3)
        ax.scatter([corr], [i], s=90, color=col, edgecolor="white", linewidth=1.4, zorder=3)
        ax.text(raw - 0.02, i, f"{raw:.2f}", ha="right", va="center", fontsize=7.8, color=MUTED)
        ax.text(corr + 0.015, i, "1.00", ha="left", va="center", fontsize=7.8,
                color=col, fontweight="bold")
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r[0] for r in rows], fontsize=8.8)
    ax.set_xlim(0, 1.12)
    ax.set_xlabel("accuracy on TP cells")
    ax.set_ylim(-0.6, len(rows) - 0.4)
    # annotate the two endpoints once
    ax.text(0.30, len(rows) - 0.15, "raw string match", fontsize=8, color=MUTED,
            ha="center", style="italic")
    ax.text(1.00, len(rows) - 0.15, "after OntologyMapper\n(vs gold's own IDs)",
            fontsize=8, color=INK, ha="center", style="italic")
    from matplotlib.lines import Line2D
    ax.legend(handles=[
        Line2D([0], [0], marker="o", color="white", markerfacecolor="white",
               markeredgecolor=INK, markersize=8, label="raw value-acc"),
        Line2D([0], [0], marker="o", color="white", markerfacecolor=INK,
               markeredgecolor="white", markersize=9, label="correct_acc"),
    ], loc="lower right", frameon=False, fontsize=8.2)
    fig.savefig(OUT / "fig3_harmonization.png")
    plt.close(fig)


if __name__ == "__main__":
    fig1_pipeline()
    fig3_model_compare()
    fig4_harmonization()
    print("wrote:", *[p.name for p in sorted(OUT.glob("*.png"))])
