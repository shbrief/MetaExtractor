#!/usr/bin/env python3
"""Decide whether a refactor's benchmark re-run is acceptable.

The plan's gate for a behaviour-preserving change to the extraction path has two
criteria, and this applies both to a fresh tree against the reference one.

1. **Scores.** The reference tree's three repeats show how much the *same* code
   varies under sampling, and that spread is the yardstick -- a change that stays
   within it has not been shown to alter anything.

   Two tests, because requiring every new repeat inside a three-point min-max is
   too tight to be meaningful: sampling alone would breach it. So:

   * the new tree's **median** must fall inside the reference range, and
   * the two ranges must **overlap**.

   A failure on either is a signal; a failure on both is strong. The per-repeat
   numbers are printed regardless, because with n=3 a reader should see the
   points and not only the verdict.

2. **Prompt caching survived.** Aggregate ``cache_read_input_tokens`` against
   ``cache_creation_input_tokens``. A collapse in the read/write ratio is the
   single number that proves a lost cache breakpoint, and it is already in
   run-meta -- far cheaper to read than to re-derive. With the paper block cached
   and a schema batched into N calls, one call writes the prefix and N-1 read it,
   so the ratio should be near N-1 and must not fall toward zero.

Usage::

    python benchmarks/cmd_sonnet5/accept_refactor.py --new out_v5 --ref out_v4
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _prf(c: dict) -> tuple[float | None, float | None, float | None]:
    """Precision, recall, F1 from TPc/TPw/FN/FP counts."""
    tpc, tpw = c.get("tp_correct", 0), c.get("tp_wrong", 0)
    fn, fp = c.get("fn", 0), c.get("fp", 0)
    p = tpc / (tpc + tpw + fp) if (tpc + tpw + fp) else None
    r = tpc / (tpc + tpw + fn) if (tpc + tpw + fn) else None
    f = (2 * p * r / (p + r)) if (p and r) else (0.0 if (p is not None and r is not None) else None)
    return p, r, f


def per_repeat_scores(tree: Path) -> dict[str, dict[str, list[float]]]:
    """``{join: {model: [f1 per repeat]}}`` pooled over studies, from summary.json."""
    out: dict[str, dict[str, list[float]]] = {"end_to_end": {}, "conditional": {}}
    for summary in sorted(tree.glob("*_r*/summary.json")):
        model = summary.parent.name.rsplit("_r", 1)[0]
        payload = json.loads(summary.read_text())
        for join in out:
            pooled: dict[str, int] = {}
            for study in payload.get("per_study", []):
                for k, v in (study.get(join) or {}).get("content", {}).items():
                    pooled[k] = pooled.get(k, 0) + v
            _, _, f1 = _prf(pooled)
            if f1 is not None:
                out[join].setdefault(model, []).append(round(f1, 4))
    return out


def cache_ratio(tree: Path) -> dict[str, dict[str, int | float]]:
    """Aggregate cache write/read tokens per model, from the per-attempt run-metas."""
    out: dict[str, dict[str, int | float]] = {}
    for meta in sorted(tree.glob("*_r*/*.meta.json")):
        if ".attempt" in meta.name:
            continue
        model = meta.parent.name.rsplit("_r", 1)[0]
        try:
            u = (json.loads(meta.read_text()).get("usage") or {})
        except (OSError, json.JSONDecodeError):
            continue
        d = out.setdefault(model, {"cache_creation_input_tokens": 0,
                                   "cache_read_input_tokens": 0,
                                   "input_tokens": 0, "n_calls": 0})
        for k in d:
            d[k] += u.get(k, 0) or 0
    for d in out.values():
        w = d["cache_creation_input_tokens"]
        d["read_per_write"] = round(d["cache_read_input_tokens"] / w, 3) if w else None
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--new", required=True, help="the tree under test, e.g. out_v5")
    ap.add_argument("--ref", default="out_v4", help="the reference tree (default out_v4)")
    args = ap.parse_args()

    new, ref = HERE / args.new, HERE / args.ref
    for t in (new, ref):
        if not t.is_dir():
            raise SystemExit(f"no tree {t}")

    sn, sr = per_repeat_scores(new), per_repeat_scores(ref)
    cn, cr = cache_ratio(new), cache_ratio(ref)

    print(f"# Acceptance check — `{args.new}` against `{args.ref}`\n")
    print("## 1. Scores\n")
    print(f"| join | model | {args.ref} repeats | {args.ref} range "
          f"| {args.new} repeats | {args.new} median | ok? |")
    print("|---|---|---|---|---|--:|:-:|")
    failures = []
    for join, title in (("end_to_end", "all curated"), ("conditional", "matched")):
        for model in sorted(set(sr[join]) | set(sn[join])):
            rv, nv = sr[join].get(model, []), sn[join].get(model, [])
            if not rv or not nv:
                print(f"| {title} | {model} | {rv or '—'} |  | {nv or '—'} |  | n/a |")
                continue
            lo, hi = min(rv), max(rv)
            nlo, nhi = min(nv), max(nv)
            med = statistics.median(nv)
            median_inside = lo <= med <= hi
            overlaps = nlo <= hi and lo <= nhi
            if not (median_inside and overlaps):
                failures.append((title, model, nv, (lo, hi), med,
                                 median_inside, overlaps))
            verdict = ("yes" if median_inside and overlaps
                       else "median" if overlaps
                       else "NO")
            print(f"| {title} | {model} | {rv} | {lo:.3f}–{hi:.3f} | {nv} "
                  f"| {med:.3f} | {verdict} |")
    print()
    print(f"`ok?` is **yes** when the {args.new} median sits inside the {args.ref} "
          f"range *and* the ranges overlap; **median** when only the ranges "
          f"overlap; **NO** when they are disjoint. With three repeats a side, "
          f"treat this as a direction and read the points.\n")

    print("## 2. Prompt caching\n")
    print("| model | tree | cache_write | cache_read | read/write |")
    print("|---|---|--:|--:|--:|")
    cache_warn = []
    for model in sorted(set(cn) | set(cr)):
        for label, d in ((args.ref, cr.get(model)), (args.new, cn.get(model))):
            if not d:
                continue
            print(f"| {model} | {label} | {d['cache_creation_input_tokens']:,} "
                  f"| {d['cache_read_input_tokens']:,} | "
                  f"{d['read_per_write'] if d['read_per_write'] is not None else '—'} |")
        a, b = cr.get(model), cn.get(model)
        if a and b and a["read_per_write"] and b["read_per_write"] is not None:
            # A real collapse, not sampling noise: more than a third below the
            # reference ratio means prefixes stopped being reused.
            if b["read_per_write"] < a["read_per_write"] * 0.67:
                cache_warn.append((model, a["read_per_write"], b["read_per_write"]))
    print()

    print("## Verdict\n")
    ok = True
    if failures:
        ok = False
        print("**Scores: FAIL.** Outside the reference repeat spread:\n")
        for title, model, nv, (lo, hi), med, _median_inside, ov in failures:
            why = ("ranges disjoint" if not ov
                   else f"median {med:.3f} outside {lo:.3f}–{hi:.3f}")
            print(f"- {title} / {model}: {nv} against {lo:.3f}–{hi:.3f} ({why})")
        print("\nBisect before merging.\n")
    else:
        print("**Scores: PASS** — the median sits inside the reference spread and "
              "the ranges overlap, for every join and model.\n")
    if cache_warn:
        ok = False
        print("**Caching: FAIL.** The read/write ratio collapsed, which means a "
              "cache breakpoint was lost:\n")
        for model, a, b in cache_warn:
            print(f"- {model}: {a} → {b}")
    else:
        print("**Caching: PASS** — prefixes are still being reused at the "
              "reference rate.\n")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
