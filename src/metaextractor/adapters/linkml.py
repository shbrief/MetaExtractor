"""LinkML → metaextractor.Schema adapter.

Consumes a LinkML schema (parsed YAML/JSON dict) and emits a Schema whose
fields correspond to the slots of a chosen class.

Mapping:
  slot.description           -> field.description
  slot.range == integer|float -> "number"
  slot.range == boolean      -> "boolean"
  slot.range == <name>_enum  -> "enum" + allowed_values (keys) and
                                value_descriptions ({key: "description (meaning)"})
                                from enums[<name>_enum].permissible_values
  slot.range == string|<other>|<missing> -> "string"
  slot.multivalued == True   -> "list"   (overrides scalar typing)
  slot.required              -> field.required
  slot.unit / slot.ucum_unit -> field.unit
"""
from __future__ import annotations

from typing import Any

from metaextractor.schema import Field, Schema

LINKML_NUMERIC = {"integer", "int", "float", "double", "decimal"}
LINKML_BOOL = {"boolean", "bool"}
LINKML_STRING = {"string", "str", "uri", "uriorcurie", "ncname", "date", "datetime"}


class LinkMLAdapterError(ValueError):
    pass


def is_linkml_schema(data: dict[str, Any]) -> bool:
    return isinstance(data, dict) and any(k in data for k in ("classes", "slots", "enums"))


def _enum_values(
    enums: dict[str, Any], enum_name: str
) -> tuple[list[str], dict[str, str]]:
    """Return (keys, key -> "description (meaning)") for an enum.

    The descriptions map is sparse: only keys whose permissible_value carries
    a `description` and/or `meaning` appear. Empty when the enum lists bare
    keys only — which is the common case for hand-authored LinkML.
    """
    enum_def = enums.get(enum_name) or {}
    pv = enum_def.get("permissible_values") or {}
    keys: list[str] = []
    descs: dict[str, str] = {}
    if isinstance(pv, dict):
        for k, v in pv.items():
            key = str(k)
            keys.append(key)
            label = _pv_label(v)
            if label:
                descs[key] = label
    elif isinstance(pv, list):
        for v in pv:
            if isinstance(v, dict):
                key = str(v.get("text") or v.get("name") or v)
                keys.append(key)
                label = _pv_label(v)
                if label:
                    descs[key] = label
            else:
                keys.append(str(v))
    return keys, descs


def _pv_label(pv: Any) -> str:
    """Format a permissible_value's description and meaning into one string.

    Returns "" when nothing extra is available (bare keys, None, etc.).
    """
    if not isinstance(pv, dict):
        return ""
    desc = (pv.get("description") or pv.get("title") or "").strip()
    meaning = (pv.get("meaning") or "").strip()
    if desc and meaning:
        return f"{desc} ({meaning})"
    if meaning:
        return f"({meaning})"
    return desc


def _slot_to_field(name: str, slot: dict[str, Any], enums: dict[str, Any]) -> Field:
    raw_desc = slot.get("description")
    desc = (raw_desc.strip() if isinstance(raw_desc, str) else "") or name
    range_ = slot.get("range")
    multivalued = bool(slot.get("multivalued"))
    allowed_values: list[str] | None = None
    value_descriptions: dict[str, str] | None = None

    if range_ in enums:
        allowed_values, vdescs = _enum_values(enums, range_)
        if allowed_values:
            ftype = "enum"
            value_descriptions = vdescs or None
        else:
            # Dynamic enum (LinkML `reachable_from` / ontology subtree) with no
            # static permissible_values — nothing to enumerate, so treat it as
            # free text rather than emitting an invalid empty-allowed_values enum.
            ftype = "string"
            allowed_values = None
    elif isinstance(range_, str) and range_ in LINKML_NUMERIC:
        ftype = "number"
    elif isinstance(range_, str) and range_ in LINKML_BOOL:
        ftype = "boolean"
    else:
        ftype = "string"

    if multivalued:
        ftype = "list"
        allowed_values = None
        value_descriptions = None

    return Field(
        name=name,
        description=desc,
        type=ftype,  # type: ignore[arg-type]
        allowed_values=allowed_values,
        value_descriptions=value_descriptions,
        unit=slot.get("unit") or slot.get("ucum_unit"),
        required=bool(slot.get("required", False)),
    )


def linkml_to_schema(data: dict[str, Any], class_name: str | None = None) -> Schema:
    """Convert a parsed LinkML schema dict into a metaextractor Schema.

    class_name: name of the class whose slots become fields. Defaults to
    the single class in the file; required if multiple classes exist.
    """
    if not is_linkml_schema(data):
        raise LinkMLAdapterError("Input does not look like a LinkML schema")

    classes = data.get("classes") or {}
    slots_root = data.get("slots") or {}
    enums = data.get("enums") or {}

    if class_name is None:
        if len(classes) == 1:
            class_name = next(iter(classes))
        elif len(classes) == 0:
            raise LinkMLAdapterError("LinkML schema defines no classes")
        else:
            raise LinkMLAdapterError(
                f"Multiple classes ({sorted(classes)}); pass class_name=..."
            )

    cls = classes.get(class_name)
    if cls is None:
        raise LinkMLAdapterError(f"Class '{class_name}' not found in schema")

    slot_names = cls.get("slots") or []
    attrs = cls.get("attributes") or {}

    fields: list[Field] = []
    for sname in slot_names:
        sdef = slots_root.get(sname) or attrs.get(sname) or {}
        fields.append(_slot_to_field(sname, sdef, enums))
    for sname, sdef in attrs.items():
        if sname not in slot_names:
            fields.append(_slot_to_field(sname, sdef or {}, enums))

    if not fields:
        raise LinkMLAdapterError(f"Class '{class_name}' has no slots/attributes")

    return Schema(fields=fields)
