"""LLM-proposed, deterministically-executed table transformation plans.

Supplementary tables from biomedical papers often arrive with structures
the default "row-0 is the header" parser can't make sense of: stacked
multi-row headers, super-headers that group columns under measurement
classes, sample types spread horizontally across columns. This module
handles those cases without letting the LLM touch cell values.

The flow per kept supplementary table:

    1. ``is_feature_matrix`` rejects abundance / presence matrices
       (taxa × samples or feature × samples) — these are not
       sample-metadata tables and would otherwise pollute the per-sample
       output with one "sample" row per feature.

    2. ``propose_plan`` asks the LLM, given the first ~20 raw rows and
       the schema field names, to emit a :class:`TablePlan`: which rows
       form the header, how to merge them, which output columns are
       id_vars, and (optionally) how to melt wide-format groups (e.g.
       a single sample_type column spread across Mother/Infant/Milk
       sub-columns) into long format. The LLM only manipulates column
       names — it never sees cell values, so it cannot hallucinate them.

    3. ``execute_plan`` applies the plan to the raw cell grid in pure
       Python: header rows are merged with a chosen separator, each
       data row produces one output row per melt category, and id_vars
       pass through verbatim. Same plan + same raw grid → same output,
       every time.

Plan-execution failures (missing column references, etc.) surface as
:class:`PlanExecutionError` so the caller can fall back or skip the
table without crashing the whole extraction.
"""
from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from metaextractor.supplementary import Table


# --------------------------------------------------------------------------- #
# Feature-matrix detection
# --------------------------------------------------------------------------- #

# Patterns that strongly suggest a row index is a biological feature, not a
# sample-metadata field. Hits in the first column's values short-circuit to
# "this is a feature matrix" without further inspection.
_TAXONOMY_RE = re.compile(r"\b[kpcofgst]__[A-Za-z0-9_]+")  # MetaPhlAn-style
_GENOME_ACC_RE = re.compile(r"^(GCF_|GCA_|NC_|NZ_|NW_|RefSeq)")  # genome accessions


def _looks_numeric(value: str) -> bool:
    if not value:
        return False
    try:
        float(value)
        return True
    except ValueError:
        return False


# Sample-ID-shaped: alphanumeric runs joined by _ or - (no spaces), 4-40 chars.
# Catches column headers of transposed sample tables and feature × samples
# matrices alike.
_SAMPLE_ID_RE = re.compile(r"^[A-Za-z0-9]+([_-][A-Za-z0-9]+)+$")


def _sample_id_signal(headers: list[str]) -> float:
    """Fraction of (post-col-0) headers that look like sample IDs."""
    candidates = [h for h in headers[1:] if h]
    if not candidates:
        return 0.0
    hits = sum(1 for h in candidates if _SAMPLE_ID_RE.match(h))
    return hits / len(candidates)


def is_feature_matrix(table: Table, n_sample_probe: int = 20) -> bool:
    """Heuristic: is this table feature × samples (or sample-IDs-as-columns)?

    Two signatures qualify:

    1. **Feature × samples matrix**: data rows are dominated by feature
       identifiers (taxonomic lineages, genome accessions) in column 0
       and numeric measurements across the rest.
    2. **Samples-as-columns transposed table**: most column headers
       (excluding col 0) look like sample IDs. Whether the body is
       taxonomy or sample-metadata-by-field, the layout is wrong for a
       per-sample rows pipeline.

    Returns False on small mixed-type sample-metadata tables (st8-style).
    """
    if not table.raw_rows or len(table.raw_rows) < 3:
        return False
    n_cols = len(table.raw_rows[0])
    if n_cols < 2:
        return False

    # Signature 2: do the column headers themselves look like sample IDs?
    # Check row 0; if it's mostly empty (super-header pattern), also peek at
    # row 1 — st10-style tables put sample IDs one row down.
    header_candidates = list(table.raw_rows[0])
    nonempty = sum(1 for h in header_candidates[1:] if h)
    if nonempty < max(2, (n_cols - 1) * 0.3) and len(table.raw_rows) > 1:
        # Merge row 0 + row 1 headers, preferring non-empty cells from row 1.
        row1 = table.raw_rows[1]
        for i in range(1, n_cols):
            if not header_candidates[i] and i < len(row1) and row1[i]:
                header_candidates[i] = row1[i]
    if _sample_id_signal(header_candidates) >= 0.8 and n_cols >= 5:
        return True

    # Signature 1: feature IDs in col 0 + numeric body.
    data_rows = table.raw_rows[1 : 1 + n_sample_probe]
    if not data_rows:
        return False
    first_col_vals = [r[0] for r in data_rows if r and r[0]]
    if not first_col_vals:
        return False
    feature_hits = sum(
        1 for v in first_col_vals
        if _TAXONOMY_RE.search(v) or _GENOME_ACC_RE.match(v)
    )
    feature_signal = feature_hits / len(first_col_vals)

    total = 0
    numeric = 0
    for row in data_rows:
        for cell in row[1:n_cols]:
            if cell == "":
                continue
            total += 1
            if _looks_numeric(cell):
                numeric += 1
    numeric_signal = (numeric / total) if total else 0.0

    return feature_signal >= 0.5 and numeric_signal >= 0.7


