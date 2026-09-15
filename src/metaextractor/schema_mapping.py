"""Column-to-schema-field mapping backends for the deterministic table path.

Two backends share one interface, ``map_table(columns, rows, schema_field_names,
exclude_targets=()) -> ColumnMapping``:

* :class:`LexicalColumnMapper` — :func:`metaextractor.column_mapper.map_columns`
  (exact → normalized → alias → fuzzy on header text). No dependencies.
* :class:`SchemaMapperColumnMapper` — MetaHarmonizer's SchemaMapper
  (``SchemaMapEngine``), a configurable subset of stages 1–3: (1) dictionary matching
  on header text (exact and fuzzy, standard fields and an alias dictionary), (2) value
  matching against the schema's allowed values, (3) embedding-based field matching.
  The LLM stage is never used, and the NCI ontology matcher is disabled so that
  extraction from a frozen retrieval stays offline.

SchemaMapper returns a ranked candidate for most columns, including candidates
whose score is below the threshold of the method that produced them. A candidate
is accepted only when its score reaches that method's threshold, taken from
MetaHarmonizer's own settings (``Settings``: ``fuzzy_thresh``,
``value_percentage_thresh``, ``numeric_thresh``, ``field_alias_thresh``; exact
matches score 1.0). Two columns claiming one field: the higher score wins (then the
earlier column); the other stays unmapped and is recorded as a collision.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable

from metaextractor.column_mapper import ColumnMapping, map_columns


class LexicalColumnMapper:
    """The lexical cascade of :func:`metaextractor.column_mapper.map_columns`."""

    name = "lexical"

    def __init__(self, aliases: dict[str, str] | None = None):
        self.aliases = aliases

    def map_table(self, columns: list[str], rows: list[dict[str, Any]],
                  schema_field_names: list[str],
                  exclude_targets: Iterable[str] = ()) -> ColumnMapping:
        excluded = set(exclude_targets)
        m = map_columns(columns, [f for f in schema_field_names if f not in excluded],
                        aliases=self.aliases)
        return m

    def describe(self) -> dict[str, Any]:
        return {"backend": self.name}


def _sha256(path: str | Path | None) -> str | None:
    if not path:
        return None
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class _NoOntologyMatcher:
    """Stand-in for SchemaMapper's NCI ontology matcher (which calls a web service)."""

    def match(self, col: str) -> list:
        return []


class SchemaMapperColumnMapper:
    """MetaHarmonizer SchemaMapper (stages 1–3, offline) as a column mapper.

    ``target_schema_path`` is SchemaMapper's target table (``field_name,is_numeric_field``);
    ``alias_dict_path`` and ``value_dict_path`` are its alias dictionary (CSV) and
    allowed-values dictionary (JSON). The engine is built once and reused per table.
    """

    name = "schemamapper"

    def __init__(self, target_schema_path: str | Path, alias_dict_path: str | Path | None = None,
                 value_dict_path: str | Path | None = None, stages: tuple[int, ...] = (1, 2, 3)):
        # SchemaMapper writes result CSVs under SM_OUTPUT_DIR (read at import); keep them
        # out of the MetaHarmonizer data directory. map_table does not write any.
        os.environ.setdefault("SM_OUTPUT_DIR", tempfile.mkdtemp(prefix="metaextractor_sm_"))
        from metaharmonizer.models.schema_mapper.engine import SchemaMapEngine

        if not set(stages) <= {1, 2, 3}:
            raise ValueError(f"SchemaMapper stages must be a subset of (1, 2, 3), got {stages}")
        self.stages = tuple(sorted(stages))
        self.paths = {"target_schema": str(target_schema_path),
                      "alias_dict": str(alias_dict_path) if alias_dict_path else "",
                      "value_dict": str(value_dict_path) if value_dict_path else ""}
        # The engine reads an input file at construction; seed it with a one-cell table.
        with tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False) as fh:
            fh.write("placeholder\nx\n")
            seed = fh.name
        try:
            self.engine = SchemaMapEngine(
                seed, schema=None, mode="manual", target_schema_path=self.paths["target_schema"],
                alias_dict_path=self.paths["alias_dict"], value_dict_path=self.paths["value_dict"])
        finally:
            os.unlink(seed)
        self.engine.ontology = _NoOntologyMatcher()
        st = self.engine.settings
        self.thresholds = {
            "std_exact": 1.0, "alias_exact": 1.0,
            "std_fuzzy": st.fuzzy_thresh / 100, "alias_fuzzy": st.fuzzy_thresh / 100,
            "value": st.value_percentage_thresh, "ontology": st.value_percentage_thresh,
            "numeric": st.numeric_thresh, "semantic": st.field_alias_thresh,
        }

    def _candidate(self, col: str) -> dict[str, Any]:
        """SchemaMapper's cascade for one column: the first enabled stage that returns anything."""
        e = self.engine
        stage_fns = {1: e.stage1_match, 2: e.stage2_match, 3: e.stage3_match}
        for stage in self.stages:
            row = stage_fns[stage](col)
            if row:
                return row
        return {}

    def map_table(self, columns: list[str], rows: list[dict[str, Any]],
                  schema_field_names: list[str],
                  exclude_targets: Iterable[str] = ()) -> ColumnMapping:
        import pandas as pd

        allowed = set(schema_field_names) - set(exclude_targets)
        e = self.engine
        e.df = pd.DataFrame([[str(r.get(c, "")) for c in columns] for r in rows],
                            columns=columns, dtype=str)
        e._col_values_cache, e._col_freq_cache = {}, {}

        accepted: dict[str, tuple[str, float, str]] = {}   # column -> (field, score, tier)
        result = ColumnMapping()
        for col in columns:
            row = self._candidate(col)
            field, score = row.get("match1"), float(row.get("match1_score") or 0.0)
            method = row.get("method", "")
            if not field or field not in allowed or score < self.thresholds.get(method, 1.01):
                result.unmapped.append(col)
                continue
            accepted[col] = (field, score, f"schemamapper:{row.get('stage')}:{method}({score:.3f})")

        by_field: dict[str, list[str]] = {}
        for col, (field, _, _) in accepted.items():
            by_field.setdefault(field, []).append(col)
        for field, cols in by_field.items():
            winner = max(cols, key=lambda c: (accepted[c][1], -columns.index(c)))
            for col in cols:
                if col == winner:
                    result.mapped[col] = field
                    result.tier_used[col] = accepted[col][2]
                else:
                    result.collisions.append((col, field))
                    result.unmapped.append(col)
        return result

    def describe(self) -> dict[str, Any]:
        try:
            from importlib.metadata import version
            mh_version = version("metaharmonizer")
        except Exception:  # pragma: no cover
            mh_version = None
        return {"backend": self.name, "metaharmonizer_version": mh_version,
                "thresholds": self.thresholds, "stages": list(self.stages),
                "disabled": "stage 4 (LLM), stage-2 NCI ontology matcher",
                **{f"{k}_path": v for k, v in self.paths.items()},
                **{f"{k}_sha256": _sha256(v) for k, v in self.paths.items()}}


__all__ = ["LexicalColumnMapper", "SchemaMapperColumnMapper"]
