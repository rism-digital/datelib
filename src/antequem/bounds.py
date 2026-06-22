"""Helpers for deriving simple year bounds from EDTF AST values."""

from __future__ import annotations

from antequem.types import (
    Consecutive,
    DateAnnotated,
    DateValue,
    EDTF,
    Endpoint,
    Interval,
    ListEDTF,
    LongYear,
    SeasonValue,
    UnspecifiedValue,
    Y,
    YM,
    YMD,
)


def _year_from_unspecified(text: str, fill: str) -> int | None:
    if len(text) != 4:
        return None
    if not all(ch.isdigit() or ch == "X" for ch in text):
        return None
    return int(text.replace("X", fill))


def _lower_year_from_value(value: DateValue | SeasonValue | UnspecifiedValue) -> int | None:
    match value:
        case YMD(year, _, _):
            return year
        case YM(year, _):
            return year
        case Y(year):
            return year
        case LongYear(year):
            return year
        case SeasonValue(year, _):
            return year
        case UnspecifiedValue(year, _, _):
            if year is None:
                return None
            return _year_from_unspecified(year, "0")


def _upper_year_from_value(value: DateValue | SeasonValue | UnspecifiedValue) -> int | None:
    match value:
        case YMD(year, _, _):
            return year
        case YM(year, _):
            return year
        case Y(year):
            return year
        case LongYear(year):
            return year
        case SeasonValue(year, _):
            return year
        case UnspecifiedValue(year, _, _):
            if year is None:
                return None
            return _year_from_unspecified(year, "9")


def _lower_year_from_endpoint(endpoint: Endpoint) -> int | None:
    if isinstance(endpoint, DateAnnotated):
        return _lower_year_from_value(endpoint.value)
    return None


def _upper_year_from_endpoint(endpoint: Endpoint) -> int | None:
    if isinstance(endpoint, DateAnnotated):
        return _upper_year_from_value(endpoint.value)
    return None


def lower_year(edtf: EDTF) -> int | None:
    """Return the lowest represented year for *edtf*, if one is available.

    Uncertainty and approximation qualifiers do not widen the returned year.
    For unspecified years such as ``201X`` or ``20XX``, the lower bound fills
    ``X`` digits with ``0``.
    """

    match edtf:
        case DateAnnotated(value, _, _):
            return _lower_year_from_value(value)
        case Interval(lower, _):
            return _lower_year_from_endpoint(lower)
        case Consecutive(lower, _):
            if lower is None:
                return None
            return _lower_year_from_value(lower)
        case ListEDTF():
            return None


def upper_year(edtf: EDTF) -> int | None:
    """Return the highest represented year for *edtf*, if one is available.

    Uncertainty and approximation qualifiers do not widen the returned year.
    For unspecified years such as ``201X`` or ``20XX``, the upper bound fills
    ``X`` digits with ``9``.
    """

    match edtf:
        case DateAnnotated(value, _, _):
            return _upper_year_from_value(value)
        case Interval(_, upper):
            return _upper_year_from_endpoint(upper)
        case Consecutive(_, upper):
            if upper is None:
                return None
            return _upper_year_from_value(upper)
        case ListEDTF():
            return None
