#!/usr/bin/env python
"""Rebuild the cMD `disease` corpus the v0.4.1 way — CombinedCorpusBuilder over
the cMD spec: dynamic root NCIT:C7057 ('Disease, Disorder or Finding') merged
with the static term NCIT:C115935 ('Healthy'). Then map BOTH the extracted and
the gold disease values through OntologyMapper against this combined corpus and
write the crosswalks used by rescore.py.

NOTE: cMD's disease seed also lists MONDO:0000001. We build the NCIt arm
(C7057 + static Healthy) only: gold disease IDs are NCIt, so NCIt is what code-
level agreement is scored against; MONDO would add cross-ontology synonyms but
not change NCIt-code matches. Runs in an isolated cache (non-destructive).
"""
from __future__ import annotations
import json, pathlib, time
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
BENCH = HERE.parent
MANI = json.loads((BENCH / "manifest.json").read_text())
SPLIT = lambda s: [t.strip() for t in str(s).replace("/", ";").replace(",", ";").split(";") if t.strip()]

from metaharmonizer.knowledge_db.combined_corpus_builder import CombinedCorpusBuilder
from metaharmonizer import OntoMapEngine
from metaharmonizer._paths import RETRIEVED_ONTOLOGIES_DIR


def collect(field):
    vals = set()
    for outdir in ("out", "out_haiku"):
        for m in MANI:
            p = BENCH / outdir / f"{m['study']}.json"
            if not p.exists():
                continue
            d = json.loads(p.read_text())
            for c in [d.get("fields") or {}] + list(d.get("samples") or []):
                v = c.get(field)
                if isinstance(v, dict):
                    v = v.get("value")
                for x in (v if isinstance(v, list) else [v]):
                    if x and str(x).strip().lower() not in ("not_reported", "na", "nan", ""):
                        vals.update(SPLIT(x))
    return sorted(vals)


def gold_terms(field):
    import csv
    vals = set()
    for m in MANI:
        for r in csv.DictReader(pathlib.Path(m["gold_tsv"]).open(), delimiter="\t"):
            v = (r.get(field) or "").strip()
            if v and v.lower() not in ("na", "nan", "not_reported", ""):
                vals.update(SPLIT(v))
    return sorted(vals)


def code_map_from(df):
    lab = "official_label" if "official_label" in df.columns else "label"
    return {str(l).strip().lower(): str(c) for l, c in zip(df[lab], df["obo_id"])}


def crosswalk(res, cmap):
    res = res.copy()
    res["match1_code"] = res["match1"].map(lambda l: cmap.get(str(l).strip().lower(), ""))
    return res[["query", "ref_match", "stage", "match1", "match1_score", "match1_code"]]


def main():
    t0 = time.time()
    b = CombinedCorpusBuilder()
    print("building combined disease corpus: NCIT:C7057 (descendants) + static NCIT:C115935 ...", flush=True)
    recs = b.build(dynamic_roots=["NCIT:C7057"], static_terms=["NCIT:C115935"], prop="descendant")
    corpus_df = pd.DataFrame(recs)
    print(f"combined corpus: {len(corpus_df)} terms in {time.time()-t0:.0f}s "
          f"| Healthy present: {'NCIT:C115935' in set(corpus_df['obo_id'])}", flush=True)
    corpus_df.to_csv(HERE / "disease_corpus_v041.csv", index=False)
    cmap = code_map_from(corpus_df)

    ext_terms, g_terms = collect("disease"), gold_terms("disease")
    print(f"extracted disease terms: {len(ext_terms)} | gold: {len(g_terms)}", flush=True)

    print("mapping extracted disease terms ...", flush=True)
    res_ext = OntoMapEngine(corpus_category="disease", query_ls=ext_terms,
                            corpus_df=corpus_df, s3_strategy=None, persist_corpus=True).run()
    crosswalk(res_ext, cmap).to_csv(HERE / "crosswalk_disease.csv", index=False)

    print("mapping gold disease terms ...", flush=True)
    res_gold = OntoMapEngine(corpus_category="disease", query_ls=g_terms,
                             corpus_df=corpus_df, s3_strategy=None, persist_corpus=True).run()
    crosswalk(res_gold, cmap).to_csv(HERE / "crosswalk_gold_disease.csv", index=False)

    print("\n=== extracted disease mappings ===", flush=True)
    print(crosswalk(res_ext, cmap)[["query", "match1", "match1_score", "match1_code"]].to_string(index=False))
    print("\n=== gold disease mappings ===", flush=True)
    print(crosswalk(res_gold, cmap)[["query", "match1", "match1_score", "match1_code"]].to_string(index=False))
    print(f"\nTOTAL {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
