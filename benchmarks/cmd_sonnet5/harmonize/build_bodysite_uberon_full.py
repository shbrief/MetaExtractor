#!/usr/bin/env python
"""Build the full-UBERON `body_site` corpus (UBERON:0001062 "anatomical entity" descendants).

The committed `bodysite_corpus_v041.csv` holds exactly the six UBERON meanings of the cMD
`body_site` enum. A six-term closed corpus with no similarity threshold forces every queried
string onto one of six body sites -- "USA" scores 0.51 against *skin epidermis*, "Sweden" 0.52
against *feces*. This builds the anatomy subtree instead, so a value that is not a body site has
somewhere else to land and, with a threshold, can go unmapped.

The schema's own `body_site_details` slot already names this root, so the corpus is the one the
schema declares rather than a new choice.

  python harmonize/build_bodysite_uberon_full.py [--out PATH]
"""
from __future__ import annotations

import argparse
import pathlib
import time

import pandas as pd
from metaharmonizer.knowledge_db.combined_corpus_builder import CombinedCorpusBuilder

HERE = pathlib.Path(__file__).resolve().parent
ROOT = "UBERON:0001062"
#: The six cMD enum meanings, kept explicit so the enum's own targets cannot go missing
#: if the subtree fetch changes upstream.
CMD_BODYSITE = ["UBERON:0001988", "UBERON:0000167", "UBERON:0001003",
                "UBERON:0000996", "UBERON:0001707", "UBERON:0001913"]
COLUMNS = ["iri", "ontology_name", "ontology_prefix", "short_form", "label", "obo_id",
           "definitions", "description", "synonyms", "parents", "children", "roles", "type"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "bodysite_corpus_uberon_full.csv"))
    args = ap.parse_args()

    b = CombinedCorpusBuilder()
    t0 = time.time()
    recs = b.build_field_corpus(
        {"col.name": "body_site", "dynamic.enum": ROOT, "dynamic.enum.property": "descendant",
         "static.enum": "|".join(CMD_BODYSITE), "allowedvalues": None},
        fetch_static_synonyms=False)
    have = {r.get("obo_id") for r in recs}
    missing = [c for c in CMD_BODYSITE if c not in have]
    if missing:
        recs += b._fetch_single_records(missing)
    df = pd.DataFrame(recs)
    for c in COLUMNS:
        if c not in df.columns:
            df[c] = ""
    df = df[COLUMNS].drop_duplicates(subset="obo_id")

    # Keep UBERON only. The subtree traversal also returns CL cells, GO cellular components,
    # NCBITaxon taxa and a few contributor ORCIDs carried as ``obo_id``; none is a body site,
    # cMD's ``body_site_ontology_term_id`` values are UBERON, and OntoMapEngine refuses a
    # corpus spanning several prefixes.
    prefix = df["obo_id"].astype(str).str.split(":").str[0]
    dropped = prefix.value_counts().drop("UBERON", errors="ignore")
    df = df[prefix == "UBERON"]
    df.to_csv(args.out, index=False)
    if len(dropped):
        print("dropped non-UBERON terms:", dropped.to_dict())

    have = set(df["obo_id"])
    print(f"{len(df)} terms in {time.time()-t0:.0f}s -> {args.out}")
    print("cMD enum meanings present:",
          {c: c in have for c in CMD_BODYSITE})


if __name__ == "__main__":
    main()
