#!/usr/bin/env python
"""Regenerate the extracted-value (and gold) OntologyMapper crosswalks used by
`bench.py harmonize` / rescore.py, WITHOUT rebuilding the corpora.

The corpora are the committed v0.4.1 artifacts (disease = C7057 + static Healthy;
body_site = 6 UBERON terms; treatment = the NCIt Pharmacologic-Substance corpus),
and their sap-bert FAISS indexes are already persisted under ~/.metaharmonizer,
so this only embeds the query terms and does the FAISS lookup — minutes, not the
3.6 h the original corpus build took.

Extracted terms are collected from the UNION of the single-run dirs (out, out_haiku)
and the multi-seed representative runs actually scored in MANUSCRIPT Section 3.6
(out_ms/sonnet_r1, out_ms/haiku_r1), so every value scored there has a crosswalk
entry. Gold terms are run-independent. Both sides map through the SAME corpus, so
code-level agreement is well defined.

Usage:  python regen_crosswalks.py [disease|body_site|treatment ...]
        (no args = all three)
"""
from __future__ import annotations
import csv, json, pathlib, sys, time
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
BENCH = HERE.parent
MANI = json.loads((BENCH / "manifest.json").read_text())

from metaharmonizer import OntoMapEngine
from metaharmonizer._paths import RETRIEVED_ONTOLOGIES_DIR

# Dirs whose extracted values must all be covered by the crosswalk.
EXT_DIRS = ("out", "out_haiku", "out_ms/sonnet_r1", "out_ms/haiku_r1")
SPLIT = lambda s: [t.strip() for t in str(s).replace("/", ";").replace(",", ";").split(";") if t.strip()]

# Per-field corpus source. disease/body_site use the committed v041 corpus CSV as
# an explicit corpus_df; treatment uses the NCIt registry corpus (as run_om.py did).
CORPUS_CSV = {
    "disease":   HERE / "disease_corpus_v041.csv",
    "body_site": HERE / "bodysite_corpus_v041.csv",
    "treatment": RETRIEVED_ONTOLOGIES_DIR / "ncit_treatment_corpus.csv",
}
OM_CATEGORY = {"disease": "disease", "body_site": "bodysite", "treatment": "treatment"}


def _lab_col(df: pd.DataFrame) -> str:
    return "official_label" if "official_label" in df.columns else "label"


def code_map(field: str) -> dict[str, str]:
    df = pd.read_csv(CORPUS_CSV[field])
    lab = _lab_col(df)
    return {str(l).strip().lower(): str(c) for l, c in zip(df[lab], df["obo_id"])}


def collect_extracted(field: str) -> list[str]:
    vals: set[str] = set()
    for outdir in EXT_DIRS:
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


def collect_gold(field: str) -> list[str]:
    vals: set[str] = set()
    for m in MANI:
        for r in csv.DictReader(pathlib.Path(m["gold_tsv"]).open(), delimiter="\t"):
            v = (r.get(field) or "").strip()
            if v and v.lower() not in ("na", "nan", "not_reported", ""):
                vals.update(SPLIT(v))
    return sorted(vals)


def run_om(field: str, terms: list[str]):
    """Map terms through the field's corpus, reusing the persisted FAISS index."""
    kw = dict(corpus_category=OM_CATEGORY[field], query_ls=terms,
              s3_strategy=None, persist_corpus=True)
    if field in ("disease", "body_site"):
        kw["corpus_df"] = pd.read_csv(CORPUS_CSV[field])
    else:  # treatment: NCIt registry corpus (persisted lm_ index)
        kw["ontology_source"] = "ncit"
    return OntoMapEngine(**kw).run()


def to_crosswalk(res: pd.DataFrame, cmap: dict) -> pd.DataFrame:
    res = res.copy()
    res["match1_code"] = res["match1"].map(lambda l: cmap.get(str(l).strip().lower(), ""))
    cols = ["query", "ref_match", "stage", "match1", "match1_score", "match1_code"]
    return res[[c for c in cols if c in res.columns]]


def main(fields: list[str]) -> None:
    for field in fields:
        t0 = time.time()
        cmap = code_map(field)
        ext, gold = collect_extracted(field), collect_gold(field)
        print(f"\n=== {field}: {len(ext)} extracted terms, {len(gold)} gold terms ===", flush=True)

        to_crosswalk(run_om(field, ext), cmap).to_csv(HERE / f"crosswalk_{field}.csv", index=False)
        print(f"  wrote crosswalk_{field}.csv", flush=True)
        to_crosswalk(run_om(field, gold), cmap).to_csv(HERE / f"crosswalk_gold_{field}.csv", index=False)
        print(f"  wrote crosswalk_gold_{field}.csv  ({time.time()-t0:.0f}s)", flush=True)


if __name__ == "__main__":
    fields = [a for a in sys.argv[1:] if a in OM_CATEGORY] or list(OM_CATEGORY)
    main(fields)
