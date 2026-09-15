"""Offline comparison of fan-out rule options on the development extractions (out_v3).

Used to choose the propagation rule for bench-v4 (option C, "C_allowlist_plus_range",
was adopted as schema annotation propagate_study_value; the age range-pair block in
C is moot because no age field is annotated). For each extraction: strip cells written by
fan-out and the age rule, re-apply a rule option, then score with bench.score_study
against out_v3/crosswalks. No API calls; out_v3 is read only. With the options
v3_asis current, per-field cell counts of current reproduce out_v3 exactly.

  CMD_CURATION_DIR=... python dev_analysis/fanout_options.py OUTDIR v3_asis current \
      D_range_pair_only D2_range_pair_group_guard C_allowlist_plus_range A_no_sample_scope

Note: the options are implemented in this script's own ``fan_out`` (``current`` is the
out_v3 rule) and ignore the schema's ``propagate_study_value`` annotation; option C's
allowlist is ``UNIFORM_OK``.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

BENCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BENCH))
sys.path.insert(0, str(BENCH / "harmonize"))
import bench  # noqa: E402
from bench_paths import AGE_RULES, SCHEMA, load_manifest  # noqa: E402
from crosswalk import Harmonizer  # noqa: E402

from metaextractor import sample_rules as sr  # noqa: E402
from metaextractor.output import ExtractionResult  # noqa: E402
from metaextractor.schema_loader import load_schema_file  # noqa: E402

OUT = Path(sys.argv[1])
SRC = BENCH / "out_v3"
schema = load_schema_file(SCHEMA)
rules = sr.AgeBoundRules.from_json(AGE_RULES)
SCOPE = {f.name: f.scope for f in schema.fields}
UNIFORM_OK = {"body_site"}  # option C allowlist (sample-scoped fields allowed to propagate)


def strip(result: ExtractionResult) -> None:
    for s, p in zip(result.samples, result.sample_provenance):
        for f, src in list(p.items()):
            if src.startswith(("study_fanout", "subgroup_fanout", "age_rule")):
                s.pop(f, None)
                del p[f]


def range_pair(result: ExtractionResult) -> bool:
    lo, hi = result.fields.get("age_min"), result.fields.get("age_max")
    a, b = (sr._num(lo.value) if lo else None), (sr._num(hi.value) if hi else None)
    return a is not None and b is not None and a != b


def fan_out(result: ExtractionResult, option: str) -> Counter:
    """sr.fan_out_fields_to_samples with the option's extra blocks, counted per field."""
    counts: Counter = Counter()
    if not result.samples or not result.fields:
        return counts
    sr.ensure_provenance(result)
    sub = {sr._normalize_subgroup(s): s for s in (result.subgroups or [])}
    pair = range_pair(result)
    for sample, prov in zip(result.samples, result.sample_provenance):
        found = {sub[sr._normalize_subgroup(v)] for v in sample.values()
                 if isinstance(v, str) and sr._normalize_subgroup(v) in sub}
        sg = next(iter(found)) if len(found) == 1 else None
        for fname, fr in result.fields.items():
            if not sr.is_nr(sample.get(fname)):
                continue
            fscope = SCOPE.get(fname)
            if sg and fr.by_subgroup and sg in fr.by_subgroup and not sr.is_nr(fr.by_subgroup[sg]):
                v = fr.by_subgroup[sg]
                if fscope != "study" and (sr.is_multi_valued(v) or sr.is_aggregate(v)):
                    counts[(fname, "blocked")] += 1
                    continue
                sample[fname] = sr.stringify(v); prov[fname] = f"subgroup_fanout:{sg}"
                counts[(fname, "propagated")] += 1
                continue
            v = fr.value
            if sr.is_nr(v):
                continue
            blocked = False
            if fscope != "study":
                blocked = (sr.is_multi_valued(v) or sr.is_aggregate(v)
                           or (fscope == "sample" and (result.subgroups or fr.by_subgroup)))
            if not blocked and fscope == "sample":
                if option == "A_no_sample_scope":
                    blocked = True
                elif option == "C_allowlist_plus_range":
                    blocked = fname not in UNIFORM_OK or (fname in ("age_min", "age_max") and pair)
                elif option in ("D_range_pair_only", "D2_range_pair_group_guard"):
                    blocked = fname in ("age_min", "age_max") and pair
            if blocked:
                counts[(fname, "blocked")] += 1
                continue
            sample[fname] = sr.stringify(v); prov[fname] = "study_fanout"
            counts[(fname, "propagated")] += 1
    return counts


def age_rules_ignoring_propagated_group(res: ExtractionResult) -> None:
    """Age rule, but a propagated age_group does not define a record's bounds."""
    hidden = []
    for s, p in zip(res.samples, res.sample_provenance):
        if str(p.get("age_group", "")).startswith(sr.PROPAGATED_PREFIXES):
            hidden.append((s, s.pop("age_group")))
    sr.normalize_age_bounds(res, rules, schema)
    for s, v in hidden:
        s["age_group"] = v


def main(options: list[str]) -> None:
    harm = Harmonizer(SRC / "crosswalks")
    manifest = load_manifest()
    report: dict = {}
    for option in options:
        prop = Counter()
        per_field = defaultdict(bench._zero)
        per_field_cond = defaultdict(bench._zero)
        by_study_field = defaultdict(bench._zero)
        for run in sorted(p for p in SRC.glob("*_r*") if p.is_dir()):
            dst = OUT / option / run.name
            dst.mkdir(parents=True, exist_ok=True)
            for m in manifest:
                rj = run / f"{m['study']}.json"
                out = dst / rj.name
                if rj.exists():
                    res = ExtractionResult.model_validate_json(rj.read_text())
                    if option != "v3_asis":
                        strip(res)
                        if res.granularity == "sample_level":
                            mk = run.name.split("_")[0]
                            prop.update({(mk, f, k): v for (f, k), v in fan_out(res, option).items()})
                        if option == "D2_range_pair_group_guard":
                            age_rules_ignoring_propagated_group(res)
                        else:
                            sr.normalize_age_bounds(res, rules, schema)
                    out.write_text(res.model_dump_json())
                else:
                    out.unlink(missing_ok=True)
                rec = bench.score_study(m, out, harm)
                for f, c in rec["fields_end_to_end"].items():
                    if f in bench.META_FIELDS:
                        continue
                    bench._add(per_field[(run.name.split("_")[0], f)], c)
                    bench._add(per_field_cond[(run.name.split("_")[0], f)], rec["fields_conditional"][f])
                    bench._add(by_study_field[(run.name.split("_")[0], m["study"], f)], c)
        report[option] = {"propagation": {"|".join(k): v for k, v in sorted(prop.items())},
                          "per_field": {f"{mk}|{f}": v for (mk, f), v in per_field.items()},
                          "per_field_cond": {f"{mk}|{f}": v for (mk, f), v in per_field_cond.items()},
                          "by_study_field": {"|".join(k): v for k, v in by_study_field.items()}}
    (OUT / "report.json").write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main(sys.argv[2:])
