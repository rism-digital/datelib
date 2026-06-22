"""Tests for antequem.natlang.coerce"""

import pytest

from antequem.natlang.coerce import coerce, is_no_date


class TestNoDateValues:
    @pytest.mark.parametrize(
        "value",
        [
            "",
            None,
            "s.a.",
            "[s.d.]",
            "s.d.",
            "n.d.",
            "unknown",
            "unk",
            "(n.d.)",
            "[n. d.]",
            "XVI-XVIII",
            "Año X",
        ],
    )
    def test_known_no_dates(self, value):
        assert is_no_date(value) is True
        assert coerce(value) is None

    def test_regular_date_is_not_no_date(self):
        assert is_no_date("1850") is False


class TestSimpleYear:
    def test_single_year(self):
        assert coerce("1850") == "1850"

    def test_year_range(self):
        assert coerce("1850-1900") == "1850/1900"

    def test_masked_year_with_month_day(self):
        assert coerce("188?-07-02") == "188X-07-02"

    def test_masked_year_with_month(self):
        assert coerce("188?-07") == "188X-07"

    def test_leading_hyphen_is_before_year(self):
        assert coerce("-1910") == "/1910"

    def test_bce_year(self):
        assert coerce("70 BCE") == "-0069"

    def test_padded_bce_year(self):
        assert coerce("0070 BCE") == "-0069"

    def test_one_bce(self):
        assert coerce("1 BCE") == "0000"

    def test_ce_year(self):
        assert coerce("19 CE") == "0019"

    def test_bce_ce_range(self):
        assert coerce("0070 BCE-0019") == "-0069/0019"

    def test_bc_ad_range(self):
        assert coerce("70 BC-19 AD") == "-0069/0019"

    def test_bce_approximate_range_with_trailing_era(self):
        assert coerce("0450c-0385c BCE") == "-0449~/-0384~"


class TestSlashDate:
    def test_dd_mm_yyyy(self):
        assert coerce("12/04/1850") == "1850-04-12"

    def test_slash_divided_alt(self):
        assert coerce("185004/12") == "1850-04"

    def test_alt_dashed(self):
        assert coerce("1850----") == "1850"


class TestDotSeparated:
    def test_dd_mm_yyyy_dots(self):
        assert coerce("12.04.1850") == "1850-04-12"

    def test_single_digit_day_month(self):
        assert coerce("1.1.1850") == "1850-01-01"

    def test_dot_separated_with_approximate_a_suffix(self):
        assert coerce("19.4.1877a") == "/1877-04-19"

    def test_dot_separated_with_approximate_c_suffix(self):
        assert coerce("12.11.1898c") == "1898-11-12~"

    def test_dot_separated_with_single_digit_and_c_suffix(self):
        assert coerce("4.1.1922c") == "1922-01-04~"

    def test_dot_separated_with_p_suffix(self):
        assert coerce("15.8.1914p") == "1914-08-15/"


class TestBracketStripping:
    """Regression tests for bracket-wrapped inputs."""

    def test_brackets_strip_before_century_dashes(self):
        assert coerce("[17??]") == "1601/1700"

    def test_brackets_strip_before_circa(self):
        assert coerce("[circa 1850]") == "1850~"

    def test_brackets_strip_before_approximate(self):
        assert coerce("[approximately 1781]") == "1781~"

    def test_brackets_strip_simple_year(self):
        assert coerce("[1781]") == "1781"

    def test_brackets_strip_embedded_year_prefix(self):
        assert coerce("[15]58") == "1558"

    def test_brackets_strip_embedded_year_suffix(self):
        assert coerce("1[773]") == "1773"

    def test_brackets_strip_approx(self):
        assert coerce("[approx 1800]") == "1800~"

    def test_brackets_strip_around(self):
        assert coerce("[around 1800]") == "1800~"

    def test_brackets_strip_about(self):
        assert coerce("[about 1800]") == "1800~"

    def test_brackets_strip_unspecified_decade_shorthand(self):
        assert coerce("[194-]") == "194X"


