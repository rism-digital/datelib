"""Tests for datelib.bounds."""

from datelib import lower_year, parse, upper_year
from datelib.types import DateAnnotated, ListEDTF, UnspecifiedValue, Y


class TestYearBounds:
    def test_year_only(self):
        ast = parse("1850").unwrap()
        assert lower_year(ast) == 1850
        assert upper_year(ast) == 1850

    def test_month_and_day_precision_ignore_subyear(self):
        ast = parse("1850-04-12").unwrap()
        assert lower_year(ast) == 1850
        assert upper_year(ast) == 1850

    def test_qualifiers_do_not_widen_year(self):
        ast = parse("1850%").unwrap()
        assert lower_year(ast) == 1850
        assert upper_year(ast) == 1850

    def test_unspecified_decade(self):
        ast = parse("201X").unwrap()
        assert lower_year(ast) == 2010
        assert upper_year(ast) == 2019

    def test_unspecified_century(self):
        ast = parse("20XX").unwrap()
        assert lower_year(ast) == 2000
        assert upper_year(ast) == 2099

    def test_interval(self):
        ast = parse("1984?/2004~").unwrap()
        assert lower_year(ast) == 1984
        assert upper_year(ast) == 2004

    def test_open_interval(self):
        ast = parse("/1985").unwrap()
        assert lower_year(ast) is None
        assert upper_year(ast) == 1985

    def test_unknown_interval_endpoint(self):
        ast = parse("1985/").unwrap()
        assert lower_year(ast) == 1985
        assert upper_year(ast) is None

    def test_list_is_ambiguous(self):
        ast = ListEDTF([DateAnnotated(Y(1850)), DateAnnotated(Y(1900))], is_choice=True)
        assert lower_year(ast) is None
        assert upper_year(ast) is None

    def test_unspecified_without_year_returns_none(self):
        ast = DateAnnotated(UnspecifiedValue(month="XX"))
        assert lower_year(ast) is None
        assert upper_year(ast) is None
