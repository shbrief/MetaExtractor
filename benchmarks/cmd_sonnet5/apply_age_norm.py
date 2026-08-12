#!/usr/bin/env python
"""Deterministically retrofit the age_min/age_max normalization onto the frozen
out_ms_refined extractions, WITHOUT re-calling any LLM.

The age-bound normalization (metaextractor.extractor._normalize_age_bounds) is a
deterministic post-processing step added after out_ms_refined was generated. Because
it depends only on already-extracted field values — not on a fresh model sample —
applying it to the existing <study>.json is exactly equivalent to what a re-run with
the *same* LLM output would have produced, but changes nothing about enumeration
counts, false-positive totals, or run-to-run variance. It isolates the age effect.

Flow (rewrites files in place under out_ms_refined/):
  <model>_r<k>/<study>.json  -> reload as ExtractionResult, normalize, rewrite json+csv

Then rescore + reaggregate with the existing harness:
  python rerun_sra.py eval
  python aggregate.py out_ms_refined
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from metaextractor.evaluation import load_extraction          # noqa: E402
from metaextractor.extractor import _normalize_age_bounds     # noqa: E402
from metaextractor.writers import to_csv                      # noqa: E402

HERE = Path(__file__).resolve().parent
DST = HERE / "out_ms_refined"
MODELS = ["sonnet", "haiku"]
RUNS = 3
ORDER = [
    "Bengtsson-PalmeJ_2015", "TettAJ_2019_b", "LiJ_2017", "NayakRR_2021",
    "PasolliE_2019", "Heitz-BuschartA_2016", "FanY_2023", "QinJ_2012",
    "ContevilleLC_2019", "LiSS_2016",
]


def main() -> None:
    total_files, total_cells = 0, 0
    for model in MODELS:
        for k in range(1, RUNS + 1):
            od = DST / f"{model}_r{k}"
            if not od.exists():
                continue
            for study in ORDER:
                rj = od / f"{study}.json"
                if not rj.exists():
                    continue
                result = load_extraction(rj)
                n = _normalize_age_bounds(result)          # the real, shared step
                rj.write_text(result.model_dump_json(indent=2), encoding="utf-8")
                to_csv(result, od / f"{study}.csv", include_provenance=True)
                total_files += 1
                total_cells += n
                if n:
                    print(f"{model}_r{k}/{study}: {n} age cell(s) normalized", flush=True)
    print(f"\nDONE: {total_cells} age_min/age_max cell(s) rewritten across "
          f"{total_files} extraction(s).")


if __name__ == "__main__":
    main()
