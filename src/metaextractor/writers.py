"""Output writers. JSON is the primary form; CSV is a flat projection
suitable for spreadsheets and downstream tabular tools."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from metaextractor.output import ExtractionResult


def cell_value(cell: Any, *, prefer_normalized: bool = False) -> Any:
    """Unwrap a sample cell that carries the verbatim/normalized split.

    A per-sample cell is normally the verbatim scalar the extractor emitted.
    Downstream harmonization may replace it with a
    ``{"value": <verbatim>, "normalized_value": <canonical>}`` object; this
    returns the verbatim ``value`` by default, or ``normalized_value``
    (falling back to ``value`` when absent) when ``prefer_normalized``.
    """
    if isinstance(cell, dict) and "value" in cell:
        if prefer_normalized:
            norm = cell.get("normalized_value")
            return norm if norm is not None else cell.get("value")
        return cell.get("value")
    return cell


def _stringify(value: Any, *, prefer_normalized: bool = False) -> str:
    """Render a field value for a CSV cell. Lists become '; '-joined."""
    value = cell_value(value, prefer_normalized=prefer_normalized)
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(_stringify(v, prefer_normalized=prefer_normalized) for v in value)
    return str(value)


def to_csv(
    result: ExtractionResult,
    path: str | Path,
    include_provenance: bool = False,
) -> None:
    """Write the extraction as CSV.

    Row layout depends on granularity:
      - study_level    : one row, one column per field.
      - subgroup_level : one row per subgroup; per-field value taken from
                         `by_subgroup` when present, else the top-level value.
      - sample_level   : one row per entry in `samples`.

    If ``include_provenance`` is True, each field gets three extra
    columns: ``<field>__evidence``, ``<field>__section``, ``<field>__confidence``.
    For sample-level output these describe the *study-level* claim the field
    was extracted from, and each field additionally gets ``<field>__source``:
    the per-cell origin recorded in ``sample_provenance`` (a table/manifest
    column, the model, a fan-out rule, or an age rule).
    """
    path = Path(path)
    field_names = list(result.fields.keys())

    if result.granularity == "sample_level":
        rows = [
            {"paper_id": result.paper_id, **{k: _stringify(v) for k, v in sample.items()}}
            for sample in result.samples
        ]
        data_cols = sorted({k for r in rows for k in r if k != "paper_id"})
        header = ["paper_id"]
        if not include_provenance:
            header += data_cols
        else:
            prov = result.sample_provenance
            for i, row in enumerate(rows):
                p = prov[i] if i < len(prov) else {}
                for col in data_cols:
                    row[f"{col}__source"] = p.get(col, "")
                    fr = result.fields.get(col)
                    if fr is not None:
                        row[f"{col}__evidence"] = fr.evidence_quote
                        row[f"{col}__section"] = fr.section
                        row[f"{col}__confidence"] = fr.confidence
            for col in data_cols:
                header.append(col)
                header.append(f"{col}__source")
                if col in result.fields:
                    header.extend([f"{col}__evidence", f"{col}__section", f"{col}__confidence"])
        _write(path, header, rows)
        return

    columns = ["paper_id"]
    if result.granularity == "subgroup_level":
        columns.append("subgroup")
    for name in field_names:
        columns.append(name)
        if include_provenance:
            columns.extend([f"{name}__evidence", f"{name}__section", f"{name}__confidence"])

    rows: list[dict[str, str]] = []
    subgroups = result.subgroups if result.granularity == "subgroup_level" else [None]

    for sg in subgroups:
        row: dict[str, str] = {"paper_id": result.paper_id or ""}
        if sg is not None:
            row["subgroup"] = sg
        for name, field in result.fields.items():
            if sg is not None and field.by_subgroup and sg in field.by_subgroup:
                row[name] = _stringify(field.by_subgroup[sg])
            else:
                row[name] = _stringify(field.value)
            if include_provenance:
                row[f"{name}__evidence"] = field.evidence_quote
                row[f"{name}__section"] = field.section
                row[f"{name}__confidence"] = field.confidence
        rows.append(row)

    _write(path, columns, rows)


def _write(path: Path, header: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
