"""MetaHarmonizer (OntologyMapper) crosswalks for post-harmonization scoring.

A run tree keeps the crosswalks generated from its own extracted terms in
``TREE/crosswalks/`` (``harmonize/regen_crosswalks.py --tree TREE``):

  crosswalk_<field>.csv       extracted terms -> OntologyMapper top match
  crosswalk_gold_<field>.csv  gold terms      -> OntologyMapper top match

Every field with a ``crosswalk_<field>.csv`` is harmonized; adding a corpus and
regenerating crosswalks for another field brings it into scoring with no code
change. A value maps to the *set* of ontology codes of its delimiter-separated
terms. Exact-stage rows (whose ``match1_code`` is empty because the query *is* a
corpus label) are backfilled from the field corpus's label -> code map.

:class:`Harmonizer` supplies the comparison used by ``bench.py eval``:

* harmonized field, gold cell has a curated ``<field>_ontology_term_id``:
  correct iff every extracted term maps and the extracted code set equals the
  curated code set;
* harmonized field, gold cell has no curated id: both values map through the
  same crosswalk and are compared as code sets (a value whose terms do not all
  map is compared as its string);
* any other field: the extracted value as is (``evaluation.values_match``).
"""
from __future__ import annotations

import os
import pathlib
import re

import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent

GOLD_ID_SUFFIX = "_ontology_term_id"
# Marks a gold cell already replaced by its curated code set (see Harmonizer.gold_rows).
_CURATED = "\x00curated:"

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
    }.get(field)


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


def load_field_crosswalk(field: str, directory: pathlib.Path) -> dict[str, str]:
    """Union of the gold and extracted crosswalks for ``field`` (same corpus)."""
    cm = corpus_code_map(field)
    return {**crosswalk_map(directory / f"crosswalk_gold_{field}.csv", cm),
            **crosswalk_map(directory / f"crosswalk_{field}.csv", cm)}


def queried_terms(field: str, directory: pathlib.Path) -> set[str]:
    """Every term sent to OntologyMapper for ``field``, mapped or not."""
    out: set[str] = set()
    for name in (f"crosswalk_gold_{field}.csv", f"crosswalk_{field}.csv"):
        if (directory / name).exists():
            out.update(norm(q) for q in pd.read_csv(directory / name)["query"].dropna())
    return out


def terms_of(value) -> list[str]:
    items = value if isinstance(value, list) else [value]
    return [t.strip() for v in items for t in SPLIT.split(str(v)) if t.strip()]


def codes_of(value, cw: dict[str, str]) -> set[str]:
    return {cw[norm(t)] for t in terms_of(value) if norm(t) in cw}


def gold_id_codes(s) -> set[str]:
    return {c.strip() for c in re.split(r"[;,]", str(s)) if c.strip()
            and c.strip().lower() not in ("na", "nan", "not_reported", "")}


def _is_nr(value) -> bool:
    from metaextractor.evaluation import is_not_reported
    return is_not_reported(value)


class Harmonizer:
    """Post-harmonization comparison for the fields that have a crosswalk in ``directory``."""

    def __init__(self, directory: pathlib.Path):
        self.directory = pathlib.Path(directory)
        if not self.directory.is_dir():
            raise FileNotFoundError(
                f"no crosswalk directory {self.directory}; run "
                f"harmonize/regen_crosswalks.py --tree <tree> first")
        self.fields = sorted(p.stem[len("crosswalk_"):] for p in self.directory.glob("crosswalk_*.csv")
                             if not p.stem.startswith("crosswalk_gold_"))
        self.crosswalks = {f: load_field_crosswalk(f, self.directory) for f in self.fields}
        self.queried = {f: queried_terms(f, self.directory) for f in self.fields}

    def codes(self, value, field: str) -> set[str] | None:
        """Code set of ``value``, or None unless every term maps."""
        cw = self.crosswalks[field]
        terms = terms_of(value)
        if not terms or any(norm(t) not in cw for t in terms):
            return None
        return {cw[norm(t)] for t in terms}

    def unqueried_terms(self, value, field: str) -> list[str]:
        """Terms of ``value`` that were never sent to OntologyMapper (a stale crosswalk)."""
        return [t for t in terms_of(value) if norm(t) not in self.queried[field]]

    def gold_rows(self, gold: list[dict]) -> list[dict]:
        """Copy of ``gold`` with each harmonized cell that has a curated ontology id
        replaced by that id set, so it is compared as curated codes."""
        out = []
        for row in gold:
            r = dict(row)
            for f in self.fields:
                ids = gold_id_codes(row.get(f + GOLD_ID_SUFFIX, ""))
                if ids and not _is_nr(row.get(f)):
                    r[f] = _CURATED + "|".join(sorted(ids))
            out.append(r)
        return out

    def canonicalize(self, value, field: str):
        """``evaluation.evaluate`` canonicalizer: a code-set string for harmonized
        values, the value unchanged otherwise."""
        if field not in self.crosswalks or _is_nr(value):
            return value
        if isinstance(value, str) and value.startswith(_CURATED):
            return value[len(_CURATED):]
        codes = self.codes(value, field)
        return "|".join(sorted(codes)) if codes else value

    @staticmethod
    def display(value) -> str:
        """A gold cell for reports (strips the curated-id marker)."""
        return value[len(_CURATED):] if isinstance(value, str) and value.startswith(_CURATED) else value
