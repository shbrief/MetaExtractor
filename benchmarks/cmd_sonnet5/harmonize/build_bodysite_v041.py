#!/usr/bin/env python
"""Rebuild the cMD `body_site` corpus against UBERON (the ontology gold uses).

cMD `body_site` is a STATIC 6-value enum, each with an explicit UBERON meaning:
    feces UBERON:0001988 · oral cavity UBERON:0000167 · skin epidermis UBERON:0001003
    vagina UBERON:0000996 · nasal cavity UBERON:0001707 · milk UBERON:0001913
So the corpus is exactly those 6 terms (CombinedCorpusBuilder static_terms, OLS4).
Then map BOTH extracted and gold body_site values through it and write crosswalks
that rescore.py compares against gold's UBERON `body_site_ontology_term_id`.
"""
from __future__ import annotations
import csv, json, pathlib, time
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
BENCH = HERE.parent
MANI = json.loads((BENCH / "manifest.json").read_text())
SPLIT = lambda s: [t.strip() for t in str(s).replace("/", ";").replace(",", ";").split(";") if t.strip()]

CMD_BODYSITE = ["UBERON:0001988", "UBERON:0000167", "UBERON:0001003",
                "UBERON:0000996", "UBERON:0001707", "UBERON:0001913"]

from metaharmonizer.knowledge_db.combined_corpus_builder import CombinedCorpusBuilder
from metaharmonizer import OntoMapEngine


def collect(field, dirs):
    vals = set()
    for outdir in dirs:
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
    vals = set()
    for m in MANI:
        for r in csv.DictReader(pathlib.Path(m["gold_tsv"]).open(), delimiter="\t"):
            v = (r.get(field) or "").strip()
            if v and v.lower() not in ("na", "nan", "not_reported", ""):
                vals.update(SPLIT(v))
    return sorted(vals)


def crosswalk(res, cmap):
    res = res.copy()
    res["match1_code"] = res["match1"].map(lambda l: cmap.get(str(l).strip().lower(), ""))
    return res[["query", "ref_match", "stage", "match1", "match1_score", "match1_code"]]


def main():
    t0 = time.time()
    b = CombinedCorpusBuilder()
    print("building UBERON body_site corpus (6 static cMD terms) ...", flush=True)
    recs = b.build(dynamic_roots=[], static_terms=CMD_BODYSITE)
    corpus_df = pd.DataFrame(recs)
    corpus_df.to_csv(HERE / "bodysite_corpus_v041.csv", index=False)
    lab = "official_label" if "official_label" in corpus_df.columns else "label"
    cmap = {str(l).strip().lower(): str(c) for l, c in zip(corpus_df[lab], corpus_df["obo_id"])}
    print(f"corpus: {len(corpus_df)} terms | {dict(zip(corpus_df[lab], corpus_df['obo_id']))}", flush=True)

    ext = collect("body_site", ("out", "out_haiku"))
    g = gold_terms("body_site")
    print(f"extracted body_site: {ext}\ngold body_site: {g}", flush=True)

    res_ext = OntoMapEngine(corpus_category="bodysite", query_ls=ext,
                            corpus_df=corpus_df, s3_strategy=None, persist_corpus=True).run()
    crosswalk(res_ext, cmap).to_csv(HERE / "crosswalk_body_site.csv", index=False)
    res_gold = OntoMapEngine(corpus_category="bodysite", query_ls=g,
                             corpus_df=corpus_df, s3_strategy=None, persist_corpus=True).run()
    crosswalk(res_gold, cmap).to_csv(HERE / "crosswalk_gold_body_site.csv", index=False)

    print("\n=== extracted body_site mappings ===", flush=True)
    print(crosswalk(res_ext, cmap)[["query", "match1", "match1_score", "match1_code"]].to_string(index=False))
    print("\n=== gold body_site mappings ===", flush=True)
    print(crosswalk(res_gold, cmap)[["query", "match1", "match1_score", "match1_code"]].to_string(index=False))
    print(f"\nTOTAL {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
