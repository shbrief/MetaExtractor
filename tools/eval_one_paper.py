"""CLI wrapper around ``metaextractor.evaluation.evaluate``.

Usage:
    python tools/eval_one_paper.py RESULT.json GOLD.tsv \
        [--paper PAPER.txt] [--rows-out cells.tsv]

The cMD-specific field-name crosswalk and the age-unit recipe live here,
so the library module stays gold-schema-agnostic.
"""
from __future__ import annotations

import argparse

from metaextractor.evaluation import (
    evaluate,
    load_extraction,
    load_gold_tsv,
)

# extractor field name → cMD sample-table column. Edit when adding fields.
CMD_FIELD_MAP: dict[str, str] = {
    "subject_id":          "subject_id",
    "age_group":           "age_group",
    "age_max":             "age_max",
    "age_min":             "age_min",
    "age_years":           "age_years",
    "age":                 "age",
    "age_unit":            "age_unit",
    "body_site":           "body_site",
    "control":             "control",
    "country":             "country",
    "curator":             "curator",
    "disease":             "disease",
    "dna_extraction_kit":  "dna_extraction_kit",
    "ncbi_accession":      "ncbi_accession",
    "obgyn_lactating":     "obgyn_lactating",
    "obgyn_pregnancy":     "obgyn_pregnancy",
    "pmid":                "pmid",
    "sequencing_platform": "sequencing_platform",
    "sex":                 "sex",
    "westernized":         "westernized",
    "target_condition":    "target_condition",
    "study_name":          "study_name",
    "biomarker_name":      "biomarker_name",
    "biomarker_unit":      "biomarker_unit",
    "biomarker_value":     "biomarker_value",
}

# Numeric fields that depend on a unit-carrier field for cross-unit comparison.
CMD_UNIT_FIELDS: dict[str, str] = {
    "age":     "age_unit",
    "age_min": "age_unit",
    "age_max": "age_unit",
}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("result_json")
    ap.add_argument("gold_tsv")
    ap.add_argument("--paper", help="paper text for evidence-quote verbatim check")
    ap.add_argument("--rows-out", help="path to write per-cell TSV")
    args = ap.parse_args()

    extraction = load_extraction(args.result_json)
    gold = load_gold_tsv(args.gold_tsv)
    paper_text = open(args.paper).read() if args.paper else None

    result = evaluate(
        extraction=extraction,
        gold_rows=gold,
        field_map=CMD_FIELD_MAP,
        paper_text=paper_text,
        unit_fields=CMD_UNIT_FIELDS,
    )

    print(result.summary())
    if args.rows_out:
        result.to_cells_tsv(args.rows_out)
        print(f"\nWrote per-cell results: {args.rows_out}")


if __name__ == "__main__":
    main()
