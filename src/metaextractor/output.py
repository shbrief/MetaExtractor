"""Output schema matching the OutputSchema in the system prompt."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Granularity = Literal["study_level", "subgroup_level", "sample_level"]
ExtractionType = Literal["directly_stated", "derived", "inferred", "not_reported"]
Confidence = Literal["high", "medium", "low"]


class FieldResult(BaseModel):
    value: Any
    by_subgroup: dict[str, Any] | None = None
    unit: str | None = None
    normalized_value: Any = None
    normalized_unit: str | None = None
    extraction_type: ExtractionType
    confidence: Confidence
    evidence_quote: str
    section: str
    notes: str | None = None


class ExtractionResult(BaseModel):
    paper_id: str | None = None
    granularity: Granularity
    subgroups: list[str] = Field(default_factory=list)
    fields: dict[str, FieldResult]
    samples: list[dict[str, Any]] = Field(default_factory=list)
    extraction_warnings: list[str] = Field(default_factory=list)
