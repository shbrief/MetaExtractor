"""Deterministic relevance scoring: which supplementary tables carry the schema.

A per-sample metadata table and a feature/measurement × samples matrix look
*identical* to the generic relevance signals — both have many rows and a
unique key-like first column — yet only the former belongs in a per-sample
pipeline. So relevance scoring needs a **negative** signal that recognises
measurement matrices and rejects them, or every abundance / expression /
metabolomics matrix flows into ``propose_plan`` and pollutes the join with
one row per feature.

That negative signal is deliberately domain-neutral. It has two layers:

    * a **fast-path** — ``table_plan.is_feature_matrix`` — that recognises
      microbiome-shaped matrices by cheap regexes (MetaPhlAn taxonomy,
      genome accessions) or by transposed sample-ID column headers. Its
      vocabulary is microbiome-specific, but it is *only* a precision
      shortcut, not the load-bearing logic.
    * a **general path** — a dense numeric body whose columns match nothing
      in the schema. Orientation-independent and organism-independent: it
      catches an RNA-seq / metabolomics / proteomics matrix whose sample
      columns aren't ID-shaped, which the fast-path would miss. The
      "matches nothing in the schema" guard is what keeps a legitimately
      numeric *sample* table (clinical labs: glucose, age, bmi per row)
      from being mistaken for a matrix — its headers match schema fields.

The positive relevance signals (used once a table survives the matrix check):

    * shape       — several rows, ≥2 columns (not a one-row summary block)
    * id_column   — a near-unique key column (one row per sample)
    * name_match  — column headers overlap schema field names / descriptions
    * enum_match  — a column's *values* are a schema enum's allowed_values

``enum_match`` is the strongest signal and the one an LLM prompt struggles
to get right, because it matches on cell content rather than header wording:
a ``sex`` column named ``"Gender"`` still matches when its values are
``male``/``female``.

``score_table`` is the whole verdict: it returns ``is_matrix=True`` with
score 0 for matrices, and a positive relevance score otherwise.
``TableRelevance.matched_fields`` / ``.reasons`` are the provenance trail.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from metaextractor.schema import Field, Schema
from metaextractor.supplementary import Table
from metaextractor.table_plan import is_feature_matrix

# Positive-signal weights; sum to 1.0. Enum-value overlap is the most
# discriminating signal because it is content-based, not header-wording based.
_W_SHAPE = 0.20
_W_ID = 0.20
_W_NAME = 0.25
_W_ENUM = 0.35

# Thresholds above which a single field is counted as matched to a column.
_NAME_MATCH_MIN = 0.5
_ENUM_MATCH_MIN = 0.3

# General measurement-matrix thresholds (domain-neutral path). A table wide
# and numeric enough to look like a measurement grid, that matches nothing in
# the schema, is a feature × samples matrix rather than sample metadata.
_MATRIX_NUMERIC_MIN = 0.7
_MATRIX_MIN_COLS = 5
_MATRIX_MIN_ROWS = 3

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    """Lowercase alphanumeric tokens of a header or field name/description."""
    return set(_TOKEN_RE.findall(str(text).lower()))


def _containment(needle: set[str], haystack: set[str]) -> float:
    """Fraction of ``needle`` tokens present in ``haystack`` (0 if empty)."""
    return len(needle & haystack) / len(needle) if needle else 0.0


def _is_number(value: str) -> bool:
    if not value:
        return False
    try:
        float(value)
        return True
    except ValueError:
        return False


# --------------------------------------------------------------------------- #
# Individual signals — each returns a float in [0, 1]
# --------------------------------------------------------------------------- #


def _shape_signal(table: Table) -> float:
    """Per-sample tables have several rows and ≥2 columns; 1-row blocks score ~0."""
    if len(table.columns) < 2:
        return 0.0
    return min(len(table.rows) / 8, 1.0)


def _id_column_signal(table: Table) -> tuple[float, str | None]:
    """Strongest when some column's values are near-unique over ≥4 rows.

    Mirrors the "one output row per biological sample" contract the plan
    executor targets — a table with no key-like column rarely is one.
    """
    best_frac, best_col = 0.0, None
    for col in table.columns:
        vals = [str(r.get(col, "")) for r in table.rows if str(r.get(col, "")) != ""]
        if len(vals) < 4:
            continue
        uniq = len(set(vals)) / len(vals)
        if uniq > best_frac:
            best_frac, best_col = uniq, col
    return (best_frac, best_col) if best_frac > 0.9 else (0.0, None)


def _numeric_body_density(table: Table) -> float:
    """Fraction of non-empty body cells (all columns after the first) that are numeric.

    Skips column 0, which in a measurement matrix holds the feature labels
    (gene / taxon / metabolite names) — the numeric signal lives in the body.
    """
    body_cols = table.columns[1:]
    total = numeric = 0
    for r in table.rows:
        for col in body_cols:
            v = str(r.get(col, ""))
            if not v:
                continue
            total += 1
            if _is_number(v):
                numeric += 1
    return numeric / total if total else 0.0


def _name_match(field_obj: Field, columns: list[str], col_tokens: dict[str, set[str]]) -> str | None:
    """Best column matching a field by name, with the description as fallback vocab.

    Two forms, whichever is stronger: the field *name* tokens covered by the
    header (``age`` ⊆ ``"Age (years)"``), or the header tokens covered by the
    field's name+description vocabulary (``"body_mass_index"`` ⊆ the ``bmi``
    field's description). The description form requires a ≥2-token header so a
    single generic token like ``id`` can't match every field's prose.
    """
    name_tok = _tokens(field_obj.name)
    vocab_tok = name_tok | _tokens(field_obj.description or "")
    best, best_score = None, 0.0
    for col in columns:
        ctok = col_tokens[col]
        by_name = _containment(name_tok, ctok)
        by_vocab = _containment(ctok, vocab_tok) if len(ctok) >= 2 else 0.0
        score = max(by_name, by_vocab)
        if score > best_score:
            best, best_score = col, score
    return best if best_score >= _NAME_MATCH_MIN else None


def _enum_match(field_obj: Field, table: Table) -> tuple[str | None, float]:
    """Best column whose distinct values overlap the enum's allowed_values.

    Content-based: catches columns whose header does not resemble the field
    name at all (``"Gender"`` → ``sex``) as long as the values line up.
    """
    if field_obj.type != "enum" or not field_obj.allowed_values:
        return None, 0.0
    targets = {v.lower() for v in field_obj.allowed_values}
    if field_obj.value_descriptions:  # accept human-readable labels too
        targets |= {k.lower() for k in field_obj.value_descriptions}
    best, best_frac = None, 0.0
    for col in table.columns:
        seen = {str(r.get(col, "")).lower() for r in table.rows} - {""}
        if not seen:
            continue
        frac = len(seen & targets) / len(seen)
        if frac > best_frac:
            best, best_frac = col, frac
    return (best, best_frac) if best_frac >= _ENUM_MATCH_MIN else (None, 0.0)


def _schema_matches(
    table: Table, schema: Schema, col_tokens: dict[str, set[str]]
) -> tuple[dict[str, str], int, int, list[str]]:
    """Match every schema field to a column (enum-value first, then name).

    Returns ``(matched_fields, name_hits, enum_hits, reasons)``. Shared by
    ``score_table`` and ``is_measurement_matrix`` so the matching runs once.
    """
    matched: dict[str, str] = {}
    name_hits = enum_hits = 0
    reasons: list[str] = []
    for f in schema.fields:
        col, frac = _enum_match(f, table)
        if col:
            matched[f.name] = col
            enum_hits += 1
            reasons.append(f"{f.name}: values match enum in {col!r} ({frac:.0%})")
            continue
        col = _name_match(f, table.columns, col_tokens)
        if col:
            matched.setdefault(f.name, col)
            name_hits += 1
    return matched, name_hits, enum_hits, reasons


# --------------------------------------------------------------------------- #
# Measurement-matrix detection (the negative signal)
# --------------------------------------------------------------------------- #


def is_measurement_matrix(table: Table, schema: Schema | None = None) -> bool:
    """Is this a feature/measurement × samples matrix rather than sample metadata?

    Domain-neutral. Fast-path first (``is_feature_matrix``: microbiome
    taxonomy/genome regexes + transposed sample-ID headers), then a general
    path: a wide, dense-numeric body that matches nothing in the schema. When
    no ``schema`` is given, the general path relies on shape + numeric density
    alone (it cannot apply the "matches nothing" guard).
    """
    if is_feature_matrix(table):
        return True
    if (
        len(table.columns) < _MATRIX_MIN_COLS
        or len(table.rows) < _MATRIX_MIN_ROWS
        or _numeric_body_density(table) < _MATRIX_NUMERIC_MIN
    ):
        return False
    if schema is None:
        return True
    col_tokens = {c: _tokens(c) for c in table.columns}
    matched, _, _, _ = _schema_matches(table, schema, col_tokens)
    return not matched  # numeric grid that matches a schema field is a real sample table


# --------------------------------------------------------------------------- #
# Combined score
# --------------------------------------------------------------------------- #


@dataclass
class TableRelevance:
    """Deterministic relevance of one table to the schema. High score = keep."""

    name: str
    score: float
    shape: float
    id_column: float
    name_match: float
    enum_match: float
    matched_fields: dict[str, str] = field(default_factory=dict)  # field name -> column
    reasons: list[str] = field(default_factory=list)
    is_matrix: bool = False  # feature/measurement × samples matrix — reject unconditionally


def score_table(table: Table, schema: Schema) -> TableRelevance:
    """Score one table against ``schema`` with deterministic signals only.

    A measurement matrix short-circuits to ``score=0.0, is_matrix=True`` so
    the verdict is self-contained; the reasons say which path caught it.
    """
    # Fast-path matrix: microbiome regexes or transposed sample-ID headers.
    if is_feature_matrix(table):
        return TableRelevance(
            table.name, 0.0, 0.0, 0.0, 0.0, 0.0,
            reasons=["feature × samples matrix (taxonomy/genome or transposed fast-path)"],
            is_matrix=True,
        )

    col_tokens = {c: _tokens(c) for c in table.columns}
    shape = _shape_signal(table)
    id_score, id_col = _id_column_signal(table)
    matched, name_hits, enum_hits, match_reasons = _schema_matches(table, schema, col_tokens)

    # General-path matrix: a wide, dense-numeric grid that matches nothing in
    # the schema is a feature × samples table, however unique its first column
    # looks. The "not matched" guard spares legitimately numeric sample tables.
    if (
        not matched
        and len(table.columns) >= _MATRIX_MIN_COLS
        and len(table.rows) >= _MATRIX_MIN_ROWS
        and _numeric_body_density(table) >= _MATRIX_NUMERIC_MIN
    ):
        return TableRelevance(
            table.name, 0.0, shape, id_score, 0.0, 0.0,
            reasons=["dense numeric measurement grid with no schema-matching columns"],
            is_matrix=True,
        )

    reasons: list[str] = []
    if id_col:
        reasons.append(f"key-like column {id_col!r}")
    reasons.extend(match_reasons)

    n = max(len(schema.fields), 1)
    name_match = name_hits / n
    enum_match = enum_hits / n
    score = round(
        _W_SHAPE * shape + _W_ID * id_score + _W_NAME * name_match + _W_ENUM * enum_match,
        4,
    )
    return TableRelevance(
        table.name, score, shape, id_score, name_match, enum_match,
        matched_fields=matched, reasons=reasons,
    )


def rank_tables(tables: list[Table], schema: Schema) -> list[TableRelevance]:
    """Score every table; return high-to-low. Deterministic, no LLM."""
    return sorted(
        (score_table(t, schema) for t in tables),
        key=lambda r: r.score,
        reverse=True,
    )