class TestMonthNameDates:
    """Dates with spelled-out month names."""

    def test_month_day_comma_year(self):
        assert coerce("August 22, 1785") == "1785-08-22"

    def test_month_day_year(self):
        assert coerce("August 22 1785") == "1785-08-22"

    def test_day_month_year(self):
        assert coerce("22 August 1785") == "1785-08-22"

    def test_uppercase(self):
        assert coerce("AUGUST 22, 1785") == "1785-08-22"

    def test_month_year_only(self):
        assert coerce("August 1785") == "1785-08"

    def test_various_months(self):
        assert coerce("January 1, 2000") == "2000-01-01"
        assert coerce("December 31, 1999") == "1999-12-31"
        assert coerce("February 29, 2020") == "2020-02-29"

    def test_comma_after_month_with_brackets(self):
        assert coerce("[April, 30 1814]") == "1814-04-30"

    def test_comma_after_month(self):
        assert coerce("April, 30 1814") == "1814-04-30"

    def test_embedded_month_name_date(self):
        assert coerce("copy of letter, March 14th 1863") == "1863-03-14"

    def test_dated_month_name_date(self):
        assert coerce("dated August 22, 1785") == "1785-08-22"

    def test_embedded_month_year(self):
        assert coerce("written around August 1785 in Paris") == "1785-08"


class TestCenturyExpressions:
    def test_th_century(self):
        assert coerce("18th century") == "1701/1800"

    def test_st_century(self):
        assert coerce("1st century") == "0001/0100"

    def test_rd_century(self):
        assert coerce("23rd century") == "2201/2300"

    def test_century_c_dot(self):
        assert coerce("18th c.") == "1701/1800"

    def test_century_fraction_second_half(self):
        result = coerce("16th century, second half")
        assert result == "1550/1600"

    def test_century_fraction_third(self):
        result = coerce("15th century, first third")
        assert result == "1400/1433"

    def test_century_fraction_quarter(self):
        result = coerce("18th century, 2nd quarter")
        assert result == "1725/1750"

    def test_century_adjective_early(self):
        result = coerce("16th century, early")
        assert result == "1500/1510"

    def test_century_adjective_late(self):
        result = coerce("16th century, late")
        assert result == "1590/1600"

    def test_century_adjective_middle(self):
        result = coerce("16th century, middle")
        assert result == "1525/1575"

    def test_code_notation_decade(self):
        result = coerce("18.2d")
        assert result == "1711/1720"

    def test_code_notation_beginning(self):
        result = coerce("19.in")
        assert result == "1801/1810"

    def test_code_notation_quarter(self):
        result = coerce("17.3q")
        assert result == "1651/1675"

    def test_century_dashes(self):
        assert coerce("17--") == "1601/1700"

    def test_century_question_marks(self):
        assert coerce("17??") == "1601/1700"

    def test_century_truncated(self):
        assert coerce("18/19") == "1701/1900"

    def test_century_turn_shorthand(self):
        assert coerce("18./19.") == "1790%/1810%"

    def test_century_turn_shorthand_previous(self):
        assert coerce("17./18.") == "1690%/1710%"

    def test_century_turn_shorthand_next(self):
        assert coerce("19./20.") == "1890%/1910%"

    def test_century_short_c(self):
        assert coerce("18C") == "1701/1800"

    def test_century_short_c_dot(self):
        assert coerce("18c.") == "1701/1800"

    def test_century_short_sc_suffix(self):
        assert coerce("18.sc") == "1701/1800"

    def test_century_truncated_sc_suffix(self):
        assert coerce("18/19.sc") == "1701/1900"


