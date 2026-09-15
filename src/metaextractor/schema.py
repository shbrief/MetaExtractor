"""Input schema: the user-supplied description of fields to extract."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field as PydField, field_validator

FieldType = Literal["string", "number", "enum", "boolean", "list"]
#: Whether a field describes the whole study or an individual sample. Governs
#: deterministic fan-out (``metaextractor.sample_rules``); ``None`` = undeclared.
FieldScope = Literal["study", "sample"]


class Field(BaseModel):
    name: str
    description: str
    type: FieldType
    allowed_values: list[str] | None = None
    value_descriptions: dict[str, str] | None = None
    unit: str | None = None
    target_unit: str | None = None
    required: bool = False
    scope: FieldScope | None = None
    #: For a ``sample``-scoped field: a single study-level value may be written to every
    #: record of a cohort reported without subgroups (e.g. a specimen type stated once
    #: for all samples). Without it, a sample-scoped field is filled only from
    #: sample-level evidence. Governs fan-out only; not sent to the model.
    propagate_study_value: bool = False
    #: Name of the field this field is the unit of (e.g. ``age_unit`` → ``age``). A
    #: study- or subgroup-level unit is written only to records that carry that value.
    #: Governs fan-out only; not sent to the model.
    unit_of: str | None = None

    @field_validator("allowed_values")
    @classmethod
    def _enum_requires_allowed(cls, v, info):
        if info.data.get("type") == "enum" and not v:
            raise ValueError("enum fields require non-empty allowed_values")
        return v


class Schema(BaseModel):
    fields: list[Field] = PydField(min_length=1)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | list[dict[str, Any]]) -> "Schema":
        if isinstance(data, list):
            return cls(fields=[Field(**f) for f in data])
        if "fields" in data:
            return cls(fields=[Field(**f) for f in data["fields"]])
        raise ValueError("Schema dict must contain 'fields' key or be a list of fields")

    def to_prompt_json(self) -> dict[str, Any]:
        # ``scope``, ``propagate_study_value``, and ``unit_of`` drive deterministic post-processing only;
        # they are not sent to the model.
        return {"fields": [f.model_dump(exclude_none=True, exclude={"scope", "propagate_study_value", "unit_of"})
                           for f in self.fields]}
