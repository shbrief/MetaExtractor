"""Re-score the development check under the committed schema, offline (no model calls).

The ``devcheck_haiku45`` extractions were produced when ``propagate_study_value`` held
``body_site`` only. This replays their saved records through the current
``cmd.clean.linkml.yaml`` -- re-running the fan-out, the age rules and the scoring with the
run's own crosswalks -- so the effect of an allowlist change is visible without re-extracting.
The fan-out never overwrites a filled cell, so replaying is equivalent to having run with the
current annotations.

  CMD_CURATION_DIR=... python dev_analysis/allowlist_replay.py
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent
sys.path.insert(0, str(BENCH))
sys.path.insert(0, str(BENCH / "harmonize"))
import bench                                                # noqa: E402
from bench_paths import AGE_RULES, SCHEMA, load_manifest    # noqa: E402
from crosswalk import Harmonizer                            # noqa: E402

from metaextractor import sample_rules as sr                # noqa: E402
from metaextractor.output import ExtractionResult           # noqa: E402
from metaextractor.schema_loader import load_schema_file    # noqa: E402

RUN = HERE / "devcheck_haiku45" / "haiku_r1"
TMP = RUN / "_replay.json"
KEYS = ("tp_correct", "tp_wrong", "fn", "fp")


def main() -> None:
    schema = load_schema_file(SCHEMA)
    allow = sorted(f.name for f in schema.fields if f.propagate_study_value)
    rules = sr.AgeBoundRules.from_json(AGE_RULES)
    harm = Harmonizer(HERE / "devcheck_haiku45" / "crosswalks")
    print(f"propagate_study_value = {allow}\n")
    asrun = {k: 0 for k in KEYS}
    now = {k: 0 for k in KEYS}
    print(f"{'study':24} {'as run TPc/TPw':>16} {'replayed TPc/TPw':>18}")
    for m in load_manifest():
        p = RUN / f"{m['study']}.json"
        if not p.exists():
            continue
        res = ExtractionResult.model_validate_json(p.read_text())
        a = bench.score_study(m, p, harm)["end_to_end"]["content"]
        r = res.model_copy(deep=True)
        sr.fan_out_fields_to_samples(r, schema)
        sr.normalize_age_bounds(r, rules, schema)
        TMP.write_text(r.model_dump_json())
        b = bench.score_study(m, TMP, harm)["end_to_end"]["content"]
        TMP.unlink()
        for k in KEYS:
            asrun[k] += a[k]
            now[k] += b[k]
        mark = "  <-" if (a["tp_correct"], a["tp_wrong"]) != (b["tp_correct"], b["tp_wrong"]) else ""
        pair = lambda c: f"{c['tp_correct']}/{c['tp_wrong']}"
        print(f"{m['study']:24} {pair(a):>16} {pair(b):>18}{mark}")
    for label, t in (("as run   ", asrun), ("replayed ", now)):
        print(f"\n{label} pooled: TPc {t['tp_correct']} TPw {t['tp_wrong']} FN {t['fn']} "
              f"FP {t['fp']} F1 {bench.metrics(t)['f1']:.4f}")


if __name__ == "__main__":
    main()
