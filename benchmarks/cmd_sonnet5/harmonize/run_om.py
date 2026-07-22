#!/usr/bin/env python
"""Build NCIt corpora and run OntologyMapper on the extracted disease/body_site/
treatment values from both model runs, writing one crosswalk CSV per category.

Crosswalk columns: query, ref_match, stage, match1 (top label), match1_score,
match1_code (obo_id joined from the built corpus).

Ontology roots (NCIt via EVSREST, keyless):
  disease   -> NCIT:C2991  (Disease or Disorder)  [overrides the shipped
               oncology default NCIT:C3262 Neoplasm, which does not cover cMD's
               general-disease vocabulary]
  bodysite  -> NCIT:C32221 (Body Part)            [registry default]
  treatment -> NCIT:C1909  (Pharmacologic Substance) [registry default]
"""
from __future__ import annotations
import json, sys, time, pathlib, collections
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
BENCH = HERE.parent
MANI = json.loads((BENCH / "manifest.json").read_text())

# --- override the shipped oncology disease root with general Disease-or-Disorder
from metaharmonizer.engine import ontology_mapping_engine as ome
ome._CORPUS_REGISTRY[("disease", "ncit")] = "NCIT:C2991"
from metaharmonizer import OntoMapEngine
from metaharmonizer._paths import RETRIEVED_ONTOLOGIES_DIR

CATS = {  # extraction field -> OM corpus_category
    "disease": "disease",
    "body_site": "bodysite",
    "treatment": "treatment",
}
SPLIT = lambda s: [t.strip() for t in str(s).replace("/", ";").split(";") if t.strip()]


def collect(field: str) -> list[str]:
    vals: set[str] = set()
    for outdir in ("out", "out_haiku"):
        for m in MANI:
            p = BENCH / outdir / f"{m['study']}.json"
            if not p.exists():
                continue
            d = json.loads(p.read_text())
            containers = [d.get("fields") or {}] + list(d.get("samples") or [])
            for c in containers:
                v = c.get(field)
                if isinstance(v, dict):
                    v = v.get("value")
                for x in (v if isinstance(v, list) else [v]):
                    if x and str(x).strip().lower() not in ("not_reported", "na", "nan", ""):
                        vals.update(SPLIT(x))
    return sorted(vals)


def corpus_code_map(category: str) -> dict[str, str]:
    """label(lower) -> obo_id, from the built corpus CSV."""
    csvp = RETRIEVED_ONTOLOGIES_DIR / f"ncit_{category}_corpus.csv"
    df = pd.read_csv(csvp)
    lab = "label" if "label" in df.columns else df.columns[df.columns.str.contains("label", case=False)][0]
    oid = "obo_id" if "obo_id" in df.columns else df.columns[df.columns.str.contains("obo_id|code", case=False)][0]
    return {str(l).strip().lower(): str(c) for l, c in zip(df[lab], df[oid])}


def main():
    for field, category in CATS.items():
        terms = collect(field)
        print(f"\n=== {field} ({category}): {len(terms)} unique atomic terms ===", flush=True)
        print("  terms:", terms, flush=True)
        if not terms:
            continue
        t0 = time.time()
        eng = OntoMapEngine(
            corpus_category=category,
            query_ls=terms,
            ontology_source="ncit",
            s3_strategy=None,          # Stage 1 exact + Stage 2 embed + 2.5 synonym
        )
        res = eng.run()
        print(f"  OM done in {time.time()-t0:.0f}s", flush=True)
        code_map = corpus_code_map(category)
        res["match1_code"] = res["match1"].map(
            lambda l: code_map.get(str(l).strip().lower(), "")
        )
        out = HERE / f"crosswalk_{field}.csv"
        cols = ["query", "ref_match", "stage", "match1", "match1_score", "match1_code"]
        res[[c for c in cols if c in res.columns]].to_csv(out, index=False)
        print(f"  wrote {out}", flush=True)


if __name__ == "__main__":
    main()
