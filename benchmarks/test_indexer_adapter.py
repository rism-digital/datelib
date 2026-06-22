"""Smoke tests for the indexer adapter (antequem migration)."""

import sys

sys.path.insert(0, "/Users/ahankins/Documents/code/rism/MuscatPlus/antequem/benchmarks")

from indexer_adapter import (
    _extract_range,
    convert_to_edtf,
    parse_date_statement,
    process_date_statements,
    process_edtf_date,
    simplify_date_statement,
)


class TestAdapterAPI:
    """Verify the adapter functions return the old API shapes."""

    def test_simplify_date_statement(self):
        assert simplify_date_statement("s.a.") == "s.a."  # no-date marker
        assert simplify_date_statement("18th century") == "1701/1800"
        assert simplify_date_statement("circa 1850") == "1850~"

    def test_process_edtf_date_simple(self):
        assert process_edtf_date("1985", "1985") == (1985, 1985)

    def test_process_edtf_date_interval(self):
        assert process_edtf_date("1850/1900", "1850/1900") == (1850, 1900)

    def test_process_edtf_date_open_end(self):
        result = process_edtf_date("1850/..", "1850/..")
        assert result[0] == 1850
        assert result[1] is not None

    def test_parse_date_statement(self):
        assert parse_date_statement("1985") == (1985, 1985)
        assert parse_date_statement("1850-1900") == (1850, 1900)
        assert parse_date_statement("s.a.") == (None, None)

    def test_process_date_statements(self):
        result = process_date_statements(["1850", "1900"], "test-001")
        assert result == [1850, 1900]

    def test_convert_to_edtf(self):
        assert convert_to_edtf("1850c") == "1850~"
        assert convert_to_edtf("1850p") == "1850/.."
        assert convert_to_edtf("1850a") == "../1850"

    def test_extract_range_date(self):
        import antequem
        result = antequem.parse("1985")
        assert result.is_ok
        assert _extract_range(result.unwrap()) == (1985, 1985)

    def test_extract_range_interval(self):
        import antequem
        result = antequem.parse("1850/1900")
        assert result.is_ok
        assert _extract_range(result.unwrap()) == (1850, 1900)
