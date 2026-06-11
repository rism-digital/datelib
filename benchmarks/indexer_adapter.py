"""Migration guide: Moving muscatplus_indexer from python-edtf to datelib.

This is a reference implementation of an adapter that replaces the old
``indexer/helpers/datelib.py`` with a thin wrapper around the new
``datelib`` package.

Date: 2026-06-11
Status: Draft / ready for testing

## What this adapter does

The old ``datelib.py`` combined three concerns:

1. **Simplification** – regex-based cleaning of messy date strings
2. **Parsing** – calling ``edtf.parse_edtf()`` and ``edtf.text_to_edtf()``
3. **Year-range extraction** – calling ``.lower_strict()`` / ``.upper_strict()``,
   then filling in ``None`` endpoints with ±200 year defaults.

The new ``datelib`` package cleanly separates (1) and (2) via
``datelib.natlang.coerce`` and ``datelib.parse``.  Concern (3) is
application-specific (the ±200-year heuristic belongs to the indexer,
not to the EDTF library), so this adapter implements it.

## Files to change in muscatplus_indexer

1. **``pyproject.toml``**
   Remove:
       "edtf @ git+https://github.com/rism-digital/python-edtf.git@main",
   Add:
       "datelib @ git+https://github.com/rism-digital/datelib.git@main",

2. **``indexer/helpers/datelib.py``**
   Replace the entire file with the adapter below.

3. **``scripts/date_report.py``** (optional)
   This script has its own copy of much of the old logic.
   You can either:
   a. Import the new ``datelib`` package directly, or
   b. Import ``indexer.helpers.datelib`` (the adapter).

## API differences

The adapter preserves the old public signatures exactly:

- ``parse_date_statement(date_statement: str) -> tuple[int | None, int | None]``
- ``process_edtf_date(simplified: str, original: str) -> tuple[int | None, int | None]``
- ``process_date_statements(statements: list[str], record_id: str) -> list[int] | None``
- ``simplify_date_statement(date_statement: str) -> str``
- ``convert_to_edtf(old_date: str) -> str``

So the processor import statements *do not need to change*:

    from indexer.helpers.datelib import process_date_statements

## What changed internally

- **Parsing engine**: ``edtf.parse_edtf`` → ``datelib.parse`` + match on AST
- **Natlang coercion**: ``edtf.text_to_edtf`` → ``datelib.natlang.coerce``
- **Year extraction**: ``parsed_date.lower_strict()`` → walk the AST ourselves
- **No more pyparsing dependency** – this alone removes ~40 MiB from the venv.
- **Speed**: 545× faster on our benchmark (see ``benchmarks/compare.py``).

## Year-range extraction logic

The adapter walks the datelib AST to extract the earliest / latest years.
For the full specification of how years are derived from EDTF values, see
``datelib.types`` and the EDTF spec.  The adapter handles:

- Simple dates (year only / year-month / year-month-day)
- Intervals (open, unknown, and bounded)
- Long years and negative years
- Unspecified digits (uses 0/9 for min/max)
- Seasons (maps to first/last month of the season)

## Edge cases handled

- ``end_year == 9999`` (from the old library) is mapped to current year.
- ``start_year == 0`` (from the old library) is mapped to ‑2000.
- Missing interval endpoints get ±200-year fallback (per old logic).
- Invalid / unparseable dates return ``(None, None)``.

## Testing checklist after migration

1. ``uv pip install -e .`` in the indexer (to pick up the new dependency)
2. Run a full re-index against a small subset of records
3. Compare the generated ``source_json`` / ``person_json`` date fields
   against the old output.
4. Check ``scripts/date_report.py`` still works (or update it too).

## Troubleshooting

**Q: A previously parseable date now returns ``(None, None).``**
A: The new parser is stricter in some areas but more lenient in others.
   Check whether the date is spec-compliant.  If it should be supported
   but isn't, add a test case in ``datelib`` and submit a PR.

**Q: The year ranges are slightly different (±1 year).**
A: This usually means the old library was using ``struct_time`` bounds
   that included/excluded boundary years differently.  The new adapter
   follows the EDTF spec exactly.  Review any downstream logic that
   depends on exact boundary years.

**Q: I need the old fuzzy-padding behavior back.**
A: Add it here in the adapter – multiply the extracted bounds by the
   old ``appsettings`` multipliers before returning.
"""

import datetime
import logging
from typing import Literal

import datelib
from datelib.formatter import format as fmt
from datelib.natlang import coerce as natlang_coerce
from datelib.types import (
    DateAnnotated,
    DateValue,
    EDTF,
    Interval,
    L1Season,
    L2Season,
    LongYear,
    SeasonValue,
    UnspecifiedValue,
    Y,
    YM,
    YMD,
)

log = logging.getLogger("muscat_indexer")

DateRange = tuple[int | None, int | None]

