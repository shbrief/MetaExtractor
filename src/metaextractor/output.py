"""Output schema matching the OutputSchema in the system prompt."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

Granularity = Literal["study_level", "subgroup_level", "sample_level"]
ExtractionType = Literal["directly_stated", "derived", "inferred", "not_reported"]
Confidence = Literal["high", "medium", "low"]

#: Provenance slots that locate a value in the source; meaningless for an absent value.
LOCATION_SLOTS = ("evidence_quote", "section")


def _is_absent(v: Any) -> bool:
    """``None``, empty, or a case-variant of ``not_reported`` / ``not reported``."""
    if v is None:
        return True
    if isinstance(v, (list, dict)):
        return not v
    return isinstance(v, str) and v.strip().lower().replace(" ", "_") in ("", "not_reported")


class FieldResult(BaseModel):
    value: Any
    by_subgroup: dict[str, Any] | None = None
    unit: str | None = None
    normalized_value: Any = None
    normalized_unit: str | None = None
    extraction_type: ExtractionType
    confidence: Confidence
    #: Required for a reported value; may be null when the value is ``not_reported``.
    evidence_quote: str | None = None
    #: Required for a reported value; may be null when the value is ``not_reported``.
    section: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _location_required_for_reported_values(self) -> FieldResult:
        if _is_absent(self.value):
            return self
        missing = [s for s in LOCATION_SLOTS if getattr(self, s) is None]
        if missing:
            raise ValueError(f"{', '.join(missing)} must be a string for a reported value")
        return self


class TableSelection(BaseModel):
    """Deterministic per-table relevance verdict for a supplementary table.

    Provenance for downstream harmonization: which tables were fed to the
    per-sample pipeline, which were rejected as measurement matrices or for
    low schema relevance, and — via ``matched_fields`` — which column fed
    which schema field.
    """

    name: str
    selected: bool
    score: float
    is_matrix: bool = False
    matched_fields: dict[str, str] = Field(default_factory=dict)  # schema field -> source column
    reasons: list[str] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    paper_id: str | None = None
    granularity: Granularity
    subgroups: list[str] = Field(default_factory=list)
    fields: dict[str, FieldResult]
    samples: list[dict[str, Any]] = Field(default_factory=list)
    #: Parallel to ``samples``: ``{field: source}`` per sample, recording where each
    #: cell came from (table/manifest cell, model, fan-out, or a derivation rule).
    #: See ``metaextractor.sample_rules`` for the source descriptors.
    sample_provenance: list[dict[str, str]] = Field(default_factory=list)
    table_selection: list[TableSelection] = Field(default_factory=list)
    extraction_warnings: list[str] = Field(default_factory=list)
