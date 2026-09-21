#!/usr/bin/env python
"""Build the crosswalk corpora for the two ``corpus.type = custom_enum`` fields.

``sequencing_platform`` and ``dna_extraction_kit`` declare a custom enumeration in
``cmd_schema.csv`` rather than an ontology node, so there is no public corpus to
pull from OLS/EVSREST the way ``disease`` (NCIt C7057), ``body_site`` (UBERON) and
``treatment`` (NCIt C1908) are pulled. This builds a *local* corpus in the same CSV
shape so those two fields can be scored through the same post-harmonization path.

Why they need one: the schema and the cMD reference name the same instrument
differently -- the schema says ``Illumina HiSeq``, the curated tables say
``IlluminaHiSeq``. Scored as surface strings, an extraction that *obeys* the schema
is counted wrong. A crosswalk maps both vocabularies into one concept space, so the
comparison is about which instrument was used and not about how it is spelled.

The corpus is authored from two inputs ONLY -- the schema's ``allowedvalues`` and the
curated vocabulary actually present in the cMD gold tables. Extracted values are never
consulted, so the alignment cannot be tuned to flatter a run. Three rules, in order:

1. one concept per schema allowed value (the canonical label);
2. a whitespace-insensitive alias for every canonical label, applied uniformly and not
   per-token (``Illumina HiSeq`` -> ``IlluminaHiSeq``, and equally ``Illumina MiSeq`` ->
   ``IlluminaMiSeq`` although no curated row uses that form). Case is already ignored
   downstream by ``crosswalk.norm``, which is what aligns ``Qiagen``/``QIAGEN``;
3. ``EXPLICIT`` below: curated abbreviations that rule 2 cannot reach. Each entry is an
   orthographic/abbreviation identity, never a judgement that two different products are
   the same thing -- ``QIAamp`` is NOT folded into ``QIAGEN``, and ``PowerSoil DNA
   Isolation Kit`` is NOT folded into ``Qiagen``, so a disagreement about which kit was
   used still scores as a disagreement.

Any curated token still unreachable becomes its own concept (rule 4), so the gold side
always maps and a gold-only vocabulary item is not silently forced onto a schema term.

Usage:  CMD_CURATION_DIR=... python build_custom_enum_corpora.py
"""
from __future__ import annotations

import csv
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent
BENCH = HERE.parent
sys.path.insert(0, str(BENCH))
from bench_paths import gold_paths, load_manifest  # noqa: E402

SCHEMA_CSV = pathlib.Path(
    "~/OmicsMLRepo/MetaHarmonizerSchemaRegistry/schema/curatedmetagenomicdata/cmd_schema.csv"
).expanduser()

FIELDS = {"sequencing_platform": "CMDPLAT", "dna_extraction_kit": "CMDKIT"}

# Rule 3. Curated token -> canonical schema label. Abbreviations only.
EXPLICIT = {
    "sequencing_platform": {"IonProton": "Ion Torrent Proton"},
    "dna_extraction_kit": {"MPBio": "MP Biomedicals"},
}

COLUMNS = ["iri", "ontology_name", "ontology_prefix", "short_form", "label", "obo_id",
           "definitions", "description", "synonyms", "parents", "children", "roles", "type"]

NR = {"na", "nan", "not_reported", ""}


def squash(s: str) -> str:
    return re.sub(r"\s+", "", s)


def schema_allowed(field: str) -> list[str]:
    rows = list(csv.DictReader(SCHEMA_CSV.open(), delimiter=" ", quotechar='"'))
    row = next(r for r in rows if r["col.name"] == field)
    return [v.strip() for v in row["allowedvalues"].split("|") if v.strip()]


def gold_vocab(field: str) -> list[str]:
    seen: dict[str, None] = {}
    for m in load_manifest():
        for gp in gold_paths(m):
            for r in csv.DictReader(gp.open(), delimiter="\t"):
                v = (r.get(field) or "").strip()
                if v and v.lower() not in NR:
                    seen[v] = None
    return sorted(seen)


def build(field: str) -> tuple[list[dict], dict]:
    prefix = FIELDS[field]
    canon = schema_allowed(field)
    gold = gold_vocab(field)

    # concept index: normalised surface form -> canonical label
    surface: dict[str, str] = {}
    concepts: list[str] = []

    def add_concept(label: str) -> None:
        concepts.append(label)
        surface.setdefault(label.lower(), label)

    for lab in canon:                                   # rule 1
        add_concept(lab)
    for lab in canon:                                   # rule 2, uniform
        surface.setdefault(squash(lab).lower(), lab)
    for tok, lab in EXPLICIT[field].items():            # rule 3
        if lab not in concepts:
            raise SystemExit(f"{field}: EXPLICIT target {lab!r} is not a schema allowed value")
        surface.setdefault(tok.lower(), lab)

    gold_only = []
    for tok in gold:                                    # rule 4
        if tok.lower() not in surface:
            add_concept(tok)
            surface.setdefault(squash(tok).lower(), tok)
            gold_only.append(tok)

    code = {lab: f"{prefix}:{i:04d}" for i, lab in enumerate(concepts, start=1)}
    aliases: dict[str, list[str]] = {lab: [] for lab in concepts}
    for norm_form, lab in surface.items():
        if norm_form != lab.lower():
            aliases[lab].append(norm_form)

    rows = []
    for norm_form, lab in surface.items():
        # one row per surface form, all sharing the concept's code
        label = lab if norm_form == lab.lower() else norm_form
        rows.append({
            "iri": f"https://omicsmlrepo.org/cmd/{prefix.lower()}/{code[lab].split(':')[1]}",
            "ontology_name": prefix.lower(), "ontology_prefix": prefix,
            "short_form": code[lab].replace(":", "_"),
            "label": label, "obo_id": code[lab],
            "definitions": f"['{field} value {lab!r} of the cMD schema custom enumeration.']",
            "description": f"{field} value {lab!r} of the cMD schema custom enumeration.",
            "synonyms": str(sorted(set(aliases[lab]))),
            "parents": "[]", "children": "[]", "roles": "[]", "type": "class",
        })
    rows.sort(key=lambda r: (r["obo_id"], r["label"]))

    report = {"canonical": canon, "gold": gold, "gold_only": gold_only,
              "unmapped_gold": [t for t in gold if t.lower() not in surface],
              "surface": surface, "code": code}
    return rows, report


def main() -> None:
    for field in FIELDS:
        rows, rep = build(field)
        out = HERE / f"{field}_corpus.csv"
        with out.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=COLUMNS)
            w.writeheader()
            w.writerows(rows)
        print(f"\n=== {field} -> {out.name} ===")
        print(f"  {len(rep['code'])} concepts, {len(rows)} surface forms")
        print(f"  schema allowed values : {len(rep['canonical'])}")
        print(f"  curated gold tokens   : {len(rep['gold'])}")
        for tok in rep["gold"]:
            lab = rep["surface"].get(tok.lower())
            how = ("identical" if lab == tok else
                   "EXPLICIT" if tok in EXPLICIT[field] else
                   "gold-only concept" if tok in rep["gold_only"] else
                   "case/whitespace")
            print(f"    {tok:<24} -> {lab:<28} [{how}]  {rep['code'][lab]}")
        assert not rep["unmapped_gold"], rep["unmapped_gold"]


if __name__ == "__main__":
    main()
