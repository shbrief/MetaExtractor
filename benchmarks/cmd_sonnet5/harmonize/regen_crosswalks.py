#!/usr/bin/env python
"""Regenerate the extracted-value (and gold) OntologyMapper crosswalks used for
post-harmonization scoring (`bench.py eval`), WITHOUT rebuilding the corpora.

The corpora are the committed v0.4.1 artifacts (disease = C7057 + static Healthy;
body_site = 6 UBERON terms; treatment = the NCIt Pharmacologic-Substance corpus),
and their sap-bert FAISS indexes are already persisted under ~/.metaharmonizer,
so this only embeds the query terms and does the FAISS lookup — minutes, not the
3.6 h the original corpus build took.

Extracted terms are collected from every ``<model>_r<k>`` run dir of the scored tree
(``--tree``, default ``out_v2``), so every value scored by ``bench.py eval`` has a
crosswalk entry. Gold terms are run-independent. Both sides map through the SAME
corpus, so code-level agreement is well defined. Crosswalks are written to
``TREE/crosswalks/`` next to the outputs they were generated from.

Usage:  CMD_CURATION_DIR=... python regen_crosswalks.py [--tree out_v2] [disease|body_site|treatment ...]
        (no fields = all three)
"""
from __future__ import annotations
import csv, json, os, pathlib, sys, time
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
BENCH = HERE.parent
sys.path.insert(0, str(BENCH))
from bench_paths import gold_paths, load_manifest  # noqa: E402

MANI = load_manifest()

from metaharmonizer import OntoMapEngine
from metaharmonizer._paths import RETRIEVED_ONTOLOGIES_DIR

# Run dirs whose extracted values must all be covered by the crosswalk (set in main).
EXT_DIRS: list[pathlib.Path] = []
OUT_DIR: list[pathlib.Path] = []
SPLIT = lambda s: [t.strip() for t in str(s).replace("/", ";").replace(",", ";").split(";") if t.strip()]

# Per-field corpus source. disease/body_site use the committed v041 corpus CSV as
# an explicit corpus_df; treatment uses the NCIt registry corpus (as run_om.py did).
CORPUS_CSV = {
    "disease":   HERE / "disease_corpus_v041.csv",
    # Same override as crosswalk.py, so mapping and scoring always share one corpus file.
    "body_site": pathlib.Path(os.environ["CMD_BODYSITE_CORPUS"])
                 if os.environ.get("CMD_BODYSITE_CORPUS")
                 else HERE / "bodysite_corpus_v041.csv",
    # Honour the same override as crosswalk.py so scoring and mapping share one corpus file.
    "treatment": pathlib.Path(os.environ.get("METAHARMONIZER_ONTOLOGIES_DIR", RETRIEVED_ONTOLOGIES_DIR))
                 / "ncit_treatment_corpus.csv",
    # Local custom_enum corpora (harmonize/build_custom_enum_corpora.py).
    "sequencing_platform": HERE / "sequencing_platform_corpus.csv",
    "dna_extraction_kit":  HERE / "dna_extraction_kit_corpus.csv",
    # Real NCIt codes (C14225/C14238), so this one is not a local corpus.
    "host_species":        HERE / "host_species_corpus.csv",
}
OM_CATEGORY = {"disease": "disease", "body_site": "bodysite", "treatment": "treatment",
               "sequencing_platform": "sequencing_platform",
               "dna_extraction_kit": "dna_extraction_kit",
               "host_species": "host_species"}
# Local corpora carry local codes (CMDPLAT:/CMDKIT:), which no ontology API can resolve,
# so the synonym-boost stage has nothing to look up and is skipped. Stages 1.0 (exact,
# which is what the alias rows are for) and 2.0 (sap-bert embedding) still run.
LOCAL_CORPUS = {"sequencing_platform", "dna_extraction_kit"}


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
            p = outdir / f"{m['study']}.json"
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
        for r in (row for gp in gold_paths(m)
                  for row in csv.DictReader(gp.open(), delimiter="\t")):
            v = (r.get(field) or "").strip()
            if v and v.lower() not in ("na", "nan", "not_reported", ""):
                vals.update(SPLIT(v))
    return sorted(vals)


def run_om(field: str, terms: list[str]):
    """Map terms through the field's corpus, reusing the persisted FAISS index."""
    kw = dict(corpus_category=OM_CATEGORY[field], query_ls=terms,
              s3_strategy=None, persist_corpus=True)
    if field in LOCAL_CORPUS:
        kw["skip_stage25"] = True
    # Every field passes its corpus explicitly, so mapping never depends on a
    # registry-managed corpus path being present.
    kw["corpus_df"] = pd.read_csv(CORPUS_CSV[field])
    if field in ("treatment", "host_species"):
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

        to_crosswalk(run_om(field, ext), cmap).to_csv(OUT_DIR[0] / f"crosswalk_{field}.csv", index=False)
        print(f"  wrote crosswalk_{field}.csv", flush=True)
        to_crosswalk(run_om(field, gold), cmap).to_csv(OUT_DIR[0] / f"crosswalk_gold_{field}.csv", index=False)
        print(f"  wrote crosswalk_gold_{field}.csv  ({time.time()-t0:.0f}s)", flush=True)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("fields", nargs="*", help=f"subset of {list(OM_CATEGORY)}")
    ap.add_argument("--tree", default="out_v2")
    ap.add_argument("--out", default=None,
                    help="crosswalk output directory (default: TREE/crosswalks). Use it to "
                         "regenerate against a different corpus without touching a frozen tree.")
    a = ap.parse_args()
    if bad := [f for f in a.fields if f not in OM_CATEGORY]:
        raise SystemExit(f"unknown field(s): {bad}")
    tree = pathlib.Path(a.tree)
    tree = tree if tree.is_absolute() else BENCH / tree
    EXT_DIRS[:] = sorted(d for d in tree.glob("*_r*") if d.is_dir())
    if not EXT_DIRS:
        raise SystemExit(f"no run dirs under {tree}")
    out = pathlib.Path(a.out) if a.out else tree / "crosswalks"
    OUT_DIR[:] = [out if out.is_absolute() else BENCH / out]
    OUT_DIR[0].mkdir(parents=True, exist_ok=True)
    main(a.fields or list(OM_CATEGORY))
