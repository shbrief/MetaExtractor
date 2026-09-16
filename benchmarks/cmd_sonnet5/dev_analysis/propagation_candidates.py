"""What would each candidate field recover if it were added to ``propagate_study_value``?

Offline, no model calls: replays the development check's own saved extractions
(``devcheck_haiku45/haiku_r1``) with one schema annotation flipped at a time, re-runs
the fan-out and the age rules, and re-scores with the same crosswalks.

Reports, per candidate field:

* the studies where a study-level value is currently blocked from reaching samples,
  and which fan-out rule blocks it;
* the correct / wrong cells that allowing it would add, and the pooled F1 it moves.

A field annotated ``unit_of`` (``age_unit``) is blocked by the unit rule before the
scope rule is reached, so the allowlist cannot recover it; that is reported separately.

  CMD_CURATION_DIR=... python dev_analysis/propagation_candidates.py
"""
from __future__ import annotations

import copy
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent
sys.path.insert(0, str(BENCH))
sys.path.insert(0, str(BENCH / "harmonize"))
import bench                                                  # noqa: E402
from bench_paths import AGE_RULES, SCHEMA, load_manifest      # noqa: E402
from crosswalk import Harmonizer                              # noqa: E402

from metaextractor import sample_rules as sr                  # noqa: E402
from metaextractor.output import ExtractionResult             # noqa: E402
from metaextractor.schema_loader import load_schema_file      # noqa: E402

RUN = HERE / "devcheck_haiku45" / "haiku_r1"
TMP = HERE / "devcheck_haiku45" / "_candidate_score.json"


def refanned(res: ExtractionResult, schema, rules) -> tuple[ExtractionResult, Counter]:
    """Re-run the fan-out and age rules on a copy (fan-out never overwrites filled cells)."""
    r = res.model_copy(deep=True)
    counts = sr.fan_out_fields_to_samples(r, schema)
    sr.normalize_age_bounds(r, rules, schema)
    return r, counts


def score(mf: dict, res: ExtractionResult, harm) -> dict:
    TMP.write_text(res.model_dump_json())
    r = bench.score_study(mf, TMP, harm)
    TMP.unlink(missing_ok=True)
    return r["end_to_end"]["content"]


def main() -> None:
    schema = load_schema_file(SCHEMA)
    by_name = {f.name: f for f in schema.fields}
    rules = sr.AgeBoundRules.from_json(AGE_RULES)
    harm = Harmonizer(HERE / "devcheck_haiku45" / "crosswalks")
    manifest = {m["study"]: m for m in load_manifest()}

    saved = {}
    for st in manifest:
        p = RUN / f"{st}.json"
        if p.exists():
            saved[st] = ExtractionResult.model_validate_json(p.read_text())

    # Which fields are blocked, where, and by which rule.
    blocked: dict[str, dict[str, str]] = {}
    for st, res in saved.items():
        if not (res.samples and res.fields):
            continue
        for name, fr in res.fields.items():
            f = by_name.get(name)
            if f is None or sr.is_nr(fr.value) or f.propagate_study_value:
                continue
            if not any(sr.is_nr(s.get(name)) for s in res.samples):
                continue
            if f.unit_of:
                rule = "unit_of (needs the record to carry its value)"
            elif f.scope != "sample":
                continue
            elif sr.is_multi_valued(fr.value):
                rule = "multi-valued cohort list"
            elif sr.is_aggregate(fr.value):
                rule = "aggregate statistic"
            elif res.subgroups or fr.by_subgroup:
                rule = "sample scope + subgroups declared"
            else:
                rule = "sample scope, not on the allowlist"
            blocked.setdefault(name, {})[st] = rule

    base = {st: score(manifest[st], saved[st], harm) for st in saved}
    def pooled(per: dict) -> dict:
        return {k: sum(c[k] for c in per.values()) for k in ("tp_correct", "tp_wrong", "fn", "fp")}
    b = pooled(base)
    print(f"baseline pooled: TPc {b['tp_correct']} TPw {b['tp_wrong']} FN {b['fn']} "
          f"FP {b['fp']} F1 {bench.metrics(b)['f1']:.4f}\n")

    rows = []
    for name, where in sorted(blocked.items()):
        f = by_name[name]
        if f.unit_of:
            rows.append((name, where, None))
            continue
        f.propagate_study_value = True
        per = {}
        for st in saved:
            r, _ = refanned(saved[st], schema, rules)
            per[st] = score(manifest[st], r, harm)
        f.propagate_study_value = False
        p = pooled(per)
        rows.append((name, where, {k: p[k] - b[k] for k in p} | {"f1": bench.metrics(p)["f1"]}))

    print(f"{'field':26} {'+TPc':>6} {'+TPw':>6} {'pooled F1':>10}  studies (blocking rule)")
    for name, where, d in rows:
        w = "; ".join(f"{st}" for st in where)
        if d is None:
            print(f"{name:26} {'n/a':>6} {'n/a':>6} {'n/a':>10}  {w}  [{list(where.values())[0]}]")
        else:
            print(f"{name:26} {d['tp_correct']:>+6} {d['tp_wrong']:>+6} {d['f1']:>10.4f}  {w}")
    print(f"\n{'(baseline)':26} {'':>6} {'':>6} {bench.metrics(b)['f1']:>10.4f}")

    # Everything the allowlist could take, together.
    flip = [by_name[n] for n, w, d in rows if d is not None]
    for f in flip:
        f.propagate_study_value = True
    per = {st: score(manifest[st], refanned(saved[st], schema, rules)[0], harm) for st in saved}
    p = pooled(per)
    print(f"{'ALL candidates together':26} {p['tp_correct']-b['tp_correct']:>+6} "
          f"{p['tp_wrong']-b['tp_wrong']:>+6} {bench.metrics(p)['f1']:>10.4f}")


if __name__ == "__main__":
    main()