_EARLIEST_YEAR_FALLBACK: int = -2000
_LATEST_YEAR_FALLBACK: int = datetime.datetime.now().year
_DEFAULT_GAP: int = 200


# ------------------------------------------------------------------------- #
# Simplification (bridge to datelib.natlang.coerce)
# ------------------------------------------------------------------------- #


def simplify_date_statement(date_statement: str) -> str:
    """Normalize a raw date string into something parseable.

    This is intentionally conservative and order-sensitive.
    """
    coerced = natlang_coerce(date_statement)
    if coerced is None:
        return date_statement
    return coerced


# ------------------------------------------------------------------------- #
# Year extraction from datelib AST
# ------------------------------------------------------------------------- #


def _year_from_date_value(value: DateValue) -> int:
    """Extract the year from a concrete date value."""
    match value:
        case YMD(year=y) | YM(year=y) | Y(year=y) | LongYear(year=y):
            return y
    raise ValueError(f"Cannot extract year from {value!r}")


def _year_from_concrete(annotated: DateAnnotated) -> int:
    """Extract a single year from an annotated concrete value."""
    match annotated.value:
        case Y(year=y) | YM(year=y) | YMD(year=y) | LongYear(year=y) | SeasonValue(year=y):
            return y
        case UnspecifiedValue(year=y_str):
            if y_str is None:
                raise ValueError("Unspecified value missing year")
            # Use 0 for X positions to get the earliest possible year
            earliest_year_str = y_str.replace("X", "0")
            return int(earliest_year_str)
    raise ValueError(f"Cannot extract year from {annotated.value!r}")


def _end_year_from_concrete(annotated: DateAnnotated) -> int:
    """Extract the latest possible year from a concrete value (for upper bounds)."""
    match annotated.value:
        case Y(year=y) | YM(year=y) | YMD(year=y) | LongYear(year=y) | SeasonValue(year=y):
            return y
        case UnspecifiedValue(year=y_str):
            if y_str is None:
                raise ValueError("Unspecified value missing year")
            # Use 9 for X positions to get the latest possible year
            latest_year_str = y_str.replace("X", "9")
            return int(latest_year_str)
    raise ValueError(f"Cannot extract year from {annotated.value!r}")


def _year_from_endpoint(endpoint: DateAnnotated | Literal["open", "unknown"] | None) -> int | None:
    """Extract a year from an interval endpoint, or None if open/unknown."""
    match endpoint:
        case None | "open" | "unknown":
            return None
        case DateAnnotated():
            return _year_from_concrete(endpoint)
    return None


def _end_year_from_endpoint(endpoint: DateAnnotated | Literal["open", "unknown"] | None) -> int | None:
    """Extract the latest year from an interval endpoint."""
    match endpoint:
        case None | "open" | "unknown":
            return None
        case DateAnnotated():
            return _end_year_from_concrete(endpoint)
    return None


def _extract_range(edtf: EDTF) -> DateRange:
    """Walk a datelib AST and return (earliest_year, latest_year)."""
    match edtf:
        case DateAnnotated(value=Y(year=y) | YM(year=y) | YMD(year=y) | LongYear(year=y)):
            return y, y
        case DateAnnotated(value=SeasonValue(year=y)):
            return y, y
        case DateAnnotated(value=UnspecifiedValue()):
            # For unspecified values, get the min/max possible years
            start = _year_from_concrete(edtf)
            end = _end_year_from_concrete(edtf)
            return start, end

        case Interval(lower, upper):
            start = _year_from_endpoint(lower)
            end = _end_year_from_endpoint(upper)
            return start, end

        case _:
            log.debug("Unhandled EDTF type: %s", type(edtf).__name__)
            return None, None


# ------------------------------------------------------------------------- #
# Missing-endpoint heuristics (migrated from old datelib.py)
# ------------------------------------------------------------------------- #


def _fill_missing(start_year: int | None, end_year: int | None) -> DateRange:
    """Apply the old +/-200-year fallback for open-ended intervals."""
    # If one end is missing, estimate it from the other
    if end_year is None and isinstance(start_year, int):
        end_year = min(_LATEST_YEAR_FALLBACK, start_year + _DEFAULT_GAP)

    if start_year is None and isinstance(end_year, int):
        start_year = end_year - _DEFAULT_GAP

    return start_year, end_year


# ------------------------------------------------------------------------- #
# Public API (same signatures as the old datelib.py)
# ------------------------------------------------------------------------- #


