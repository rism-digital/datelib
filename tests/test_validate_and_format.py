"""Tests for EDTF validation and formatting."""

import pytest

from datelib.formatter import format as fmt
from datelib.parser import parse
from datelib.result import Err
from datelib.validate import _days_in_month, _is_leap, validate


class TestLeapYear:
    def test_leap_2020(self):
        assert _is_leap(2020) is True

    def test_not_leap_2019(self):
        assert _is_leap(2019) is False

    def test_century_not_leap_1900(self):
        assert _is_leap(1900) is False

    def test_400_leap_2000(self):
        assert _is_leap(2000) is True


class TestDaysInMonth:
    def test_january(self):
        assert _days_in_month(2020, 1) == 31

    def test_february_leap(self):
        assert _days_in_month(2020, 2) == 29

    def test_february_not_leap(self):
        assert _days_in_month(2019, 2) == 28

    def test_april(self):
        assert _days_in_month(2020, 4) == 30


class TestValidate:
    def test_valid_ymd(self):
        ast = parse("1985-04-12").unwrap()
        result = validate(ast)
        assert result.is_ok

    def test_invalid_day_april(self):
        ast = parse("1985-04-31").unwrap()
        result = validate(ast)
        assert isinstance(result, Err)

    def test_invalid_feb_29_non_leap(self):
        ast = parse("2019-02-29").unwrap()
        result = validate(ast)
        assert isinstance(result, Err)

    def test_valid_feb_29_leap(self):
        ast = parse("2020-02-29").unwrap()
        result = validate(ast)
        assert result.is_ok

    def test_interval_with_valid_dates(self):
        ast = parse("1985/2005").unwrap()
        result = validate(ast)
        assert result.is_ok

    def test_interval_with_invalid_day(self):
        ast = parse("1985-02-30/2005").unwrap()
        result = validate(ast)
        assert isinstance(result, Err)

    def test_valid_season(self):
        ast = parse("2001-21").unwrap()
        result = validate(ast)
        assert result.is_ok


class TestFormatRoundTrip:
    """Verify that format(parse(s)) == s for valid inputs."""

    @pytest.mark.parametrize(
        "input_string",
        [
            # Level 0
            "1985",
            "1985-04",
            "1985-04-12",
            # Level 1
            "Y170000002",
            "Y-170000002",
            "-1985",
            "2001-21",
            "2001-22",
            "2001-23",
            "2001-24",
            "1984?",
            "2004-06~",
            "2004-06-11%",
            "201X",
            "20XX",
            "2004-XX",
            "1985-04-XX",
            "1985-XX-XX",
            "201X~",
            "1964/2008",
            "2004-06/2006-08",
            "2004-02-01/2005-02-08",
            "1985/..",
            "../1985",
            "1985/",
            "/1985",
            "1984?/2004~",
        ],
    )
    def test_round_trip(self, input_string: str):
        result = parse(input_string)
        assert result.is_ok, f"Failed to parse {input_string!r}"
        formatted = fmt(result.unwrap())
        assert formatted == input_string, (
            f"Round-trip failed: {input_string!r} -> {formatted!r}"
        )

    def test_canonical_combined_qualifier(self):
        """?~ is canonicalized to % on formatting."""
        ast = parse("1984?~").unwrap()
        assert fmt(ast) == "1984%"

    def test_format_year(self):
        ast = parse("1985").unwrap()
        assert fmt(ast) == "1985"

    def test_format_year_month(self):
        ast = parse("1985-04").unwrap()
        assert fmt(ast) == "1985-04"

    def test_format_ymd(self):
        ast = parse("1985-04-12").unwrap()
        assert fmt(ast) == "1985-04-12"

    def test_format_uncertain(self):
        ast = parse("1984?").unwrap()
        assert fmt(ast) == "1984?"

    def test_format_approximate(self):
        ast = parse("2004-06~").unwrap()
        assert fmt(ast) == "2004-06~"

    def test_format_both_qualifiers(self):
        ast = parse("2004-06-11%").unwrap()
        assert fmt(ast) == "2004-06-11%"

    def test_format_interval(self):
        ast = parse("1964/2008").unwrap()
        assert fmt(ast) == "1964/2008"

    def test_format_open_end(self):
        ast = parse("1985/..").unwrap()
        assert fmt(ast) == "1985/.."

    def test_format_open_start(self):
        ast = parse("../1985").unwrap()
        assert fmt(ast) == "../1985"

    def test_format_unknown_end(self):
        ast = parse("1985/").unwrap()
        assert fmt(ast) == "1985/"

    def test_format_unknown_start(self):
        ast = parse("/1985").unwrap()
        assert fmt(ast) == "/1985"

    def test_format_long_year(self):
        ast = parse("Y170000002").unwrap()
        assert fmt(ast) == "Y170000002"

    def test_format_negative_long_year(self):
        ast = parse("Y-170000002").unwrap()
        assert fmt(ast) == "Y-170000002"

    def test_format_season(self):
        ast = parse("2001-21").unwrap()
        assert fmt(ast) == "2001-21"

    def test_format_unspecified_day(self):
        ast = parse("1985-04-XX").unwrap()
        assert fmt(ast) == "1985-04-XX"

    def test_format_unspecified_month(self):
        ast = parse("2004-XX").unwrap()
        assert fmt(ast) == "2004-XX"

    def test_format_unspecified_both(self):
        ast = parse("1985-XX-XX").unwrap()
        assert fmt(ast) == "1985-XX-XX"

    def test_format_unspecified_decade(self):
        ast = parse("201X").unwrap()
        assert fmt(ast) == "201X"

    def test_format_unspecified_century(self):
        ast = parse("20XX").unwrap()
        assert fmt(ast) == "20XX"
