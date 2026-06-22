"""EDTF validation utilities.

Post-parse semantic checks that cannot be expressed in the grammar alone.
"""

from antequem.result import Err, Ok, ParseError, Result
from antequem.types import (
    EDTF,
    YMD,
    ConcreteValue,
    DateAnnotated,
    Interval,
    L1Season,
    L2Season,
    LongYear,
    SeasonValue,
    UnspecifiedValue,
)

# Month lengths for a non-leap year.
_MONTH_LENGTHS = [
    0,  # dummy for 1-indexing
    31, 28, 31, 30, 31, 30,
    31, 31, 30, 31, 30, 31,
]


def _is_leap(year: int) -> bool:
    """Return whether *year* is a Gregorian leap year."""
    return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)


def _days_in_month(year: int, month: int) -> int:
    """Return the number of days in the given year and month."""
    if month == 2 and _is_leap(year):
        return 29
    return _MONTH_LENGTHS[month]


def _validate_concrete(value: ConcreteValue) -> Result[None, str]:
    """Validate a concrete value, returning an error message on failure."""
    match value:
        case YMD(year, month, day):
            if month < 1 or month > 12:
                return Err(f"Invalid month {month}")
            max_day = _days_in_month(year, month)
            if day < 1 or day > max_day:
                return Err(
                    f"Invalid day {day} for year {year}, month {month} "
                    f"(max {max_day})"
                )
            return Ok(None)

        case LongYear(year):
            if abs(year) < 10_000:
                return Err(
                    f"Long year must have magnitude ≥ 10000, got {year}"
                )
            return Ok(None)

        case SeasonValue(_, season):
            if not isinstance(season, (L1Season, L2Season)):
                return Err(f"Invalid season code {season}")
            return Ok(None)

        case UnspecifiedValue(year, month, day):
            # Validate unspecified values don't have internal X placement
            # (L1 only allows rightmost X in year, and full XX for month/day)
            if year is not None and len([c for c in year if c == "X"]) > 2:
                return Err(
                    "Unspecified year may only have 1 or 2 rightmost Xs"
                )
            if month is not None and month != "XX":
                if not month.isdigit():
                    return Err(f"Invalid month {month}")
                month_num = int(month)
                if month_num < 1 or month_num > 12:
                    return Err(f"Invalid month {month}")
            if day is not None and day != "XX":
                if month is None or month == "XX":
                    return Err("Specified day requires specified month")
                if year is None:
                    return Err("Specified day requires year")
                if not day.isdigit():
                    return Err(f"Invalid day {day}")
                year_num = int(year.replace("X", "0"))
                month_num = int(month)
                day_num = int(day)
                max_day = _days_in_month(year_num, month_num)
                if day_num < 1 or day_num > max_day:
                    return Err(
                        f"Invalid day {day_num} for year {year}, month {month} "
                        f"(max {max_day})"
                    )
            return Ok(None)

        case _:
            return Ok(None)


def _validate_interval(interval: Interval) -> Result[None, str]:
    """Validate an interval.

    Currently only checks that both endpoints are not fully open/unknown.
    Date-order validation would require resolving lower/upper bounds of
    uncertain/approximate dates which is out of scope for strict validation.
    """
    lower = interval.lower
    upper = interval.upper

    # An interval must have at least one defined endpoint
    if lower is None and upper is None:
        return Err("Interval must have at least one endpoint")

    # Both unknown is pointless but valid per the spec?  ("/")
    # We already handle that in the parser.

    return Ok(None)


def validate(edtf: EDTF) -> Result[EDTF, ParseError]:
    """Validate an EDTF AST.

    Returns the AST on success, or a ParseError with a validation message.

    Examples
    --------
    >>> from antequem.parser import parse
    >>> result = parse("1985-04-12")
    >>> validate(result.unwrap()).is_ok
    True
    >>> bad = parse("1985-04-31").unwrap()
    >>> validate(bad).is_err
    True
    """
    match edtf:
        case DateAnnotated(value, _, _):
            result = _validate_concrete(value)
            if result.is_err:
                return Err(
                    ParseError(result.unwrap_err(), 0, "")
                )
            return Ok(edtf)

        case Interval(lower, upper):
            for endpoint in (lower, upper):
                if isinstance(endpoint, DateAnnotated):
                    inner = _validate_concrete(endpoint.value)
                    if inner.is_err:
                        return Err(
                            ParseError(inner.unwrap_err(), 0, "")
                        )
            interval_result = _validate_interval(edtf)
            if interval_result.is_err:
                return Err(
                    ParseError(interval_result.unwrap_err(), 0, "")
                )
            return Ok(edtf)

        case _:
            return Ok(edtf)