class TestApproximateBoundaries:
    def test_circa(self):
        assert coerce("circa 1850") == "1850~"

    def test_ca(self):
        assert coerce("ca. 1800") == "1800~"

    def test_ca_no_space(self):
        assert coerce("ca 1800") == "1800~"

    def test_um(self):
        assert coerce("um 1850") == "1850~"

    def test_before(self):
        assert coerce("before 1900") == "/1900"

    def test_before_leading_mushed_date(self):
        assert coerce("before 18991105") == "/1899-11-05"

    def test_before_leading_mushed_month(self):
        assert coerce("before 18200300") == "/1820-03"

    def test_not_after(self):
        assert coerce("not after 1800") == "/1800"

    def test_after(self):
        assert coerce("after 1800") == "1800/"

    def test_after_leading_mushed_date(self):
        assert coerce("after 18991105") == "1899-11-05/"

    def test_not_before(self):
        assert coerce("not before 1800") == "1800/"

    def test_since(self):
        assert coerce("since 1850") == "1850/"

    def test_nach(self):
        assert coerce("nach 1850") == "1850/"

    def test_vor(self):
        assert coerce("vor 1900") == "/1900"

    def test_approximate(self):
        assert coerce("approximately 1850") == "1850~"

    def test_approx(self):
        assert coerce("approx 1850") == "1850~"

    def test_around(self):
        assert coerce("around 1850") == "1850~"

    def test_about(self):
        assert coerce("about 1850") == "1850~"

    def test_circa_range(self):
        assert coerce("ca. 1780-1790") == "1780~/1790~"

    def test_circa_range_circa(self):
        assert coerce("circa 1500-1600") == "1500~/1600~"

    def test_approx_range(self):
        assert coerce("approx. 1800-1900") == "1800~/1900~"

    def test_around_range(self):
        assert coerce("around 1800-1900") == "1800~/1900~"

    def test_endpoint_approximate_range_c(self):
        assert coerce("1873c-1875c") == "1873~/1875~"

    def test_endpoint_approximate_range_a(self):
        assert coerce("1873a-1875a") == "1873~/1875~"

    def test_mixed_endpoint_approximate_range(self):
        assert coerce("1873c-1875") == "1873~/1875"

    def test_mixed_endpoint_approximate_range_right(self):
        assert coerce("1873-1875a") == "1873/1875~"

    def test_p_annotated_endpoint_range_is_unsupported(self):
        assert coerce("1873p-1875p") is None

    def test_endpoint_approximate_slash_range(self):
        assert coerce("[1938c/1941c]") == "1938~/1941~"

    def test_no_space_after_ca_dot_single_year(self):
        assert coerce("ca.1780") == "1780~"

    def test_no_space_after_ca_dot_range(self):
        assert coerce("ca.1780-1790") == "1780~/1790~"

    def test_no_space_after_circa(self):
        assert coerce("circa1500") == "1500~"

    def test_no_space_after_ca(self):
        assert coerce("ca1500") == "1500~"

    def test_no_space_after_c(self):
        assert coerce("c1798") == "1798~"

    def test_trailing_dot_after_compact_c_suffix(self):
        assert coerce("1913c.") == "1913~"

    def test_bracketed_trailing_dot_after_compact_c_suffix(self):
        assert coerce("[1921c.]") == "1921~"

    def test_ordinal_day_1st(self):
        assert coerce("August 1st 1785") == "1785-08-01"

    def test_ordinal_day_2nd(self):
        assert coerce("August 2nd 1785") == "1785-08-02"

    def test_ordinal_day_3rd(self):
        assert coerce("August 3rd 1785") == "1785-08-03"

    def test_ordinal_day_14th(self):
        assert coerce("[March 14th 1863]") == "1863-03-14"

    def test_ordinal_day_14th_bare(self):
        assert coerce("March 14th 1863") == "1863-03-14"

    def test_brackets_stripped(self):
        # [] should be stripped, then "approximately" matched
        assert coerce("[approximately 1781]") == "1781~"
    def test_birth_marker(self):
        assert coerce("1850*") == "1850/"

    def test_death_marker(self):
        assert coerce("1850+") == "/1850"

    def test_approximate_death_marker(self):
        assert coerce("1657c+") == "/1657~"

    def test_approximate_birth_marker(self):
        assert coerce("1657c*") == "1657~/"

    def test_legacy_approximate_death_marker(self):
        assert coerce("1601a+") == "/1601~"

    def test_legacy_approximate_birth_marker(self):
        assert coerce("1601a*") == "1601~/"

    def test_birth_marker_ends_with_star(self):
        assert coerce("1900*") == "1900/"


