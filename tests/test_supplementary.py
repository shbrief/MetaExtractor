"""Tests for metaextractor.supplementary — table parsing helpers."""
import csv
import io
import pytest
from metaextractor.supplementary import (
    Table,
    _csv_to_tables,
    _rows_to_table,
)


# ---------------------------------------------------------------------------
# _rows_to_table
# ---------------------------------------------------------------------------

class TestRowsToTable:
    def test_basic_grid(self):
        raw = [
            ["sample_id", "age", "sex"],
            ["s1", "30", "male"],
            ["s2", "25", "female"],
        ]
        t = _rows_to_table("test.csv", "local", raw)
        assert t is not None
        assert t.columns == ["sample_id", "age", "sex"]
        assert len(t.rows) == 2
        assert t.rows[0]["sample_id"] == "s1"
        assert t.rows[1]["sex"] == "female"

    def test_degenerate_all_empty_header_returns_none(self):
        raw = [["", "", ""], ["1", "2", "3"]]
        assert _rows_to_table("t", "local", raw) is None

    def test_too_few_rows_returns_none(self):
        # Only a header row, no data
        assert _rows_to_table("t", "local", [["col_a", "col_b"]]) is None

    def test_empty_grid_returns_none(self):
        assert _rows_to_table("t", "local", []) is None

    def test_fully_empty_rows_skipped(self):
        raw = [
            ["sample_id", "age"],
            ["", ""],          # fully empty — should be skipped
            ["s1", "30"],
        ]
        t = _rows_to_table("t", "local", raw)
        assert t is not None
        assert len(t.rows) == 1
        assert t.rows[0]["sample_id"] == "s1"

    def test_duplicate_headers_deduplicated(self):
        raw = [
            ["col", "col", "col"],
            ["a", "b", "c"],
        ]
        t = _rows_to_table("t", "local", raw)
        assert t is not None
        assert len(t.columns) == 3
        # All three column names should be unique
        assert len(set(t.columns)) == 3

    def test_none_cells_coerced_to_string(self):
        raw = [
            ["sample_id", "age"],
            [None, None],
            ["s1", "30"],
        ]
        t = _rows_to_table("t", "local", raw)
        assert t is not None
        # The all-None row is still all-empty strings → cleaned out
        # Only s1 row should remain
        non_empty = [r for r in t.rows if any(v for v in r.values())]
        assert len(non_empty) == 1

    def test_short_rows_padded(self):
        raw = [
            ["a", "b", "c"],
            ["1"],            # short row
        ]
        t = _rows_to_table("t", "local", raw)
        assert t is not None
        assert t.rows[0]["b"] == ""
        assert t.rows[0]["c"] == ""

    def test_raw_rows_preserved(self):
        raw = [
            ["sample_id", "age"],
            ["s1", "30"],
        ]
        t = _rows_to_table("t", "local", raw)
        assert t is not None
        assert len(t.raw_rows) == 2
        assert t.raw_rows[0] == ["sample_id", "age"]


# ---------------------------------------------------------------------------
# _csv_to_tables
# ---------------------------------------------------------------------------

class TestCsvToTables:
    def _make_blob(self, rows: list[list[str]], delimiter: str = ",") -> bytes:
        buf = io.StringIO()
        writer = csv.writer(buf, delimiter=delimiter)
        for row in rows:
            writer.writerow(row)
        return buf.getvalue().encode("utf-8")

    def test_simple_csv(self):
        blob = self._make_blob([
            ["sample_id", "body_site"],
            ["s1", "stool"],
            ["s2", "oral"],
        ])
        tables = _csv_to_tables("test.csv", "local", blob, ",")
        assert len(tables) == 1
        t = tables[0]
        assert t.columns == ["sample_id", "body_site"]
        assert len(t.rows) == 2

    def test_tsv(self):
        blob = self._make_blob(
            [["sample_id", "age"], ["s1", "30"]], delimiter="\t"
        )
        tables = _csv_to_tables("test.tsv", "local", blob, "\t")
        assert len(tables) == 1
        assert tables[0].rows[0]["age"] == "30"

    def test_empty_csv_returns_empty_list(self):
        tables = _csv_to_tables("empty.csv", "local", b"", ",")
        assert tables == []

    def test_header_only_csv_returns_empty_list(self):
        blob = self._make_blob([["col_a", "col_b"]])
        tables = _csv_to_tables("honly.csv", "local", blob, ",")
        assert tables == []

    def test_source_set_correctly(self):
        blob = self._make_blob([["sample_id"], ["s1"]])
        tables = _csv_to_tables("t.csv", "s3", blob, ",")
        assert tables[0].source == "s3"
