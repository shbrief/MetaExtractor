"""Tests for metaextractor.supplementary — table parsing helpers."""
import csv
import io
import pytest
from metaextractor import supplementary as supp
from metaextractor.supplementary import (
    Table,
    _csv_to_tables,
    _list_s3_files,
    _rows_to_table,
    fetch_supplementary,
)

_S3_NS = 'xmlns="http://s3.amazonaws.com/doc/2006-03-01/"'


def _s3_versions_xml() -> bytes:
    return (f"<ListBucketResult {_S3_NS}>"
            "<CommonPrefixes><Prefix>PMC123.1/</Prefix></CommonPrefixes>"
            "</ListBucketResult>").encode()


def _s3_keys_xml() -> bytes:
    # A data table plus the main article PDF/XML that must be filtered out.
    return (f"<ListBucketResult {_S3_NS}>"
            "<Contents><Key>PMC123.1/TableS1.csv</Key></Contents>"
            "<Contents><Key>PMC123.1/PMC123.1.pdf</Key></Contents>"
            "<Contents><Key>PMC123.1/PMC123.1.nxml</Key></Contents>"
            "</ListBucketResult>").encode()


class TestS3ListingFallback:
    """When no JATS hrefs are supplied (body came from Europe PMC), supplementary
    tables are still recovered by listing the S3 version prefix directly."""

    def test_list_s3_files_filters_to_data_tables(self, monkeypatch):
        monkeypatch.setattr(supp, "_http_get", lambda url, timeout=60.0: _s3_keys_xml())
        assert _list_s3_files("PMC123.1") == ["TableS1.csv"]  # pdf/nxml filtered out

    def test_fetch_supplementary_recovers_tables_without_jats_hrefs(self, monkeypatch):
        def router(url: str, timeout: float = 60.0) -> bytes:
            if "delimiter=/" in url:               # version-prefix listing
                return _s3_versions_xml()
            if "prefix=PMC123.1/" in url:          # keys under the version prefix
                return _s3_keys_xml()
            if url.endswith("TableS1.csv"):        # the file itself
                return b"sample_id,age\nS1,30\nS2,40\n"
            if "supplementaryFiles" in url:        # Europe PMC ZIP: none
                return b"not a zip"
            raise AssertionError(f"unexpected URL: {url}")

        monkeypatch.setattr(supp, "_http_get", router)
        result = fetch_supplementary("PMC123", jats_hrefs=None)
        assert "TableS1.csv" in result.included
        assert result.tables and result.tables[0].columns[:2] == ["sample_id", "age"]


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