class TestSimplificationRules:
    def test_strip_letters(self):
        assert coerce("1850p") == "1850/"

    def test_strip_letters_c(self):
        assert coerce("1850c") == "1850~"

    def test_strip_letters_a(self):
        assert coerce("1850a") == "/1850"

    def test_before_suffix_single_year(self):
        assert coerce("1811a") == "/1811"

    def test_after_suffix_single_year(self):
        assert coerce("1811p") == "1811/"

    def test_compact_before_suffix_full_date(self):
        assert coerce("18991105a") == "/1899-11-05"

    def test_compact_after_suffix_full_date(self):
        assert coerce("18991105p") == "1899-11-05/"

    def test_zero_day(self):
        assert coerce("1850-04-00") == "1850"

    def test_zero_day_xx(self):
        assert coerce("1850-04-XX") == "1850"

    def test_multi_year(self):
        assert coerce("1850-01-01-1900-12-31") == "1850/1900"

    def test_mushed_together(self):
        assert coerce("18500412") == "1850"

    def test_leading_mushed_date_with_trailing_context(self):
        assert coerce("18400213 (13.2.1840c)") == "1840-02-13"

    def test_leading_mushed_month_with_trailing_context(self):
        assert coerce("18200300 (1820c)") == "1820-03"

    def test_leading_mushed_date_range_with_trailing_context(self):
        assert (
            coerce("18510503-18511103 (Anfangs- und Schlussdatierung)")
            == "1851-05-03/1851-11-03"
        )

    def test_leading_mushed_month_range_with_trailing_context(self):
        assert coerce("17990900-17991200 (ca.)") == "1799-09/1799-12"

    def test_mushed_month_range(self):
        assert coerce("17990900-17991200") == "1799-09/1799-12"

    def test_mushed_together_range(self):
        assert coerce("18500412-19001231") == "1850/1900"

    def test_between(self):
        assert coerce("between 1790 and 1800") == "1790/1800"

    def test_between_french(self):
        assert coerce("entre 1790 et 1800") == "1790/1800"

    def test_parenthetical_single(self):
        s = "1850 (single date)"
        assert coerce(s) == "1850"

    def test_parenthetical_range(self):
        s = "1850-1900 (18th century)"
        assert coerce(s) == "1850/1900"

    def test_explicit_between_french(self):
        assert coerce("entre 1800 et 1900") == "1800/1900"

    def test_explicit_between_german(self):
        assert coerce("um 1800 bis um 1900") == "1800/1900"

    def test_embedded_between_range(self):
        assert coerce("document compiled between 1790 and 1800, revised later") == "1790/1800"

    def test_copied_between_range(self):
        assert coerce("[copied between 1790 and 1810]") == "1790/1810"

    def test_parenthetical_century_appendage_on_range(self):
        assert coerce("1750-1799 (18.2d)") == "1750/1799"

    def test_embedded_single_year_fallback(self):
        assert coerce("document compiled in 1790, revised later") == "1790"

    def test_embedded_decade_text_fallback(self):
        assert coerce("[copied during the 1780s]") == "1780"

    def test_embedded_two_year_fallback(self):
        assert coerce("document mentions 1790 and 1800 in passing") == "1790/1800"

    def test_more_than_two_years_uses_first_two(self):
        assert coerce("document mentions 1790, 1800, and 1810 in passing") == "1790/1800"


class TestUnusualFormats:
    def test_two_digit_year_with_uu_suffix(self):
        assert coerce("18uu") == "18XX"

    def test_bracketed_two_digit_year_with_uu_suffix(self):
        assert coerce("[18uu]") == "18XX"

    def test_three_digit_year_with_question_mark(self):
        assert coerce("178?") == "178X"

    def test_trailing_s_century(self):
        result = coerce("1800s")
        assert result == "1800/1899"

    def test_four_digit_int(self):
        assert coerce("1850") == "1850"

    def test_leading_hyphen(self):
        assert coerce("-1850") == "/1850"
