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


def test_scope_annotation_is_read_but_not_sent_to_model():
    from metaextractor.adapters.linkml import linkml_to_schema
    data = {
        "classes": {"S": {"slots": ["a", "b", "c"]}},
        "slots": {"a": {"annotations": {"scope": "study"}},
                  "b": {"annotations": {"scope": {"tag": "scope", "value": "sample"}}},
                  "c": {"annotations": {"scope": "other"}}},
    }
    s = linkml_to_schema(data)
    assert [f.scope for f in s.fields] == ["study", "sample", None]
    assert all("scope" not in f for f in s.to_prompt_json()["fields"])


def test_propagate_study_value_annotation_is_read_but_not_sent_to_model():
    data = {
        "classes": {"R": {"slots": ["a", "b", "c"]}},
        "slots": {"a": {"annotations": {"scope": "sample", "propagate_study_value": True}},
                  "b": {"annotations": {"scope": "sample",
                                        "propagate_study_value": {"tag": "propagate_study_value",
                                                                  "value": "true"}}},
                  "c": {"annotations": {"scope": "sample"}}},
    }
    s = linkml_to_schema(data)
    assert [f.propagate_study_value for f in s.fields] == [True, True, False]
    assert all("propagate_study_value" not in f for f in s.to_prompt_json()["fields"])


def test_unit_of_annotation_is_read_but_not_sent_to_model():
    data = {"classes": {"R": {"slots": ["age", "age_unit"]}},
            "slots": {"age": {"range": "float"},
                      "age_unit": {"annotations": {"unit_of": "age"}}}}
    s = linkml_to_schema(data)
    assert [f.unit_of for f in s.fields] == [None, "age"]
    assert all("unit_of" not in f for f in s.to_prompt_json()["fields"])
