"""Schema loading helpers shared by the CLI and the web app.

Loads a :class:`~metaextractor.schema.Schema` from raw text (JSON, native
YAML, or LinkML YAML — auto-detected) and enumerates the schemas bundled
with the package so a UI can offer them as ready-made choices.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from metaextractor.schema import Schema


class SchemaLoadError(ValueError):
    """Raised when schema text cannot be parsed into a Schema."""


def _parse_text(text: str, filename: str) -> object:
    """Parse schema text to a Python object, picking JSON vs YAML by suffix
    and falling back to the other parser when the suffix is ambiguous."""
    suffix = Path(filename).suffix.lower()
    if suffix in {".yaml", ".yml"}:
        return _parse_yaml(text)
    if suffix == ".json":
        return json.loads(text)
    # Unknown suffix (e.g. pasted text): try JSON, then YAML.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return _parse_yaml(text)


def _parse_yaml(text: str) -> object:
    try:
        import yaml
    except ImportError as e:  # pragma: no cover - depends on optional extra
        raise SchemaLoadError(
            "YAML/LinkML schemas require the 'linkml' extra: "
            "pip install 'metaextractor[linkml]'"
        ) from e
    return yaml.safe_load(text)


def load_schema_from_text(
    text: str, filename: str = "schema.json", class_name: str | None = None
) -> Schema:
    """Load a Schema from raw text.

    ``filename`` is used only to pick a parser (its suffix). LinkML files
    are auto-detected by content, so ``class_name`` selects the class whose
    slots become fields when a LinkML schema declares more than one.
    """
    try:
        data = _parse_text(text, filename)
    except json.JSONDecodeError as e:
        raise SchemaLoadError(f"Invalid JSON: {e}") from e
    except Exception as e:  # yaml.YAMLError and friends
        raise SchemaLoadError(f"Could not parse schema: {e}") from e

    if not isinstance(data, (dict, list)):
        raise SchemaLoadError("Schema must be a JSON/YAML object or list of fields.")

    from metaextractor.adapters.linkml import is_linkml_schema, linkml_to_schema

    try:
        if isinstance(data, dict) and is_linkml_schema(data):
            return linkml_to_schema(data, class_name=class_name)
        return Schema.from_dict(data)
    except Exception as e:
        raise SchemaLoadError(str(e)) from e


def load_schema_file(path: str | Path, class_name: str | None = None) -> Schema:
    """Load a Schema from a file path."""
    p = Path(path)
    return load_schema_from_text(
        p.read_text(encoding="utf-8"), filename=p.name, class_name=class_name
    )


@dataclass(frozen=True)
class BundledSchema:
    key: str          # stable identifier / filename
    label: str        # human-friendly name for a UI dropdown
    description: str   # one-line summary
    text: str          # the raw schema text


_BUNDLED_META = {
    "cmd_curatedMetagenomicData.linkml.yaml": (
        "curatedMetagenomicData (LinkML)",
        "Full cMD sample-level metadata schema — ~80 fields, ontology-anchored enums.",
    ),
    "example_study_level.json": (
        "Example study-level (JSON)",
        "Small demo schema: participants, age, study design, sample type.",
    ),
}


def bundled_schemas() -> list[BundledSchema]:
    """Return the schemas packaged under ``metaextractor/schemas``."""
    out: list[BundledSchema] = []
    try:
        root = resources.files("metaextractor").joinpath("schemas")
    except (ModuleNotFoundError, FileNotFoundError):
        return out
    for entry in sorted(root.iterdir(), key=lambda p: p.name):
        name = entry.name
        if name.startswith(".") or not entry.is_file():
            continue
        if Path(name).suffix.lower() not in {".json", ".yaml", ".yml"}:
            continue
        label, desc = _BUNDLED_META.get(name, (name, ""))
        out.append(
            BundledSchema(
                key=name,
                label=label,
                description=desc,
                text=entry.read_text(encoding="utf-8"),
            )
        )
    return out
