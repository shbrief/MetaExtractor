#!/usr/bin/env python
"""Build the ``host_species`` crosswalk corpus from the two NCIt concepts the schema names.

Unlike the two ``custom_enum`` fields, ``host_species`` declares real ontology codes --
``static.enum = NCIT:C14225|NCIT:C14238`` -- both from one ontology, so nothing here is
authored: the labels and every alias row come from NCI EVSREST. That matters, because the
alignment this corpus provides is exactly the one the reference needs. The schema shows the
model ``Human``/``Mouse``; the cMD tables curate ``Homo sapiens``; and ``Homo sapiens`` is a
recorded NCIt synonym of C14225 *Human*. Scored as surface strings the two disagree on every
row; scored as codes they are one concept.

One row per surface form, all rows of a concept sharing its ``obo_id`` -- the same shape
``build_custom_enum_corpora.py`` produces, so ``crosswalk.corpus_code_map`` resolves an
exact-stage hit on any spelling.

Usage:  python build_host_species_corpus.py
"""
from __future__ import annotations

import csv
import json
import pathlib
import sys
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import crosswalk  # noqa: E402
OUT = HERE / "host_species_corpus.csv"
CODES = ["C14225", "C14238"]
API = "https://api-evsrest.nci.nih.gov/api/v1/concept/ncit/{}?include=synonyms"

COLUMNS = ["iri", "ontology_name", "ontology_prefix", "short_form", "label", "obo_id",
           "definitions", "description", "synonyms", "parents", "children", "roles", "type"]


def fetch(code: str) -> dict:
    with urllib.request.urlopen(API.format(code), timeout=60) as r:
        return json.load(r)


def main() -> None:
    rows = []
    for code in CODES:
        d = fetch(code)
        label = d["name"]
        syns = sorted({s["name"] for s in d.get("synonyms", [])})
        # Case is folded downstream by crosswalk.norm, so distinct spellings only. Forms
        # containing a delimiter crosswalk.SPLIT treats as a value separator ("Human,
        # General", "Mammals, Mice") can never arrive as a single term, so they are dropped.
        forms = [f for f in dict.fromkeys([label] + syns) if not crosswalk.SPLIT.search(f)]
        seen = set()
        for form in forms:
            key = form.strip().lower()
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "iri": f"http://purl.obolibrary.org/obo/NCIT_{code}",
                "ontology_name": "ncit", "ontology_prefix": "NCIT",
                "short_form": f"NCIT_{code}", "label": form, "obo_id": f"NCIT:{code}",
                "definitions": "[]", "description": "",
                "synonyms": str(syns), "parents": "[]", "children": "[]",
                "roles": "[]", "type": "class",
            })
        print(f"  NCIT:{code} {label!r}: {len(seen)} surface forms -> {sorted(seen)}")
    with OUT.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {OUT.name}: {len(rows)} rows over {len(CODES)} concepts")


if __name__ == "__main__":
    main()
