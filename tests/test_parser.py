"""Tests for the EDTF parser."""


from datelib.parser import is_valid, parse
from datelib.result import Err
from datelib.types import (
    YM,
    YMD,
    DateAnnotated,
    Interval,
    L1Season,
    LongYear,
    SeasonValue,
    UnspecifiedValue,
    Y,
)

# --------------------------------------------------------------------------- #
# Level 0: Plain dates
# --------------------------------------------------------------------------- #


class TestLevel0Dates:
    def test_year_only(self):
        result = parse("1985")
        assert result.is_ok()
        value = result.unwrap()
        assert isinstance(value, DateAnnotated)
        assert isinstance(value.value, Y)
        assert value.value.year == 1985
        assert not value.uncertain
        assert not value.approximate

    def test_year_month(self):
        result = parse("1985-04")
        assert result.is_ok()
        value = result.unwrap()
        assert isinstance(value.value, YM)
        assert value.value.year == 1985
        assert value.value.month == 4

    def test_year_month_day(self):
        result = parse("1985-04-12")
        assert result.is_ok()
        value = result.unwrap()
        assert isinstance(value.value, YMD)
        assert value.value.year == 1985
        assert value.value.month == 4
        assert value.value.day == 12

    def test_negative_year(self):
        result = parse("-1985")
        assert result.is_ok()
        assert isinstance(result.value.value, Y)
        assert result.value.value.year == -1985

    def test_negative_year_month(self):
        result = parse("-1985-04")
        assert result.is_ok()
        assert isinstance(result.value.value, YM)
        assert result.value.value.year == -1985

    def test_year_leading_zeros(self):
        result = parse("0001")
        assert result.is_ok()
        assert result.value.value.year == 1

    def test_invalid_negative_year_zero(self):
        result = parse("-0000")
        assert isinstance(result, Err)
        # Should be a parse error, we're okay with it being an Err

    def test_invalid_year_month_format(self):
        result = parse("1985-4")  # Month must be 2 digits
        assert isinstance(result, Err)

    def test_invalid_year_day_format(self):
        result = parse("1985-04-1")  # Day must be 2 digits
        assert isinstance(result, Err)


# --------------------------------------------------------------------------- #
# Level 1: Seasons
# --------------------------------------------------------------------------- #


class TestLevel1Seasons:
    def test_spring(self):
        result = parse("2001-21")
        assert result.is_ok()
        value = result.unwrap()
        assert isinstance(value.value, SeasonValue)
        assert value.value.year == 2001
        assert value.value.season == L1Season.Spring

    def test_summer(self):
        result = parse("2001-22")
        assert result.is_ok()
        assert result.value.value.season == L1Season.Summer

    def test_autumn(self):
        result = parse("2001-23")
        assert result.is_ok()
        assert result.value.value.season == L1Season.Autumn

    def test_winter(self):
        result = parse("2001-24")
        assert result.is_ok()
        assert result.value.value.season == L1Season.Winter

    def test_invalid_season_code(self):
        result = parse("2001-20")
        assert isinstance(result, Err)

    def test_invalid_season_code_high(self):
        result = parse("2001-25")
        assert isinstance(result, Err)


# --------------------------------------------------------------------------- #
# Level 1: Long Year
# --------------------------------------------------------------------------- #


class TestLevel1LongYear:
    def test_long_year_positive(self):
        result = parse("Y170000002")
        assert result.is_ok()
        value = result.unwrap()
        assert isinstance(value.value, LongYear)
        assert value.value.year == 170000002

    def test_long_year_negative(self):
        result = parse("Y-170000002")
        assert result.is_ok()
        assert result.value.value.year == -170000002

    def test_long_year_too_short(self):
        result = parse("Y1984")  # Only 4 digits — not valid as long year
        assert isinstance(result, Err)

    def test_long_year_exactly_five(self):
        result = parse("Y12345")
        assert result.is_ok()
        assert result.value.value.year == 12345


# --------------------------------------------------------------------------- #
# Level 1: Uncertainty and Approximation
# --------------------------------------------------------------------------- #


class TestLevel1Uncertainty:
    def test_uncertain_year(self):
        result = parse("1984?")
        assert result.is_ok()
        value = result.unwrap()
        assert value.uncertain
        assert not value.approximate

    def test_approximate_year_month(self):
        result = parse("2004-06~")
        assert result.is_ok()
        value = result.unwrap()
        assert not value.uncertain
        assert value.approximate

    def test_uncertain_and_approximate(self):
        result = parse("2004-06-11%")
        assert result.is_ok()
        value = result.unwrap()
        assert value.uncertain
        assert value.approximate

    def test_qualifier_on_season(self):
        result = parse("2001-21~")
        assert result.is_ok()
        value = result.unwrap()
        assert isinstance(value.value, SeasonValue)
        assert value.approximate

    def test_both_flags_individual(self):
        result = parse("1984?~")
        assert result.is_ok()
        value = result.unwrap()
        assert value.uncertain
        assert value.approximate

    def test_multiple_approximate(self):
        result = parse("1984~~")
        assert result.is_ok()
        assert result.value.approximate


# --------------------------------------------------------------------------- #
# Level 1: Unspecified Digits
# --------------------------------------------------------------------------- #


