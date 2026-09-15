"""Structural reading of supplementary tables: row-0 parse or an LLM structure plan.

Supplementary tables from biomedical papers often arrive with structures
the default "row-0 is the header" parser can't make sense of: title rows,
stacked multi-row headers, super-headers that group columns, sample types
spread horizontally across columns. This module handles those cases without
letting the LLM write cell values or choose column names.

The flow per kept supplementary table:

    1. ``is_feature_matrix`` rejects abundance / presence matrices
       (taxa × samples or feature × samples).

    2. ``needs_structure_plan`` decides deterministically whether row 0 is a
       clean single header. If so, the table is read as parsed and no model
       call is made.

    3. Otherwise ``propose_plan`` asks the LLM, given the first ~20 raw rows
       (not the target schema), for a structural :class:`TablePlan`: which rows
       form the header, where data starts, which rows are notes, and whether to
       melt wide-format column groups into one row per sample.

    4. ``execute_plan`` applies the plan in pure Python. Every kept column is
       named by its own merged header text; values are copied by index. Same
       plan + same raw grid → same output, every time.

Mapping header text to schema fields happens afterwards, in the configured
column mapper (MetaHarmonizer SchemaMapper or the lexical cascade).

Plan-execution failures (bad row or column references) surface as
:class:`PlanExecutionError` so the caller can fall back to the row-0 parse.
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
    """Fraction of (post-col-0) headers that look like sample IDs.

    Requires at least one digit in the header — without this guard,
    snake_case schema field names like ``donor_id`` / ``bristol_stool_scale``
    trip the alphanumeric-joined-by-``_`` pattern just as readily as
    real sample IDs (which essentially always carry digits, e.g.
    ``SRR12345``, ``S00A4-0001``, ``PD_1``).
    """
    candidates = [h for h in headers[1:] if h]
    if not candidates:
        return 0.0
    hits = sum(
        1 for h in candidates
        if _SAMPLE_ID_RE.match(h) and any(c.isdigit() for c in h)
    )
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


class MeltGroup(BaseModel):
    """One value column produced by melting wide-format sub-columns.

    ``value_label`` names the output column in the table's own wording (e.g. the
    super-header above the grouped columns); ``sources`` maps each category label
    (e.g. ``"Mother"``) to the 0-based raw column index whose values feed it.
    """

    value_label: str
    sources: dict[str, int]


class Melt(BaseModel):
    """Long-format reshape spec for wide tables.

    All :class:`MeltGroup` entries share the same set of category keys; each category
    produces one output row per data row, with each group contributing its own
    value column. ``category_label`` names the category column in the table's own
    wording.
    """

    category_label: str
    groups: list[MeltGroup]
    skip_missing_categories: bool = True


class TablePlan(BaseModel):
    """LLM-proposed **structural** reading of a raw cell grid.

    The plan says where the header and the data are, which rows are notes, and
    whether sample-distinguishing columns must be melted. It does not select,
    name, or map columns: every kept column is named by its own merged header
    text, and mapping header text to schema fields is done afterwards by the
    configured column mapper. Column references are 0-based raw-column indices.
    """

    header_rows: list[int]
    header_merge_sep: str = " | "
    data_starts_at: int
    melt: Melt | None = None
    drop_rows: list[int] = Field(default_factory=list)
    notes: str | None = None


# --------------------------------------------------------------------------- #
# Simple tables: no plan needed
# --------------------------------------------------------------------------- #


_NUMERIC_CELL_RE = re.compile(r"^[-+]?(\d+([.,]\d+)?|\.\d+)([eE][-+]?\d+)?%?$")
_HEADER_DELIM_RE = re.compile(r"[\s_.\-|/()]+")


def _is_numeric_cell(cell: str) -> bool:
    return bool(_NUMERIC_CELL_RE.match(cell.strip()))


def _repeated_column_groups(headers: list[str]) -> str | None:
    """Two tags each attached to the same two or more stems (``age_mother``,
    ``age_infant``, ``bmi_mother``, ``bmi_infant``): a wide layout to melt."""
    tag_stems: dict[str, set[str]] = {}
    for h in headers:
        parts = [p for p in _HEADER_DELIM_RE.split(h.strip().lower()) if p]
        if len(parts) < 2:
            continue
        for tag, stem in ((parts[-1], " ".join(parts[:-1])), (parts[0], " ".join(parts[1:]))):
            tag_stems.setdefault(tag, set()).add(stem)
    tags = [t for t, stems in tag_stems.items() if len(stems) >= 2 and not _is_numeric_cell(t)]
    for i, a in enumerate(tags):
        for b in tags[i + 1:]:
            if len(tag_stems[a] & tag_stems[b]) >= 2:
                return f"repeated column groups ({a!r}/{b!r})"
    return None


def needs_structure_plan(table: Table) -> tuple[bool, str]:
    """Does this table need an LLM structure plan, or is row 0 a clean header?

    A table is read directly (row 0 = header, the rest = data) when row 0 has at
    least two labels, no blank cell inside its span, no duplicate or numeric-looking
    labels; row 1 is not a second header over numeric columns; and no column group
    repeats across tags (a wide layout). Otherwise a structure plan is requested.
    Returns ``(needs_plan, reason)``.
    """
    raw = table.raw_rows
    if len(raw) < 2:
        return True, "fewer than two rows"
    width = max(len(r) for r in raw)
    header = list(raw[0]) + [""] * (width - len(raw[0]))
    # The header must label every column that holds data (a super-header leaves
    # blanks under its span, including at the end of the row).
    used = max((i for r in raw[:22] for i, c in enumerate(r) if c.strip()), default=-1)
    labels = [c.strip() for c in header[: used + 1]]
    nonempty = [c for c in labels if c]
    if len(nonempty) < 2:
        return True, "row 0 has fewer than two labels"
    if len(nonempty) < len(labels):
        return True, "blank cells inside the header span (stacked or merged header)"
    if len({c.lower() for c in nonempty}) < len(nonempty):
        return True, "duplicate header labels"
    if sum(_is_numeric_cell(c) for c in nonempty) > 0.2 * len(nonempty):
        return True, "numeric header labels"
    body = raw[2:22]
    if body:
        numeric_cols = []
        for j in range(width):
            vals = [r[j] for r in body if j < len(r) and r[j].strip()]
            if vals and sum(_is_numeric_cell(v) for v in vals) >= 0.8 * len(vals):
                numeric_cols.append(j)
        if numeric_cols:
            row1 = raw[1]
            textual = sum(1 for j in numeric_cols
                          if j < len(row1) and row1[j].strip() and not _is_numeric_cell(row1[j]))
            if textual >= 0.5 * len(numeric_cols):
                return True, "row 1 looks like a second header row"
    wide = _repeated_column_groups(nonempty)
    if wide:
        return True, wide
    return False, "single header row"


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
    """Forward-fill blanks in the upper header rows, then join columnwise.

    Forward-fill propagates super-header labels (which export as empty cells
    under their span in xlsx/csv) so each column gets the full stacked label,
    e.g. ``"DNA (ng/µl) | Mother"``. The last (leaf) row is not filled: a blank
    leaf label belongs to that column alone.
    """
    if not header_grid:
        return []
    width = max(len(r) for r in header_grid)
    filled: list[list[str]] = []
    for ri, row in enumerate(header_grid):
        row = list(row) + [""] * (width - len(row))
        last = ""
        new_row = []
        for cell in row:
            cell = cell.strip()
            if cell:
                last = cell
                new_row.append(cell)
            else:
                new_row.append(last if ri < len(header_grid) - 1 else "")
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


def _unique_names(names: list[str]) -> list[str]:
    """Blank names become ``col_<i>``; repeats get ``_1``, ``_2``… (as the row-0 parser)."""
    seen: dict[str, int] = {}
    out: list[str] = []
    for i, n in enumerate(names):
        n = n or f"col_{i}"
        if n in seen:
            seen[n] += 1
            n = f"{n}_{seen[n]}"
        else:
            seen[n] = 0
        out.append(n)
    return out


def execute_plan(table: Table, plan: TablePlan) -> Table:
    """Apply a structural :class:`TablePlan` to a table's raw grid; return a new Table.

    Every raw column that is not a melt source is kept, named by its merged header
    text; melted columns become the category column plus one value column per group.
    Cell values pass through verbatim — no casting, normalization, or invented data.
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
    melt_sources: set[int] = set()
    if plan.melt:
        for g in plan.melt.groups:
            for cat, src in g.sources.items():
                if src < 0 or src >= n_cols:
                    raise PlanExecutionError(
                        f"Table {table.name!r}: melt.{g.value_label}.sources[{cat!r}] references "
                        f"col={src}, out of range (n_cols={n_cols})."
                    )
                melt_sources.add(src)

    header = _merge_header_rows([raw[ri] for ri in plan.header_rows], plan.header_merge_sep)
    header += [""] * (n_cols - len(header))
    kept = [ci for ci in range(n_cols) if ci not in melt_sources]
    melt_labels = ([plan.melt.category_label] + [g.value_label for g in plan.melt.groups]
                   if plan.melt and plan.melt.groups else [])
    names = _unique_names([header[ci] for ci in kept] + melt_labels)
    kept_names, melt_names = names[: len(kept)], names[len(kept):]

    drop_row_set = set(plan.drop_rows)
    data = [raw[ri] for ri in range(plan.data_starts_at, n_rows) if ri not in drop_row_set]
    data = [r + [""] * max(0, n_cols - len(r)) for r in data]

    out_rows: list[dict[str, Any]] = []
    if melt_names:
        cat_name, value_names = melt_names[0], melt_names[1:]
        all_cats = list(dict.fromkeys(c for g in plan.melt.groups for c in g.sources))
        for row in data:
            base = {name: row[ci] for name, ci in zip(kept_names, kept)}
            for cat in all_cats:
                values = {vn: (row[g.sources[cat]] if cat in g.sources else "")
                          for vn, g in zip(value_names, plan.melt.groups)}
                if plan.melt.skip_missing_categories and not any(v != "" for v in values.values()):
                    continue
                out_rows.append({**base, cat_name: cat, **values})
    else:
        for row in data:
            out_rows.append({name: row[ci] for name, ci in zip(kept_names, kept)})

    return Table(
        name=table.name,
        source=table.source,
        columns=kept_names + melt_names,
        rows=out_rows,
        raw_rows=table.raw_rows,
    )


