"""EDTF formatter: convert an AST back to its canonical string representation.

Provides a guaranteed round-trip: ``format(parse(s)) == s`` for any valid *s*.
"""

from datelib.types import (
    EDTF,
    YM,
    YMD,
    Consecutive,
    DateAnnotated,
    Interval,
    ListEDTF,
    LongYear,
    SeasonValue,
    UnspecifiedValue,
    Y,
)


def _format_concrete(value) -> str:
    """Format a concrete value (without qualifiers)."""
    match value:
        case YMD(year, month, day):
            return f"{year:04d}-{month:02d}-{day:02d}"
        case YM(year, month):
            return f"{year:04d}-{month:02d}"
        case Y(year):
            return f"{year:04d}"
        case LongYear(year):
            if year < 0:
                return f"Y-{abs(year)}"
            return f"Y{year}"
        case SeasonValue(year, season):
            return f"{year:04d}-{season.value:02d}"
        case UnspecifiedValue(year, month, day):
            if day is not None:
                if year is not None and month is not None:
                    return f"{year}-{month}-{day}"
                raise ValueError("Invalid unspecified value: day without year/month")
            if month is not None:
                if year is not None:
                    return f"{year}-{month}"
                raise ValueError("Invalid unspecified value: month without year")
            if year is not None:
                return f"{year}"
            raise ValueError("Invalid UnspecifiedValue: no components")
        case _:
            raise ValueError(f"Unknown concrete value type: {type(value)}")


def _format_annotated(annotated: DateAnnotated) -> str:
    """Format a DateAnnotated value including qualifiers."""
    base = _format_concrete(annotated.value)
    if annotated.uncertain and annotated.approximate:
        return base + "%"
    if annotated.uncertain:
        return base + "?"
    if annotated.approximate:
        return base + "~"
    return base


def _format_endpoint(endpoint) -> str:
    """Format an interval endpoint."""
    match endpoint:
        case None:
            return ""
        case "open":
            return ".."
        case "unknown":
            return ""
        case DateAnnotated():
            return _format_annotated(endpoint)
        case _:
            raise ValueError(f"Unknown endpoint type: {type(endpoint)}")


def format(edtf: EDTF) -> str:  # noqa: A001
    """Format an EDTF AST as its canonical string representation.

    Examples
    --------
    >>> from datelib.parser import parse
    >>> ast = parse("1985-04-12").unwrap()
    >>> format(ast)
    '1985-04-12'
    """
    match edtf:
        case DateAnnotated():
            return _format_annotated(edtf)
        case Interval(lower, upper):
            return f"{_format_endpoint(lower)}/{_format_endpoint(upper)}"
        case Consecutive(lower, upper):
            left = _format_concrete(lower) if lower else ""
            right = _format_concrete(upper) if upper else ""
            return f"{left}..{right}"
        case ListEDTF(members, is_choice):
            delim = ","
            body = delim.join(format(m) for m in members)
            if is_choice:
                return f"[{body}]"
            return f"{{{body}}}"
        case _:
            raise ValueError(f"Unknown EDTF type: {type(edtf)}")