# --------------------------------------------------------------------------- #
# Plan schema
# --------------------------------------------------------------------------- #


class IdColumn(BaseModel):
    """A passthrough id column. ``col`` is the 0-based raw column index;
    ``name`` is the label used in the output table."""

    col: int
    name: str


class MeltGroup(BaseModel):
    """One value column produced by melting wide-format sub-columns.

    ``sources`` maps the desired category label (e.g. ``"Mother"``) to
    the 0-based raw column index whose values feed that category.
    """

    value_column: str
    sources: dict[str, int]


class Melt(BaseModel):
    """Long-format reshape spec for wide tables.

    All :class:`MeltGroup`s share the same set of category keys; each
    category produces one output row per data row, with each group
    contributing its own value column.
    """

    category_column: str
    groups: list[MeltGroup]
    skip_missing_categories: bool = True


class TablePlan(BaseModel):
    """LLM-proposed plan for turning a raw cell grid into long-format rows.

    Column references are 0-based raw-column indices — the LLM reads
    them off the c0/c1/c2/… labels in the rendered grid. This avoids
    any disagreement with the executor about how multi-row headers
    should be merged: merging is for display naming only.
    """

    header_rows: list[int]
    header_merge_sep: str = " | "
    data_starts_at: int
    id_columns: list[IdColumn]
    melt: Melt | None = None
    drop_rows: list[int] = Field(default_factory=list)
    drop_columns: list[int] = Field(default_factory=list)
    notes: str | None = None


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #


class PlanProposalError(RuntimeError):
    """Raised when the LLM cannot produce a valid plan for a table."""

    def __init__(
        self,
        message: str,
        raw_response: str | None = None,
        usage: dict[str, int] | None = None,
    ):
        super().__init__(message)
        self.raw_response = raw_response
        self.usage = usage or {}


class PlanExecutionError(RuntimeError):
    """Raised when a plan references columns that don't exist after merging."""


# --------------------------------------------------------------------------- #
# Plan executor
# --------------------------------------------------------------------------- #


def _merge_header_rows(
    header_grid: list[list[str]],
    sep: str,
) -> list[str]:
    """Forward-fill blanks within each header row, then join columnwise.

    Forward-fill propagates super-header labels (which export as empty
    cells under their span in xlsx/csv) so each column gets the full
    stacked label, e.g. ``"DNA (ng/µl) | Mother"``.
    """
    if not header_grid:
        return []
    width = max(len(r) for r in header_grid)
    filled: list[list[str]] = []
    for row in header_grid:
        row = list(row) + [""] * (width - len(row))
        last = ""
        new_row = []
        for cell in row:
            cell = cell.strip()
            if cell:
                last = cell
                new_row.append(cell)
            else:
                new_row.append(last)
        filled.append(new_row)
    merged: list[str] = []
    for ci in range(width):
        parts = [filled[ri][ci].strip() for ri in range(len(filled)) if filled[ri][ci].strip()]
        # Drop consecutive duplicates so a single-row label doesn't become "X | X".
        deduped: list[str] = []
        for p in parts:
            if not deduped or deduped[-1] != p:
                deduped.append(p)
        merged.append(sep.join(deduped))
    return merged