# --------------------------------------------------------------------------- #
# LLM proposer
# --------------------------------------------------------------------------- #


_PROPOSE_SYSTEM = """You are a structural-layout analyst for biomedical supplementary tables.

You receive the first rows of one supplementary table from a paper. Describe how
to read its layout so that each output row corresponds to one biological sample.

You describe STRUCTURE ONLY. You do not select, rename, or interpret columns:
every column keeps the text of its own header cell(s), and cell values pass
through unchanged when the plan is executed.

Column references are integer column indices (0-based). The rendered grid
shows them as the labels c0, c1, c2, … in row 0 of the TSV display. Use
those numbers directly — do not reference columns by their text label.

Output strictly valid JSON matching this shape:

{
  "header_rows": [<int>, ...],
  "header_merge_sep": " | ",
  "data_starts_at": <int>,
  "melt": null | {
    "category_label": "<label>",
    "groups": [
      {
        "value_label": "<label>",
        "sources": {"<category>": <int>, ...}
      }
    ],
    "skip_missing_categories": true
  },
  "drop_rows": [<int>, ...],
  "notes": "<one-line rationale>"
}

Rules:
- header_rows are 0-based row indices of the header. Use 1 row for flat headers;
  use 2-3 rows when super-headers stack above leaf column names. Title or caption
  rows above the header are neither header_rows nor data.
- data_starts_at is the index of the first data row (typically one past
  the last header row).
- drop_rows: footnote, legend, or summary rows interleaved with or after the data.
- melt: only when a sample-distinguishing attribute — sample type (e.g.
  Mother/Infant/Milk), body site, subject role, time point, or compartment — is
  spread horizontally across columns, so that one row holds several samples.
  Each group's "sources" maps the category (as written in the header) to the
  column index whose values belong to that category. category_label and
  value_label must use wording taken from the table's own header cells (for
  example the super-header above the grouped columns). Use null when each row
  is already one sample.
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
    max_tokens: int = 2048,
    n_rows: int = 20,
    max_tokens_ceiling: int = 16384,
    calls: list[dict] | None = None,
) -> tuple[TablePlan, dict[str, int]]:
    """Ask the LLM to propose a :class:`TablePlan` for ``table``.

    Returns ``(plan, usage)`` where ``usage`` is the token usage summed over
    the call and any re-request (the keys match :class:`MetaExtractor.last_usage`).
    A response that stops at ``max_tokens`` is re-requested with a doubled
    budget up to ``max_tokens_ceiling`` (kept non-streaming-safe). When ``calls``
    is given, one record per API call is appended to it; the final record carries
    the parsed plan (or the raw response when it could not be parsed).
    The model is not given the target schema: the plan is structural only.
    """
    grid = _render_grid_for_llm(table.raw_rows, n_rows)
    user = (
        f"Table name: {table.name}\n"
        f"Total raw rows: {len(table.raw_rows)}\n\n"
        f"First {min(n_rows, len(table.raw_rows))} rows (TSV, row index in column 0):\n\n"
        f"{grid}\n"
    )
    usage = {"input_tokens": 0, "cache_creation_input_tokens": 0,
             "cache_read_input_tokens": 0, "output_tokens": 0, "n_calls": 0}
    budget = max_tokens
    while True:
        try:
            msg = client.messages.create(
                model=model,
                max_tokens=budget,
                system=_PROPOSE_SYSTEM,
                messages=[{"role": "user", "content": user}],
            )
        except Exception as e:
            # Covers auth errors (TypeError from missing API key), network
            # failures, rate-limit errors, etc. — anything that means we
            # cannot get a plan from the LLM.  The caller falls back to the
            # default row-0-header parse.
            raise PlanProposalError(
                f"LLM call failed: {type(e).__name__}: {e}",
                raw_response=None,
                usage=usage,
            ) from e
        u = msg.usage
        for k in ("input_tokens", "cache_creation_input_tokens",
                  "cache_read_input_tokens", "output_tokens"):
            usage[k] += getattr(u, k, 0) or 0
        usage["n_calls"] += 1
        stop_reason = getattr(msg, "stop_reason", None)
        if calls is not None:
            calls.append({"purpose": "table_plan", "table": table.name, "max_tokens": budget,
                          "stop_reason": stop_reason,
                          "output_tokens": getattr(u, "output_tokens", None)})
        if stop_reason == "max_tokens" and budget < max_tokens_ceiling:
            budget = min(budget * 2, max_tokens_ceiling)
            continue
        break
    raw = "".join(b.text for b in msg.content if b.type == "text").strip()
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
        if calls is not None:
            calls[-1]["raw_response"] = raw
        raise PlanProposalError(
            f"Plan response was not valid JSON: {e}", raw_response=raw, usage=usage,
        ) from e
    if calls is not None:
        calls[-1]["plan"] = payload
    try:
        plan = TablePlan.model_validate(payload)
    except ValidationError as e:
        raise PlanProposalError(
            f"Plan failed schema validation: {e}", raw_response=raw, usage=usage,
        ) from e
    return plan, usage
