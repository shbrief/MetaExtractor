"""Tests for metaextractor.adapters.linkml — LinkML → Schema conversion.

Regression coverage for two robustness bugs that crashed real ontology-bound
schemas (e.g. the curatedMetagenomicData / cBioPortal LinkML schemas):

1. A LinkML enum defined by `reachable_from` (a dynamic ontology subtree) has no
   static `permissible_values`, so it must NOT become an empty-`allowed_values`
   enum field (which fails validation). It should degrade to `string` (or `list`
   when multivalued).
2. A slot whose `description` is not a string (YAML `.nan` -> float) must not
   crash the `.strip()` call.
"""
from metaextractor.adapters.linkml import linkml_to_schema


def _schema(slots: dict, enums: dict | None = None) -> dict:
    return {
        "classes": {"Rec": {"slots": list(slots)}},
        "slots": slots,
        "enums": enums or {},
    }


def test_dynamic_reachable_from_enum_becomes_string():
    data = _schema(
        slots={"country": {"range": "country_enum", "description": "country of origin"}},
        enums={"country_enum": {"reachable_from": {"source_ontology": "obo:ncit",
                                                   "source_nodes": ["NCIT:C25464"]}}},
    )
    sch = linkml_to_schema(data)
    f = sch.fields[0]
    assert f.name == "country"
    assert f.type == "string"
    assert f.allowed_values is None


def test_dynamic_enum_multivalued_becomes_list():
    data = _schema(
        slots={"disease": {"range": "disease_enum", "multivalued": True,
                           "description": "diseases"}},
        enums={"disease_enum": {"reachable_from": {"source_nodes": ["NCIT:C7057"]}}},
    )
    f = linkml_to_schema(data).fields[0]
    assert f.type == "list"
    assert f.allowed_values is None


def test_static_permissible_values_still_enum():
    data = _schema(
        slots={"sex": {"range": "sex_enum", "description": "biological sex"}},
        enums={"sex_enum": {"permissible_values": {"Female": {"meaning": "NCIT:C16576"},
                                                   "Male": {"meaning": "NCIT:C20197"}}}},
    )
    f = linkml_to_schema(data).fields[0]
    assert f.type == "enum"
    assert set(f.allowed_values) == {"Female", "Male"}


def test_non_string_description_does_not_crash():
    # YAML `.nan` parses to float('nan'); the adapter must tolerate it.
    data = _schema(slots={"molecular_subtype": {"range": "string",
                                                "description": float("nan")}})
    f = linkml_to_schema(data).fields[0]
    assert f.name == "molecular_subtype"
    assert f.description == "molecular_subtype"  # falls back to the slot name
    assert f.type == "string"
