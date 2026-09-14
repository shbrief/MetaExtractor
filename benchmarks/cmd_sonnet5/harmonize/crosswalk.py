"""OntologyMapper crosswalk helpers for the cMD harmonization scoring.

Only lookup helpers live here; scoring lives in ``bench.py harmonize`` so there
is a single set of semantics (exact code-set equality). A value maps to the *set*
of ontology codes of its delimiter-separated terms:

  crosswalk_<field>.csv       extracted terms -> OntologyMapper top match
  crosswalk_gold_<field>.csv  gold terms      -> OntologyMapper top match

Exact-stage rows (whose ``match1_code`` is empty because the query *is* a corpus
label) are backfilled from the field corpus's label -> code map.
"""
from __future__ import annotations

import os
import pathlib
import re

import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent

GOLD_IDCOL = {
    "disease": "disease_ontology_term_id",
    "body_site": "body_site_ontology_term_id",
    "treatment": "treatment_ontology_term_id",
}

SPLIT = re.compile(r"[;/,]")


def norm(s) -> str:
    return re.sub(r"\s+", " ", str(s)).strip().lower()


def _treatment_corpus() -> pathlib.Path | None:
    env = os.environ.get("METAHARMONIZER_ONTOLOGIES_DIR")
    if env:
        return pathlib.Path(env) / "ncit_treatment_corpus.csv"
    try:
        from metaharmonizer._paths import RETRIEVED_ONTOLOGIES_DIR
        return pathlib.Path(RETRIEVED_ONTOLOGIES_DIR) / "ncit_treatment_corpus.csv"
    except ImportError:
        return None


def corpus_csv(field: str) -> pathlib.Path | None:
    return {
        "disease": HERE / "disease_corpus_v041.csv",   # v0.4.1 combined: C7057 + static Healthy
        "body_site": HERE / "bodysite_corpus_v041.csv",  # the six UBERON body_site enum meanings
        "treatment": _treatment_corpus(),               # NCIt Pharmacologic Substance (C1909)
    }[field]


def corpus_code_map(field: str) -> dict[str, str]:
    path = corpus_csv(field)
    if path is None or not path.exists():
        return {}
    df = pd.read_csv(path)
    lab = "official_label" if "official_label" in df.columns else "label"
    return {norm(l): str(c) for l, c in zip(df[lab], df["obo_id"])}


def crosswalk_map(path: pathlib.Path, code_map: dict[str, str]) -> dict[str, str]:
    """term(norm) -> ontology code, backfilling exact-stage rows from the corpus."""
    m: dict[str, str] = {}
    if not path.exists():
        return m
    for _, r in pd.read_csv(path).iterrows():
        q = norm(r["query"])
        raw = r.get("match1_code")
        code = str(raw).strip() if pd.notna(raw) else ""
        if not code or code.lower() == "nan":
            code = code_map.get(q, "")
        if code and code.lower() != "nan":
            m[q] = code
    return m


def load_field_crosswalk(field: str) -> dict[str, str]:
    """Union of the gold and extracted crosswalks for ``field`` (same corpus)."""
    cm = corpus_code_map(field)
    return {**crosswalk_map(HERE / f"crosswalk_gold_{field}.csv", cm),
            **crosswalk_map(HERE / f"crosswalk_{field}.csv", cm)}


def terms_of(value) -> list[str]:
    return [t.strip() for t in SPLIT.split(str(value)) if t.strip()]


def codes_of(value, cw: dict[str, str]) -> set[str]:
    return {cw[norm(t)] for t in terms_of(value) if norm(t) in cw}


def gold_id_codes(s) -> set[str]:
    return {c.strip() for c in re.split(r"[;,]", str(s)) if c.strip()
            and c.strip().lower() not in ("na", "nan", "not_reported", "")}
