"""Input schema: the user-supplied description of fields to extract."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field as PydField, field_validator

FieldType = Literal["string", "number", "enum", "boolean", "list"]


class Field(BaseModel):
    name: str
    description: str
    type: FieldType
    allowed_values: list[str] | None = None
    unit: str | None = None
    target_unit: str | None = None
    required: bool = False

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
        return {"fields": [f.model_dump(exclude_none=True) for f in self.fields]}
