"""Output writers. JSON is the primary form; CSV is a flat projection
suitable for spreadsheets and downstream tabular tools."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from metaextractor.output import ExtractionResult


def _stringify(value: Any) -> str:
    """Render a field value for a CSV cell. Lists become '; '-joined."""
    if value is None:
        return ""
    if isinstance(value, list):
        return "; ".join(_stringify(v) for v in value)
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
    """
    path = Path(path)
    field_names = list(result.fields.keys())

    if result.granularity == "sample_level":
        rows = [
            {"paper_id": result.paper_id, **{k: _stringify(v) for k, v in sample.items()}}
            for sample in result.samples
        ]
        header = ["paper_id"] + sorted({k for r in rows for k in r if k != "paper_id"})
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