def execute_plan(table: Table, plan: TablePlan) -> Table:
    """Apply a :class:`TablePlan` to a table's raw grid; return new Table.

    Column references in the plan are raw-column indices; values are
    pulled from the raw grid by index. Cell values pass through
    verbatim — no casting, normalization, or invented data.
    """
    raw = table.raw_rows
    if not raw:
        raise PlanExecutionError(f"Table {table.name!r} has no raw_rows; cannot execute plan.")

    n_rows = len(raw)
    n_cols = max((len(r) for r in raw), default=0)

    for ri in plan.header_rows:
        if ri < 0 or ri >= n_rows:
            raise PlanExecutionError(
                f"Table {table.name!r}: header_rows={plan.header_rows} out of bounds (n_rows={n_rows})."
            )
    if plan.data_starts_at >= n_rows:
        raise PlanExecutionError(
            f"Table {table.name!r}: data_starts_at={plan.data_starts_at} >= n_rows={n_rows}."
        )

    # Validate every column reference up front.
    def _check_col(ci: int, where: str) -> None:
        if ci < 0 or ci >= n_cols:
            raise PlanExecutionError(
                f"Table {table.name!r}: {where} references col={ci}, out of range "
                f"(n_cols={n_cols})."
            )

    for ic in plan.id_columns:
        _check_col(ic.col, f"id_columns[{ic.name!r}]")
    for ci in plan.drop_columns:
        _check_col(ci, "drop_columns")
    if plan.melt:
        for g in plan.melt.groups:
            for cat, src in g.sources.items():
                _check_col(src, f"melt.{g.value_column}.sources[{cat!r}]")

    drop_row_set = set(plan.drop_rows)
    data = [raw[ri] for ri in range(plan.data_starts_at, n_rows) if ri not in drop_row_set]
    # Pad short rows for safe indexing.
    data = [r + [""] * max(0, n_cols - len(r)) for r in data]

    out_rows: list[dict[str, Any]] = []
    if plan.melt and plan.melt.groups:
        all_cats: list[str] = []
        seen = set()
        for g in plan.melt.groups:
            for cat in g.sources.keys():
                if cat not in seen:
                    seen.add(cat)
                    all_cats.append(cat)
        for row in data:
            base = {ic.name: row[ic.col] for ic in plan.id_columns}
            for cat in all_cats:
                cat_has_value = False
                values: dict[str, str] = {}
                for g in plan.melt.groups:
                    src = g.sources.get(cat)
                    if src is None:
                        values[g.value_column] = ""
                    else:
                        v = row[src]
                        values[g.value_column] = v
                        if v != "":
                            cat_has_value = True
                if not cat_has_value and plan.melt.skip_missing_categories:
                    continue
                out = dict(base)
                out[plan.melt.category_column] = cat
                out.update(values)
                out_rows.append(out)
    else:
        for row in data:
            out_rows.append({ic.name: row[ic.col] for ic in plan.id_columns})

    out_columns = [ic.name for ic in plan.id_columns]
    if plan.melt and plan.melt.groups:
        out_columns.append(plan.melt.category_column)
        for g in plan.melt.groups:
            out_columns.append(g.value_column)

    return Table(
        name=table.name,
        source=table.source,
        columns=out_columns,
        rows=out_rows,
        raw_rows=table.raw_rows,
    )


# --------------------------------------------------------------------------- #
# LLM proposer
# --------------------------------------------------------------------------- #


