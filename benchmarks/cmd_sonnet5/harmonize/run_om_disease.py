#!/usr/bin/env python
"""Disease-only OntologyMapper run against the CORRECT general-disease NCIt root
(NCIT:C2991 'Disease or Disorder'), built fresh in an ISOLATED cache so the
user's shipped oncology (NCIT:C3262) disease corpus is left untouched.

Env (set by caller): METAHARMONIZER_DATA_DIR + KNOWLEDGE_DB_DIR point at a temp
dir; MODEL_CACHE_ROOT reuses the existing sap-bert download.
"""
from __future__ import annotations
import json, pathlib, time
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
BENCH = HERE.parent
MANI = json.loads((BENCH / "manifest.json").read_text())

from metaharmonizer.engine import ontology_mapping_engine as ome
ome._CORPUS_REGISTRY[("disease", "ncit")] = "NCIT:C2991"   # general disease, not neoplasm
from metaharmonizer import OntoMapEngine
from metaharmonizer._paths import RETRIEVED_ONTOLOGIES_DIR

SPLIT = lambda s: [t.strip() for t in str(s).replace("/", ";").split(";") if t.strip()]


def collect():
    vals = set()
    for outdir in ("out", "out_haiku"):
        for m in MANI:
            p = BENCH / outdir / f"{m['study']}.json"
            if not p.exists():
                continue
            d = json.loads(p.read_text())
            for c in [d.get("fields") or {}] + list(d.get("samples") or []):
                v = c.get("disease")
                if isinstance(v, dict):
                    v = v.get("value")
                for x in (v if isinstance(v, list) else [v]):
                    if x and str(x).strip().lower() not in ("not_reported", "na", "nan", ""):
                        vals.update(SPLIT(x))
    return sorted(vals)


def main():
    terms = collect()
    print(f"disease terms ({len(terms)}): {terms}", flush=True)
    t0 = time.time()
    eng = OntoMapEngine(corpus_category="disease", query_ls=terms,
                        ontology_source="ncit", s3_strategy=None)
    res = eng.run()
    print(f"OM done in {time.time()-t0:.0f}s", flush=True)
    df = pd.read_csv(RETRIEVED_ONTOLOGIES_DIR / "ncit_disease_corpus.csv")
    lab = "label"; oid = "obo_id"
    code_map = {str(l).strip().lower(): str(c) for l, c in zip(df[lab], df[oid])}
    res["match1_code"] = res["match1"].map(lambda l: code_map.get(str(l).strip().lower(), ""))
    out = HERE / "crosswalk_disease.csv"
    res[["query", "ref_match", "stage", "match1", "match1_score", "match1_code"]].to_csv(out, index=False)
    print(f"wrote {out}", flush=True)
    print(res[["query", "match1", "match1_score", "match1_code"]].to_string(index=False))


if __name__ == "__main__":
    main()
