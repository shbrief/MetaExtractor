"""Development-set check at revision-v4 HEAD vs the out_v3 Haiku repeats.

Writes ``dev_analysis/devcheck_haiku45/COMPARISON.md``: per-study record counts and
content F1 for both joins, pooled F1, and a per-field account of which correct cells
were gained and lost. For every lost/gained field the gold column's number of distinct
values in that study is reported, which separates credit that blanket study-to-sample
propagation used to supply (gold constant within the study) from credit that required
per-sample evidence.

  CMD_CURATION_DIR=... python dev_analysis/compare_devcheck_out_v3.py
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent
sys.path.insert(0, str(BENCH))
from bench import metrics                                    # noqa: E402
from bench_paths import gold_path, load_manifest             # noqa: E402

DEV = HERE / "devcheck_haiku45" / "haiku_r1"
V3 = [BENCH / "out_v3" / f"haiku_r{k}" for k in (1, 2, 3)]
CONTENT = "content"


def per_study(run: Path) -> dict[str, dict]:
    return {s["study"]: s for s in json.loads((run / "summary.json").read_text())["per_study"]}


def f1(study: dict, join: str) -> float | None:
    c = study[join][CONTENT]
    return metrics(c)["f1"] if sum(c[k] for k in ("tp_correct", "tp_wrong", "fn", "fp")) else None


def pooled(run: dict[str, dict], join: str) -> tuple[float, dict]:
    t = {k: sum(s[join][CONTENT][k] for s in run.values())
         for k in ("tp_correct", "tp_wrong", "fn", "fp")}
    return metrics(t)["f1"], t


def gold_distinct(mani: dict, study: str, field: str) -> int:
    rows = csv.DictReader(gold_path(mani[study]).open(), delimiter="\t")
    vals = {(r.get(field) or "").strip() for r in rows}
    return len({v for v in vals if v and v.lower() not in ("na", "nan")})


def fmt(x: float | None) -> str:
    return f"{x:.3f}" if isinstance(x, float) else "–"


def main() -> None:
    mani = {m["study"]: m for m in load_manifest()}
    v3 = [per_study(r) for r in V3]
    dev = per_study(DEV)
    out = ["# Development-set check (commit 852de78) vs out_v3 Haiku repeats", "",
           "One Haiku 4.5 repeat on the ten development studies, scored post-harmonization",
           "against each tree's own crosswalks. out_v3 columns are its three Haiku repeats.", "",
           "## Per study", "",
           "| study | records v3 (r1/r2/r3) | records dev | matched v3 | matched dev "
           "| F1 all-curated v3 | F1 all-curated dev | F1 matched v3 | F1 matched dev |",
           "|---|---|---|---|---|---|---|---|---|"]
    for st in dev:
        j = lambda fn: "/".join(str(fn(r[st])) for r in v3)
        out.append(
            f"| {st} | {j(lambda s: s['n_extracted'])} | {dev[st]['n_extracted']} "
            f"| {j(lambda s: s['alignment']['matched'])} | {dev[st]['alignment']['matched']} "
            f"| {'/'.join(fmt(f1(r[st], 'end_to_end')) for r in v3)} | {fmt(f1(dev[st], 'end_to_end'))} "
            f"| {'/'.join(fmt(f1(r[st], 'conditional')) for r in v3)} | {fmt(f1(dev[st], 'conditional'))} |")

    out += ["", "## Pooled over the ten studies", "",
            "| run | join | TPc | TPw | FN | FP | F1 |", "|---|---|---|---|---|---|---|"]
    for join in ("end_to_end", "conditional"):
        label = "all curated" if join == "end_to_end" else "matched"
        for k, r in zip((1, 2, 3), v3):
            f, t = pooled(r, join)
            out.append(f"| out_v3 haiku_r{k} | {label} | {t['tp_correct']} | {t['tp_wrong']} "
                       f"| {t['fn']} | {t['fp']} | {f:.4f} |")
        f, t = pooled(dev, join)
        out.append(f"| **devcheck** | {label} | {t['tp_correct']} | {t['tp_wrong']} "
                   f"| {t['fn']} | {t['fp']} | **{f:.4f}** |")

    # Per-field account. Repeats where the extraction failed carry no signal, so they are
    # excluded; a field whose surviving repeats disagree is model variance, not a rule change.
    import statistics
    gained = lost_consistent = lost_variable = 0
    rows = []
    for st in dev:
        ok = [r for r in v3 if not r[st].get("extraction_failed")]
        for field, cell in dev[st]["fields_end_to_end"].items():
            vals = [(r[st]["fields_end_to_end"].get(field) or {}).get("tp_correct", 0) for r in ok]
            if not vals:
                continue
            ref = int(statistics.median(vals))
            cur = cell.get("tp_correct", 0)
            if ref == cur and len(set(vals)) == 1:
                continue
            varies = len(set(vals)) > 1
            nd = gold_distinct(mani, st, field)
            rows.append((st, field, vals, ref, cur, nd, varies))
            if cur > ref:
                gained += cur - ref
            elif cur < ref:
                if varies:
                    lost_variable += ref - cur
                else:
                    lost_consistent += ref - cur
    out += ["", "## Correct cells gained and lost, by field", "",
            "`out_v3 TPc` lists the repeats whose extraction did not fail; the comparison uses "
            "their median. Where those repeats disagree the difference is repeat-to-repeat model "
            "variance, not a consequence of the rule changes, and is counted separately. "
            "`gold distinct` is how many distinct values the field takes across the study's "
            "curated rows; 1 means a single study-wide value, which blanket study-to-sample "
            "propagation used to supply without per-sample evidence.", "",
            "| study | field | out_v3 TPc (completed repeats) | median | TPc dev | gold distinct | v3 repeats agree |",
            "|---|---|---|---|---|---|---|"]
    for st, field, vals, ref, cur, nd, varies in sorted(rows, key=lambda r: (r[0], r[1])):
        out.append(f"| {st} | {field} | {'/'.join(map(str, vals))} | {ref} | {cur} "
                   f"| {nd}{' (constant)' if nd == 1 else ''} | {'no' if varies else 'yes'} |")
    out += ["", f"- correct cells **gained**: {gained}",
            f"- correct cells **lost** where the out_v3 repeats agreed (attributable to the rule changes): {lost_consistent}",
            f"- correct cells **lost** where the out_v3 repeats disagreed (model variance): {lost_variable}", ""]
    (DEV.parent / "COMPARISON.md").write_text("\n".join(out))
    print(f"wrote {DEV.parent / 'COMPARISON.md'}")


if __name__ == "__main__":
    main()