_PROPOSE_SYSTEM = """You are a structural-layout analyst for biomedical supplementary tables.

You receive the first rows of one supplementary table from a paper, plus the
list of schema field names the downstream pipeline cares about. You must
propose a plan describing how to read the table so each output row
corresponds to one biological sample.

You ONLY manipulate column structure — never cell values. Numeric cells,
identifiers, and free-text fields must pass through unchanged when the plan
is executed.

Column references are integer column indices (0-based). The rendered grid
shows them as the labels c0, c1, c2, … in row 0 of the TSV display. Use
those numbers directly — do not reference columns by their text label.

Output strictly valid JSON matching this shape:

{
  "header_rows": [<int>, ...],
  "header_merge_sep": " | ",
  "data_starts_at": <int>,
  "id_columns": [
    {"col": <int>, "name": "<output-column-name>"},
    ...
  ],
  "melt": null | {
    "category_column": "<output-column-name>",
    "groups": [
      {
        "value_column": "<output-column-name>",
        "sources": {"<category>": <int>, ...}
      }
    ],
    "skip_missing_categories": true
  },
  "drop_rows": [<int>, ...],
  "drop_columns": [<int>, ...],
  "notes": "<one-line rationale>"
}

Rules:
- header_rows are 0-based row indices. Use 1 row for flat headers; use 2-3
  rows when super-headers stack above leaf column names.
- data_starts_at is the index of the first data row (typically one past
  the last header row).
- id_columns: pick the columns whose values uniquely identify a sample or
  carry per-sample metadata (subject ID, pair, time point, sex, body site,
  age, …). Set "name" to a clean, snake_case-preferred label — prefer the
  schema field names you are given when one fits.
- The downstream pipeline needs one output row per biological sample. If a
  sample-distinguishing attribute — sample type (e.g. Mother/Infant/Milk),
  body site (e.g. stool/saliva), subject role, time point, or compartment —
  is spread horizontally across leaf columns, you MUST use "melt" to turn
  those columns into one categorical column. Wide-format (one row per
  subject/pair with sample-type columns side-by-side) is wrong for this
  pipeline. Each melt group's "sources" maps the category label to the
  column index whose values belong to that category. Omit melt (null) only
  when the table is already in long format (one row = one sample).
- drop_rows: footer notes / summary rows interleaved with data.
- drop_columns: indices of columns the downstream pipeline shouldn't ingest.
- Output JSON only — no prose, no fences."""


def _render_grid_for_llm(raw_rows: list[list[str]], n: int = 20) -> str:
    """Render the first ``n`` raw rows as indexed TSV for the prompt."""
    rows = raw_rows[:n]
    if not rows:
        return "(empty)"
    width = max(len(r) for r in rows)
    lines = ["row\t" + "\t".join(f"c{i}" for i in range(width))]
    for ri, row in enumerate(rows):
        row = list(row) + [""] * (width - len(row))
        cells = [c.replace("\t", " ").replace("\n", " ") for c in row]
        lines.append(f"{ri}\t" + "\t".join(cells))
    return "\n".join(lines)


def propose_plan(
    client: Any,
    model: str,
    table: Table,
    schema_field_names: list[str],
    max_tokens: int = 2048,
    n_rows: int = 20,
) -> tuple[TablePlan, dict[str, int]]:
    """Ask the LLM to propose a :class:`TablePlan` for ``table``.

    Returns ``(plan, usage)`` where ``usage`` is the per-call token usage
    dict (the keys match :class:`MetaExtractor.last_usage`).
    """
    grid = _render_grid_for_llm(table.raw_rows, n_rows)
    user = (
        f"Table name: {table.name}\n"
        f"Total raw rows: {len(table.raw_rows)}\n"
        f"Schema field names (prefer these where they fit): {schema_field_names}\n\n"
        f"First {min(n_rows, len(table.raw_rows))} rows (TSV, row index in column 0):\n\n"
        f"{grid}\n"
    )
    msg = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=_PROPOSE_SYSTEM,
        messages=[{"role": "user", "content": user}],
    )
    raw = "".join(b.text for b in msg.content if b.type == "text").strip()
    u = msg.usage
    usage = {
        "input_tokens": getattr(u, "input_tokens", 0) or 0,
        "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
        "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0,
        "output_tokens": getattr(u, "output_tokens", 0) or 0,
        "n_calls": 1,
    }
    # Strip a stray ```json fence if the model added one.
    stripped = raw
    if stripped.startswith("```"):
        nl = stripped.find("\n")
        if nl != -1:
            stripped = stripped[nl + 1 :]
        end = stripped.rfind("```")
        if end != -1:
            stripped = stripped[:end]
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as e:
        raise PlanProposalError(
            f"Plan response was not valid JSON: {e}", raw_response=raw, usage=usage,
        ) from e
    try:
        plan = TablePlan.model_validate(payload)
    except ValidationError as e:
        raise PlanProposalError(
            f"Plan failed schema validation: {e}", raw_response=raw, usage=usage,
        ) from e
    return plan, usage
