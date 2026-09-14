#!/usr/bin/env python
"""Build the benchmark's target schema ``cmd.clean.linkml.yaml`` from the cMD LinkML schema.

Two deterministic edits:

1. Downgrade ontology-reachable LinkML enums to plain string/list fields.
   MetaExtractor's LinkML adapter only expands enums with static
   ``permissible_values``; enums defined via ``reachable_from`` (dynamic ontology
   subtrees) have nothing to enumerate, so those slots become free text
   (``range: string``), treated as string (single) or list (multivalued).
2. Annotate each slot's ``scope`` (``study`` or ``sample``) per ``SCOPE`` below.
   Scope drives deterministic fan-out only (it is not sent to the model): a
   ``sample``-scoped study-level value is propagated to samples only when it is a
   single, non-aggregate value for a homogeneous cohort. Slots not listed stay
   unannotated (single non-aggregate values propagate).

  python make_clean_schema.py --src /path/to/cmd.linkml.yaml [OUT]

``--src`` defaults to ``$CMD_LINKML_SCHEMA``.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import yaml

STUDY = {
    "study_name", "curator", "pmid", "target_condition", "antibiotics_exclusion_period",
    "antibiotics_exclusion_period_unit", "dna_extraction_kit", "sequencing_platform",
    "host_species", "uncurated_metadata",
}
SAMPLE = {
    "subject_id", "sample_id", "subcohort", "control", "body_site", "body_site_details",
    "days_from_first_collection", "probing_pocket_depth", "probing_pocket_depth_value",
    "ncbi_accession", "age", "age_group", "age_min", "age_max", "age_years", "family",
    "family_role", "sex", "zigosity", "antibiotics_current_use", "bmi", "dietary_restriction",
    "disease", "disease_details", "disease_response_orr", "disease_response_pfs",
    "disease_response_pfs_month", "disease_response_recist", "feces_phenotype",
    "feces_phenotype_value", "fmt_id", "fmt_role", "hla", "neonatal_birth_weight",
    "neonatal_delivery_procedure", "neonatal_feeding_method", "neonatal_gestational_age",
    "neonatal_preterm_birth", "obgyn_birth_control", "obgyn_lactating", "obgyn_menopause",
    "obgyn_pregnancy", "smoker", "treatment", "tumor_staging_ajcc", "tumor_staging_tnm",
    "biomarker_name", "biomarker_unit", "biomarker_value", "disease_response_os",
    "disease_response_os_unit", "ecog_performance_status", "tumor_size_measurement",
    "tumor_size_residual_measurement",
}
SCOPE = {**{s: "study" for s in STUDY}, **{s: "sample" for s in SAMPLE}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?", default="cmd.clean.linkml.yaml")
    ap.add_argument("--src", default=os.environ.get("CMD_LINKML_SCHEMA"))
    args = ap.parse_args()
    if not args.src:
        raise SystemExit("pass --src or set CMD_LINKML_SCHEMA to the cMD cmd.linkml.yaml")
    data = yaml.safe_load(Path(args.src).read_text())
    enums = data.get("enums") or {}
    dynamic = {n for n, d in enums.items() if not (d or {}).get("permissible_values")}
    slots = data.get("slots") or {}
    changed = [sn for sn, sd in slots.items() if sd and sd.get("range") in dynamic]
    for sn in changed:
        slots[sn]["range"] = "string"
    annotated = 0
    for sn, scope in SCOPE.items():
        if sn in slots:
            slots[sn] = slots[sn] or {}
            slots[sn].setdefault("annotations", {})["scope"] = scope
            annotated += 1
    Path(args.out).write_text(yaml.safe_dump(data, sort_keys=False))
    print(f"downgraded {len(changed)} slots (dynamic enums -> string): {changed}")
    print(f"annotated scope on {annotated} slots "
          f"(unannotated: {sorted(set(slots) - set(SCOPE))})")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