class TestLevel1Unspecified:
    def test_unspecified_decade(self):
        result = parse("201X")
        assert result.is_ok()
        value = result.unwrap()
        assert isinstance(value.value, UnspecifiedValue)
        assert value.value.year == "201X"

    def test_unspecified_century(self):
        result = parse("20XX")
        assert result.is_ok()
        assert result.value.value.year == "20XX"

    def test_unspecified_month(self):
        result = parse("2004-XX")
        assert result.is_ok()
        value = result.unwrap()
        assert value.value.year == "2004"
        assert value.value.month == "XX"

    def test_unspecified_day(self):
        result = parse("1985-04-XX")
        assert result.is_ok()
        value = result.unwrap()
        assert value.value.year == "1985"
        assert value.value.month == "04"
        assert value.value.day == "XX"

    def test_unspecified_month_and_day(self):
        result = parse("1985-XX-XX")
        assert result.is_ok()

    def test_unspecified_year_with_month(self):
        result = parse("188X-07")
        assert result.is_ok()
        value = result.unwrap()
        assert isinstance(value.value, UnspecifiedValue)
        assert value.value.year == "188X"
        assert value.value.month == "07"

    def test_unspecified_year_with_month_and_day(self):
        result = parse("188X-07-02")
        assert result.is_ok()
        value = result.unwrap()
        assert isinstance(value.value, UnspecifiedValue)
        assert value.value.year == "188X"
        assert value.value.month == "07"
        assert value.value.day == "02"

    def test_unspecified_with_qualifier(self):
        result = parse("201X~")
        assert result.is_ok()
        value = result.unwrap()
        assert value.value.year == "201X"
        assert value.approximate

    def test_invalid_unspecified_three_x(self):
        result = parse("2XXX")
        # 3 trailing Xs — not valid per L1 (only 1 or 2)
        assert isinstance(result, Err)

    def test_invalid_unspecified_four_x(self):
        result = parse("XXXX")
        assert isinstance(result, Err)

    def test_unspecified_year_with_trailing_chars(self):
        result = parse("201X-04")
        assert result.is_ok()
        value = result.unwrap()
        assert isinstance(value.value, UnspecifiedValue)
        assert value.value.year == "201X"
        assert value.value.month == "04"


# --------------------------------------------------------------------------- #
# Level 1: Intervals
# --------------------------------------------------------------------------- #


class TestLevel1Intervals:
    def test_basic_interval(self):
        result = parse("1964/2008")
        assert result.is_ok()
        value = result.unwrap()
        assert isinstance(value, Interval)
        assert isinstance(value.lower, DateAnnotated)
        assert isinstance(value.upper, DateAnnotated)
        assert value.lower.value.year == 1964
        assert value.upper.value.year == 2008

    def test_interval_with_month_precision(self):
        result = parse("2004-06/2006-08")
        assert result.is_ok()
        value = result.unwrap()
        assert value.lower.value.month == 6
        assert value.upper.value.month == 8

    def test_interval_with_day_precision(self):
        result = parse("2004-02-01/2005-02-08")
        assert result.is_ok()
        value = result.unwrap()
        assert isinstance(value.lower.value, YMD)
        assert isinstance(value.upper.value, YMD)

    def test_open_end_interval(self):
        result = parse("1985/..")
        assert result.is_ok()
        value = result.unwrap()
        assert value.lower.value.year == 1985
        assert value.upper == "open"

    def test_open_start_interval(self):
        result = parse("../1985")
        assert result.is_ok()
        value = result.unwrap()
        assert value.lower == "open"
        assert value.upper.value.year == 1985

    def test_unknown_end(self):
        result = parse("1985/")
        assert result.is_ok()
        value = result.unwrap()
        assert value.lower.value.year == 1985
        assert value.upper == "unknown"

    def test_unknown_start(self):
        result = parse("/1985")
        assert result.is_ok()
        value = result.unwrap()
        assert value.lower == "unknown"
        assert value.upper.value.year == 1985

    def test_interval_with_qualifiers(self):
        result = parse("1984?/2004~")
        assert result.is_ok()
        value = result.unwrap()
        assert value.lower.uncertain
        assert value.upper.approximate

    def test_interval_unknown_both(self):
        result = parse("/")
        assert result.is_ok()
        value = result.unwrap()
        assert value.lower == "unknown"
        assert value.upper == "unknown"

    def test_interval_mixed_precision(self):
        result = parse("2004-02-01/2005-02")
        assert result.is_ok()

    def test_interval_start_year_end_month(self):
        result = parse("2005/2006-02")
        assert result.is_ok()


# --------------------------------------------------------------------------- #
# Invalid inputs
# --------------------------------------------------------------------------- #


class TestInvalidInputs:
    def test_empty_string(self):
        result = parse("")
        assert isinstance(result, Err)

    def test_whitespace_only(self):
        result = parse("   ")
        assert isinstance(result, Err)

    def test_gibberish(self):
        result = parse("not a date")
        assert isinstance(result, Err)

    def test_invalid_month(self):
        result = parse("1985-13")
        assert isinstance(result, Err)

    def test_invalid_day(self):
        result = parse("1985-04-32")
        assert isinstance(result, Err)

    def test_trailing_characters(self):
        result = parse("1985 extra")
        assert isinstance(result, Err)

    def test_is_valid_true(self):
        assert is_valid("1985-04-12")

    def test_is_valid_false(self):
        assert not is_valid("not a date")


# --------------------------------------------------------------------------- #
# Round-trip sanity checks
# --------------------------------------------------------------------------- #


class TestRoundTripSanity:
    """Parse inputs that should cleanly produce the expected AST types."""

    def test_leading_whitespace_stripped(self):
        result = parse("  1985")
        assert result.is_ok()
        assert result.value.value.year == 1985

    def test_trailing_whitespace_stripped(self):
        result = parse("1985  ")
        assert result.is_ok()
        assert result.value.value.year == 1985
