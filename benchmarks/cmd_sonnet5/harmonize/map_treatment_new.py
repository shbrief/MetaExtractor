#!/usr/bin/env python
"""Regenerate crosswalk_treatment.csv for the multi-seed representative runs.

Mirrors run_om.py's treatment branch only (NCIT:C1909 corpus, Stage 1 exact +
Stage 2 embed + 2.5 synonym), so the v0.4.1 disease/body_site crosswalks are left
untouched. Reads extracted treatment values from the dirs named in
RESCORE_SONNET_DIR / RESCORE_HAIKU_DIR (default out / out_haiku).
"""
from __future__ import annotations
import json, os, pathlib, time
import pandas as pd

from metaharmonizer import OntoMapEngine
from metaharmonizer._paths import RETRIEVED_ONTOLOGIES_DIR

HERE = pathlib.Path(__file__).resolve().parent
BENCH = HERE.parent
MANI = json.loads((BENCH / "manifest.json").read_text())
DIRS = [os.environ.get("RESCORE_SONNET_DIR", "out"),
        os.environ.get("RESCORE_HAIKU_DIR", "out_haiku")]
SPLIT = lambda s: [t.strip() for t in str(s).replace("/", ";").split(";") if t.strip()]


def collect() -> list[str]:
    vals: set[str] = set()
    for outdir in DIRS:
        for m in MANI:
            p = BENCH / outdir / f"{m['study']}.json"
            if not p.exists():
                continue
            d = json.loads(p.read_text())
            for c in [d.get("fields") or {}] + list(d.get("samples") or []):
                v = c.get("treatment")
                if isinstance(v, dict):
                    v = v.get("value")
                for x in (v if isinstance(v, list) else [v]):
                    if x and str(x).strip().lower() not in ("not_reported", "na", "nan", ""):
                        vals.update(SPLIT(x))
    return sorted(vals)


def main():
    terms = collect()
    print(f"treatment: {len(terms)} unique atomic terms:\n  {terms}", flush=True)
    t0 = time.time()
    eng = OntoMapEngine(corpus_category="treatment", query_ls=terms,
                        ontology_source="ncit", s3_strategy=None)
    res = eng.run()
    print(f"OM done in {time.time()-t0:.0f}s", flush=True)
    df = pd.read_csv(RETRIEVED_ONTOLOGIES_DIR / "ncit_treatment_corpus.csv")
    lab = "label" if "label" in df.columns else "official_label"
    code_map = {str(l).strip().lower(): str(c) for l, c in zip(df[lab], df["obo_id"])}
    res["match1_code"] = res["match1"].map(lambda l: code_map.get(str(l).strip().lower(), ""))
    cols = ["query", "ref_match", "stage", "match1", "match1_score", "match1_code"]
    out = HERE / "crosswalk_treatment.csv"
    res[[c for c in cols if c in res.columns]].to_csv(out, index=False)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