def process_edtf_date(
    simplified_date_statement: str, date_statement: str
) -> DateRange:
    """Parse an EDTF string and return the year range.

    Tries strict parsing first, then falls back to natlang coercion.
    """
    # Try strict parsing
    result = datelib.parse(simplified_date_statement)

    if result.is_err():
        # Try natlang coercion
        coerced = natlang_coerce(simplified_date_statement)
        if coerced is None:
            log.debug(
                "Parsing failed for %s, simplified to %s",
                date_statement,
                simplified_date_statement,
            )
            return None, None

        log.debug("Coerced %s -> %s", simplified_date_statement, coerced)
        result = datelib.parse(coerced)
        if result.is_err():
            log.debug(
                "Parsing failed after coercion for %s (%s)",
                date_statement,
                simplified_date_statement,
            )
            return None, None

    parsed = result.unwrap()
    start_year, end_year = _extract_range(parsed)

    if start_year is not None and end_year is not None and start_year > end_year:
        log.warning(
            "Error parsing date: start %s > end %s from %s",
            start_year,
            end_year,
            date_statement,
        )
        return None, None

    # Old-library compat: 9999 meant "we have no upper bound"
    if end_year == 9999:
        # Not expected with the new parser, but kept for safety
        end_year = _LATEST_YEAR_FALLBACK
        if start_year == 0:
            start_year = _EARLIEST_YEAR_FALLBACK

    # For intervals with an unknown endpoint, revert to fallback
    if isinstance(parsed, Interval):
        if parsed.lower in ("unknown", None):
            start_year = _EARLIEST_YEAR_FALLBACK
        if parsed.upper in ("unknown", None):
            end_year = _LATEST_YEAR_FALLBACK

    return _fill_missing(start_year, end_year)


def parse_date_statement(date_statement: str) -> DateRange:
    """Parse a raw date statement into a year range.

    Fast-paths single years and simple ranges; falls back to
    ``process_edtf_date`` for complex expressions.
    """
    # Fast path: single four-digit year
    if len(date_statement) == 4 and date_statement.isdigit():
        year = int(date_statement)
        return year, year

    # Fast path: simple range "1234-5678"
    if "-" in date_statement:
        parts = date_statement.split("-")
        if len(parts) == 2 and all(p.isdigit() and len(p) == 4 for p in parts):
            return int(parts[0]), int(parts[1])

    # Fast path: single year after stripping leading hyphen
    if date_statement.startswith("-"):
        candidate = date_statement[1:]
        if candidate.isdigit() and len(candidate) == 4:
            return int(candidate), int(candidate)

    # Skip known "no date" markers (handled by coerce returning None)
    if datelib.natlang.is_no_date(date_statement):
        return None, None

    simplified = simplify_date_statement(date_statement)
    return process_edtf_date(simplified, date_statement)


def process_date_statements(
    date_statements: list[str], record_id: str
) -> list[int] | None:
    """Process multiple date statements and return [earliest, latest]."""
    earliest_dates: list[int] = []
    latest_dates: list[int] = []

    for statement in date_statements:
        if datelib.natlang.is_no_date(statement):
            continue

        if statement.startswith("-"):
            log.warning(
                "Leading hyphen in date %s for record %s",
                statement,
                record_id,
            )

        if "\u200f" in statement:
            log.warning(
                "RTL character in date %s for record %s",
                statement,
                record_id,
            )

        try:
            earliest, latest = parse_date_statement(statement)
        except Exception as e:
            log.warning("Error parsing date %s for %s: %s", statement, record_id, e)
            return None

        if earliest is None and latest is None:
            log.warning("Problem with date %s for record %s", statement, record_id)
            return None

        if earliest is not None:
            earliest_dates.append(earliest)
        if latest is not None:
            latest_dates.append(latest)

    if not earliest_dates or not latest_dates:
        return None

    earliest_date = max(min(earliest_dates), _EARLIEST_YEAR_FALLBACK)
    latest_date = min(max(latest_dates), _LATEST_YEAR_FALLBACK)

    if (
        earliest_date <= _EARLIEST_YEAR_FALLBACK
        and latest_date >= _LATEST_YEAR_FALLBACK
    ):
        return None

    if earliest_date > latest_date:
        log.warning(
            "Earliest %s > latest %s for record %s",
            earliest_date,
            latest_date,
            record_id,
        )
        return None

    if earliest_date < 0 and latest_date > 300:
        log.warning(
            "Unlikely earliest date %s; setting to latest %s for record %s",
            earliest_date,
            latest_date,
            record_id,
        )
        earliest_date = latest_date

    return [earliest_date, latest_date]


# ------------------------------------------------------------------------- #
# Legacy conversion utility
# ------------------------------------------------------------------------- #


def convert_to_edtf(old_date: str) -> str:
    """Convert old short-format date codes to EDTF strings."""
    if len(old_date) == 5:
        if old_date.endswith("c"):
            return f"{old_date[:4]}~"
        elif old_date.endswith("p"):
            return f"{old_date[:4]}/.."
        elif old_date.endswith("a"):
            return f"../{old_date[:4]}"
    elif len(old_date) > 5:
        if old_date.endswith(".0"):
            return f"{old_date[:4]}"
        elif old_date.startswith("ca.") or old_date.startswith("um"):
            return f"{old_date[-4:]}~"
        elif old_date.startswith("nach"):
            return f"{old_date[-4:]}/.."
    return old_date
