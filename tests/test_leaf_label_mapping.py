"""Stacked headers: a column keeps its full header path as its name, and lexical mapping
falls back to its bottom header label when that label is unique in the table.

Regression for the LiJ_2017 smoke run: Table S2's identifier column, read with a two-row
header, was named "Data production | Sample ID" and was not recognised as sample_id.
"""
import dataclasses
import json

from metaextractor.column_mapper import map_columns_with_leaf_labels
from metaextractor.fetcher import FetchedPaper, save_fetched
from metaextractor.supplementary import Table
from metaextractor.table_plan import Melt, MeltGroup, TablePlan, execute_plan

FIELDS = ["sample_id", "age", "sex", "body_site"]


def _raw_table(raw):
    header = raw[0]
    return Table(name="S2", source="test", columns=list(header),
                 rows=[dict(zip(header, r)) for r in raw[1:]], raw_rows=raw)


def test_execute_plan_records_bottom_labels_of_stacked_headers():
    raw = [["Stage", "Data production", ""],
           ["", "Sample ID", "Insert size (bp)"],
           ["Control", "nHF511704", "300"]]
    out = execute_plan(_raw_table(raw), TablePlan(header_rows=[0, 1], data_starts_at=2))
    assert out.columns == ["Stage", "Data production | Sample ID", "Data production | Insert size (bp)"]
    assert out.leaf_labels == {"Data production | Sample ID": "Sample ID",
                               "Data production | Insert size (bp)": "Insert size (bp)"}


def test_single_row_header_has_no_leaf_labels():
    out = execute_plan(_raw_table([["Sample ID", "Age"], ["s1", "30"]]),
                       TablePlan(header_rows=[0], data_starts_at=1))
    assert out.leaf_labels == {}


def test_unique_bottom_label_maps_when_full_path_does_not():
    cols = ["Stage", "Data production | Sample ID", "Data production | Insert size (bp)"]
    m = map_columns_with_leaf_labels(cols, {cols[1]: "Sample ID", cols[2]: "Insert size (bp)"}, FIELDS)
    assert m.mapped == {"Data production | Sample ID": "sample_id"}
    assert m.tier_used["Data production | Sample ID"] == "leaf:normalized"
    assert "Data production | Sample ID" not in m.unmapped


def test_repeated_bottom_labels_are_not_collapsed():
    cols = ["Pair", "Mother | Age", "Infant | Age"]
    m = map_columns_with_leaf_labels(cols, {cols[1]: "Age", cols[2]: "Age"}, FIELDS)
    assert m.mapped == {}


def test_bottom_label_never_takes_a_field_a_full_header_mapped():
    cols = ["Sample ID", "Sequencing | Sample ID"]
    m = map_columns_with_leaf_labels(cols, {cols[1]: "Sample ID"}, FIELDS)
    # "Sample ID" label occurs twice (full header and leaf): no fallback at all
    assert m.mapped == {"Sample ID": "sample_id"}
    cols = ["sample_id", "Donor | Sample"]
    m = map_columns_with_leaf_labels(cols, {cols[1]: "Sample"}, FIELDS)
    assert m.mapped == {"sample_id": "sample_id"}   # "Sample" alias -> sample_id already taken


def test_melt_output_through_mapping():
    raw = [["pair_id", "body_site_Mother", "body_site_Infant"], ["p1", "stool", "feces"]]
    out = execute_plan(_raw_table(raw), TablePlan(
        header_rows=[0], data_starts_at=1,
        melt=Melt(category_label="sample type",
                  groups=[MeltGroup(value_label="body site", sources={"Mother": 1, "Infant": 2})])))
    m = map_columns_with_leaf_labels(out.columns, out.leaf_labels, FIELDS)
    assert m.mapped == {"body site": "body_site"}


def test_frozen_tables_format_unchanged_without_leaf_labels(tmp_path):
    t = _raw_table([["Sample ID", "Age"], ["s1", "30"]])
    paper = FetchedPaper(pmid="1", pmcid=None, doi=None, text="body", source="test", has_body=True,
                         supplementary_tables=[t])
    save_fetched(paper, tmp_path)
    saved = json.loads((tmp_path / "tables.json").read_text())
    assert set(saved[0]) == {f.name for f in dataclasses.fields(Table)} - {"leaf_labels"}
