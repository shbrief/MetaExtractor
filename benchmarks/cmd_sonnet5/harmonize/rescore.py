#!/usr/bin/env python
"""Re-score value-accuracy of disease/body_site/treatment BEFORE vs AFTER
OntologyMapper harmonization, on the same TP cells the bench eval used.

Fair metric: map BOTH the extracted value and the gold value through the SAME
OntologyMapper corpus, then compare ontology codes. This neutralizes raw-vs-
harmonized surface forms on both sides and does not depend on gold's (sparsely
populated) *_ontology_term_id column.

  baseline_correct   = normalized string equality of extracted vs gold label
                       (reproduces the bench TP_correct rate)
  harmonized_correct = OM_code(extracted) ∩ OM_code(gold) is non-empty

OM codes come from crosswalk_<field>.csv (extracted terms) and
crosswalk_gold_<field>.csv (gold terms); exact-stage rows (whose label the tool
reports as "Not Found") are backfilled from the corpus label→code map.
"""
from __future__ import annotations
import csv, json, os, pathlib, re
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
BENCH = HERE.parent
MANI = json.loads((BENCH / "manifest.json").read_text())

# Model output dirs (relative to BENCH), overridable so the same scorer runs over
# the multi-seed representative runs (e.g. out_ms/sonnet_r1) as well as the legacy
# single-run out/ + out_haiku/. Set RESCORE_SONNET_DIR / RESCORE_HAIKU_DIR.
SONNET_DIR = os.environ.get("RESCORE_SONNET_DIR", "out")
HAIKU_DIR = os.environ.get("RESCORE_HAIKU_DIR", "out_haiku")
CORPUS_CSV = {
    "disease":   HERE / "disease_corpus_v041.csv",   # v0.4.1 combined: C7057 + static Healthy
    "body_site": HERE / "bodysite_corpus_v041.csv",   # UBERON, matches gold body_site_ontology_term_id
    "treatment": pathlib.Path.home() / "OmicsMLRepo/MetaHarmonizer/data/corpus/retrieved_ontologies/ncit_treatment_corpus.csv",
}
SPLIT = lambda s: [t.strip() for t in re.split(r"[;/,]", str(s)) if t.strip()]
norm = lambda s: re.sub(r"\s+", " ", str(s)).strip().lower()


def corpus_code_map(field):
    df = pd.read_csv(CORPUS_CSV[field])
    lab = "official_label" if "official_label" in df.columns else "label"
    return {norm(l): str(c) for l, c in zip(df[lab], df["obo_id"])}


def crosswalk_map(path, code_map):
    """value(norm) -> ontology code, backfilling exact-stage rows from corpus."""
    m = {}
    if not path.exists():
        return m
    for _, r in pd.read_csv(path).iterrows():
        q = norm(r["query"])
        raw = r.get("match1_code")
        code = str(raw).strip() if pd.notna(raw) else ""
        if not code or code.lower() == "nan":  # exact-stage rows report label "Not Found"
            code = code_map.get(q, "")          # → the query IS the label; backfill from corpus
        if code and code.lower() != "nan":
            m[q] = code
    return m


def codes_of(value, cw):
    out = set()
    for tok in SPLIT(value):
        c = cw.get(norm(tok), "")
        if c:
            out.add(c)
    return out


GOLD_IDCOL = {"disease": "disease_ontology_term_id",
              "body_site": "body_site_ontology_term_id",
              "treatment": "treatment_ontology_term_id"}


def gold_id_codes(s):
    return {c.strip() for c in re.split(r"[;,]", str(s)) if c.strip()
            and c.strip().lower() not in ("na", "nan", "not_reported", "")}


def main():
    rows = []
    for field in ("disease", "body_site", "treatment"):
        cm = corpus_code_map(field)
        cw_ext = crosswalk_map(HERE / f"crosswalk_{field}.csv", cm)
        cw_gold = crosswalk_map(HERE / f"crosswalk_gold_{field}.csv", cm)
        cw = {**cw_gold, **cw_ext}  # union; both drawn from same corpus
        idcol = GOLD_IDCOL[field]
        for label, model_dir in (("Sonnet5", SONNET_DIR), ("Haiku", HAIKU_DIR)):
            tp = base = harm = n_gid = correct = 0
            for m in MANI:
                cells = BENCH / model_dir / f"{m['study']}.cells.tsv"
                if not cells.exists():
                    continue
                grows = list(csv.DictReader(pathlib.Path(m["gold_tsv"]).open(), delimiter="\t"))
                for row in csv.DictReader(cells.open(), delimiter="\t"):
                    if row["field"] != field or row["decision"] not in ("TP_correct", "TP_wrong"):
                        continue
                    tp += 1
                    ext_codes = codes_of(row["extracted"], cw)
                    if norm(row["extracted"]) == norm(row["gold"]):
                        base += 1
                    if ext_codes & codes_of(row["gold"], cw):           # both-sides agreement
                        harm += 1
                    idx = int(row["sample_idx"])
                    gidset = gold_id_codes(grows[idx].get(idcol, "")) if idx < len(grows) else set()
                    if gidset:                                          # correctness vs gold's own IDs
                        n_gid += 1
                        if ext_codes & gidset:
                            correct += 1
            rows.append(dict(model=label, field=field, tp=tp,
                             base_acc=round(base / tp, 3) if tp else None,
                             agree_acc=round(harm / tp, 3) if tp else None,       # both-sides self-consistency
                             correct_acc=round(correct / n_gid, 3) if n_gid else None,  # vs gold ontology IDs
                             n_gold_id=n_gid))
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))
    df.to_csv(HERE / "rescore_value_accuracy.csv", index=False)
    print(f"\nwrote {HERE/'rescore_value_accuracy.csv'}")
    print("\nbase_acc = raw string match vs gold label")
    print("agree_acc = extraction & gold map to same OM code (self-consistency, NOT correctness)")
    print("correct_acc = OM(extraction) matches gold's own *_ontology_term_id (true correctness), over n_gold_id cells")


if __name__ == "__main__":
    main()
