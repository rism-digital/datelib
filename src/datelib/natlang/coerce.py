"""Coerce a wide range of natural language and messy date formats into EDTF.

Based on patterns from the MuscatPlus indexer ``datelib.py``.

Examples of supported inputs::

    "circa 1850"   → "1850~"
    "ca. 1800"     → "1800~"
    "18th century" → "1701/1800"
    "18th c."      → "1701/1800"
    "18/19"        → "1701/1899"
    "1850-1860"    → "1850/1860"
    "between 1790 and 1800" → "1790/1800"
    "s.a."         → None (represents 'no date')
    "17.3q"        → "1650/1674" (17th century, 3rd quarter)
    "1800s"        → "1800/1899"
    "1850*"        → "1850/1949" (birth date approximation)
    "before 1900"  → "/1900"
    "after 1800"   → "1800/"
    "/12/1850"    → "1850-12-??" (dd/mm/yyyy)
    "1.1.1850"    → "1850-01-01" (dd.mm.yyyy)

The design philosophy is: be generous going in, and return ``None`` when we
can't make sense of the string.  Callers can then feed the resulting EDTF
string to :func:`datelib.parse` for full validation and AST construction.
"""

from __future__ import annotations

import math
import re

# -------------------------------------------------------------------------- #
# Constants
# -------------------------------------------------------------------------- #

_EARLY_CENTURY_END: int = 10
_LATE_CENTURY_START: int = 90

NO_DATE_VALUES: set[str | None] = {
    None,
    "",
    "[s.a.]",
    "[s. a.]",
    "s.a.",
    "s/d",
    "n/d",
    "(s.d.)",
    "[s.d.]",
    "[s.d]",
    "[s. d.]",
    "s. d.",
    "s.d.",
    "[n.d.]",
    "n. d.",
    "n.d.",
    "[n. d.]",
    "[o.J]",
    "o.J",
    "o.J.",
    "[s.n.]",
    "(s. d.)",
    "[s.l.]",
    "[s.a]",
    "xxxx-xxxx",
    "uuuu-uuuu",
    "?",
    "??",
    "[s..d]",
    "s/f",
    "[s.d. ]",
    "[s,d,]",
    "[s.t.]",
    "[o. J.]",
    "s.d",
    "[s.d.}",
    "o.d.",
    "s.t.",
    "[o.J.]",
    "(n.d.)",
    "[without]",
    "[s .a.]",
    "[s/d/]",
    "[s.d.[",
    "[s.c.]",
    "s/ d",
    "[?]",
    "[s,d.]",
    "[sd]",
    "(s.d)",
    "unk",
    "unknown",
    "[s. f.]",
    "[s. n.]",
    "[s. d,]",
    "[sine anno]",
    "XVI-XVIII",
    "XVII-XIX",
    "[20th c.]",
    "XIX-XX",
    "Año X",
    "(ohne Datum)",
}


# -------------------------------------------------------------------------- #
# Regex helpers
# -------------------------------------------------------------------------- #

_SIMPLE_SINGLE_YEAR_RE = re.compile(r"^(?P<year>\d{4})$")
_SIMPLE_RANGE_RE = re.compile(r"^(?P<first>\d{4})-(?P<second>\d{4})$")
_SIMPLE_SLASH_RANGE_RE = re.compile(r"^(?P<first>\d{4})/(?P<second>\d{4})$")

# dd/mm/yyyy
_SLASH_DIVIDED_RE = re.compile(
    r"^(?P<day>\d{2})/(?P<month>\d{2})/(?P<year>\d{4})"
)

# Alternative: year month/day
_ALT_DIVIDED_RE = re.compile(
    r"^(?P<year>\d{4})(?P<month>\d{2})/(?P<day>\d{2})"
)

# NNNN---- or NNNNNN--
_ALT_DASHED_RE = re.compile(r"^(?P<year>\d{4})(?P<month>-{2}|\d{2})--")

_DOT_DIVIDED_RE = re.compile(
    r"(\d{1,2}\.)?(\d{1,2})\.(\d{4})(-(\d{1,2}\.)?(\d{1,2})\.(\d{4}))?"
)

# Normalise missing spaces after prefixes: "ca.1780" → "ca. 1780"
_PREFIX_SPACE_RE = re.compile(
    r"(ca\.?|c\.|circa|um|approx\.?|approximately|around|about)(\d)",
    re.IGNORECASE,
)

_MONTHS: list[str] = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]

_MONTHS_RE = "|".join(_MONTHS)

# Matches English century expressions
# With adjective: "16th century, second half"
# Bare: "18th century"
_CENTURY_EN_RE = re.compile(
    r"^(?P<century>\d{1,2})(?:th|st|rd|nd) "
    r"century(?:, (?P<adj1>\w+)(?: (?P<adj2>\w+))?)?$",
    re.IGNORECASE,
)

_CENTURY_CODE_RE = re.compile(
    r"^(?P<century>\d{2})\.(?P<adj1>[\diesm])" r"(?P<adj2>[dqhtnxce])?$"
)

_CENTURY_DASHES_RE = re.compile(r"^(\d\d)(?:--|\?\?)$")
_CENTURY_TRUNCATED_RE = re.compile(r"^(?P<first>\d{2})/(?P<second>\d{2})$")

_MULTI_YEAR_RE = re.compile(
    r"^(?P<first>\d{4})-\d{2}-\d{2}-(?P<second>\d{4})-\d{2}-\d{2}"
)

_STRIP_LETTERS_RE = re.compile(r"(?P<year>\d{3,4})[cpqa!]")

_EXPLICIT_BETWEEN_RE = re.compile(
    r"^.*(?:between|entre|um|von|vor|et).*(?P<first>\d{4}).*(?P<second>\d{4}).*$",
    re.IGNORECASE,
)

_PARENTHETICAL_APPENDAGES1_RE = re.compile(r"(?P<range>\d{4}-\d{4})\s+\(.*\)")
_PARENTHETICAL_APPENDAGES2_RE = re.compile(r"(?P<year>\d{4})\s+\(.*\)")

# Strip trailing century abbreviations like ".sc" (Portuguese "século")
_SC_RE = re.compile(r"\.sc$", re.IGNORECASE)

_ZERO_DAY_RE = re.compile(r"^(?P<year>\d{4})-\d{2}-(00|XX)$")
_MUSHED_TOGETHER_RE = re.compile(r"(?P<first>\d{4})\d{4}")
_MUSHED_TOGETHER_RANGE_RE = re.compile(
    r"(?P<first>\d{4})\d{4}-(?P<second>\d{4})\d{4}"
)

# Matches dd-mm-yyyy after dots have been converted to dashes
_DD_MM_YYYY_RE = re.compile(
    r"^(?P<day>\d{1,2})-(?P<month>\d{1,2})-(?P<year>\d{4})$"
)

# Month-name dates: "August 22, 1785" or "22 August 1785"
_MONTH_NAME_RE = re.compile(
    rf"^(?P<month>{_MONTHS_RE})\s+(?P<day>\d{{1,2}}(?:st|nd|rd|th|d)?),?\s+(?P<year>\d{{4}})$",
    re.IGNORECASE,
)
_MONTH_NAME_DD_RE = re.compile(
    rf"^(?P<day>\d{{1,2}}(?:st|nd|rd|th|d)?)\s+(?P<month>{_MONTHS_RE})\s+(?P<year>\d{{4}})$",
    re.IGNORECASE,
)

# Alternate comma placement: "April, 30th 1814"
_MONTH_NAME_COMMA_RE = re.compile(
    rf"^(?P<month>{_MONTHS_RE}),\s+(?P<day>\d{{1,2}}(?:st|nd|rd|th|d)?)\s+(?P<year>\d{{4}})$",
    re.IGNORECASE,
)

# Month-year only (no day): "August 1785"
_MONTH_YEAR_RE = re.compile(
    rf"^(?P<month>{_MONTHS_RE})\s+(?P<year>\d{{4}})$",
    re.IGNORECASE,
)

# Requires one of the listed prefixes (NOT optional)
_CIRCA_RE = re.compile(
    r'^(ca\.?\s+|c\.\s+|circa\s+|um\s+|approx\.?\s+|approximately\s+|around\s+|about\s+)(?P<year>\d{4})$'
)

_CIRCA_RANGE_RE = re.compile(
    r'^(ca\.?\s+|c\.\s+|circa\s+|um\s+|approx\.?\s+|approximately\s+|around\s+|about\s+)'
    r'(?P<first>\d{4})-(?P<second>\d{4})$'
)

_BEFORE_RE = re.compile(r'(not after|avant|before|earlier|vor)\s+(?P<year>\d{4})')
_AFTER_RE = re.compile(r'(not before|since|after|later|apr[eé]s|apres|nach)\s+(?P<year>\d{4})$')

_CENTURY_SHORT_RE = re.compile(
    r'^(?P<century>\d{2})(?:th|st|rd|nd)?\s*(?:[Cc]\.?|sc\.?)?$'
)

_SIMPLIFICATION_RULES = [
     (_STRIP_LETTERS_RE, r"\g<year>"),
     (_ZERO_DAY_RE, r"\g<year>"),
     (_MUSHED_TOGETHER_RANGE_RE, r"\g<first>/\g<second>"),
     (_MULTI_YEAR_RE, r"\g<first>/\g<second>"),
     (_EXPLICIT_BETWEEN_RE, r"\g<first>/\g<second>"),
     (_MUSHED_TOGETHER_RE, r"\g<first>"),
     (_PARENTHETICAL_APPENDAGES1_RE, r"\g<range>"),
     (_PARENTHETICAL_APPENDAGES2_RE, r"\g<year>"),
      (_SC_RE, r""),
]


# -------------------------------------------------------------------------- #
# Internal helpers
# -------------------------------------------------------------------------- #


def _simplify(statement: str) -> str | None:
    """Normalize a raw date string into something parseable.

    Returns ``None`` if the input is a known "no date" marker.
    """
    if statement in NO_DATE_VALUES:
        return None

    s = statement

    if s.startswith("-"):
        s = s[1:]

     # Strip wrapper characters (quotes, brackets) so inner text is exposed.
     # Do this *before* any pattern checks so expressions like "[17??]"
     # are reduced to "17??" and can match century-dashes notation.
    s = s.strip().strip('"')
    s = re.sub(r"[\[\]]", "", s)

     # Strip common date qualifiers that are prefixes only
    s = re.sub(r"^(copie?d?|copia?|see|from\s+|dated\s+|copy\s+)", "", s, flags=re.IGNORECASE)

    # Normalize typographic dashes to plain hyphens, and trim spaces
    # around range markers.
    s = s.replace("\u2012", "-").replace("\u2013", "-")  # en-dash, em-dash
    s = re.sub(r"\s*-\s*", "-", s)
    s = re.sub(r"\s*/\s*", "/", s)

    # Insert a space between prefix patterns and digits when missing
    # so "ca.1780-1790" is normalised to "ca. 1780-1790".
    s = _PREFIX_SPACE_RE.sub(r"\1 \2", s)

    # Check for century dashes notation (17-- or 17??) BEFORE stripping
    # the ``?`` character globally, because ``??`` is part of the notation.
    if _CENTURY_DASHES_RE.match(s):
        return s

    # Now safe to strip remaining ``?`` characters (uncertainty markers
    # that are NOT part of century-dashes notation).
    s = s.replace("(?)", "?")
    s = re.sub(r"\?", "", s)

    # Convert dot-separated dates (dd.mm.yyyy) to dash-separated
    if _DOT_DIVIDED_RE.match(s):
        s = s.replace(".", "-")

    # Apply ordered simplification rules
    for pattern, replacement in _SIMPLIFICATION_RULES:
        s = pattern.sub(replacement, s)

    # Drop any remaining parentheses anywhere
    s = re.sub(r"[()]", "", s)

    # Normalize whitespace
    s = s.strip()

    # Normalize semantic phrases EDTF understands
    s = s.replace("not after", "before").replace("not before", "after").strip()

    return s


def _parse_numeric_ordinal(ordinal: str) -> int | None:
    """Convert ordinal word or number (e.g. '2nd', 'first') to a digit."""
    ordinal_map = {
        "1st": 1,
        "2nd": 2,
        "3rd": 3,
        "4th": 4,
    }
    mapped = ordinal_map.get(ordinal)
    if mapped is not None:
        return mapped
    # Try stripping suffixes from bare numbers like "2nd" → 2
    clean = ordinal.rstrip("stndrh")
    if clean.isdigit():
        return int(clean)
    return None


def _parse_century_fraction(
    century_start: int,
    ordinal: str,
    period: str,
) -> tuple[int, int] | None:
    """Parse century fraction expressions like '18.2d' or '17.3q'.

    The *century_start* should already be the start of the actual years,
    e.g. for '20th century' it should be 1900.
    """
    periods = {
        "half": 2,
        "h": 2,
        "third": 3,
        "t": 3,
        "quarter": 4,
        "q": 4,
        "decade": 10,
        "d": 10,
        "n": 10,
        "x": 10,
        "century": 1,
        "c": 1,
        "e": 1,
    }

    divider = periods.get(period)
    if divider is None:
        return None

    multiplier: int | None = None
    if ordinal.isdigit():
        multiplier = int(ordinal)
    else:
        multiplier = _parse_numeric_ordinal(ordinal)
        if multiplier is None:
            word_map = {
                "first": 1,
                "i": 1,
                "second": 2,
                "third": 3,
                "fourth": 4,
                "last": divider,
                "e": divider,
                "s": divider,
                "m": divider,
            }
            multiplier = word_map.get(ordinal.lower())

    if multiplier is None or multiplier < 1 or multiplier > divider:
        return None

    period_years = math.floor(100 / divider)
    return (
        century_start + (multiplier - 1) * period_years,
        century_start + multiplier * period_years,
    )


def _parse_century_adjective(
    century_start: int,
    adjective: str,
) -> tuple[int, int] | None:
    """Handle descriptors like 'early', 'late', 'middle'."""
    if adjective in ("beginning", "start", "early"):
        return century_start, century_start + _EARLY_CENTURY_END
    if adjective in ("late", "end"):
        return century_start + _LATE_CENTURY_START, century_start + 100
    if adjective == "middle":
        return century_start + 25, century_start + 75
    return None


def _century_to_edtf(century: int) -> str:
    """Convert a century number (1-based) into an EDTF interval string.

    Uses human convention where the 18th century runs 1701–1800.
    """
    start = (century - 1) * 100 + 1
    end = century * 100
    return f"{start:04d}/{end:04d}"


# -------------------------------------------------------------------------- #
# Coercion strategies (return an EDTF string or None)
# -------------------------------------------------------------------------- #


def _coerce_simple(s: str) -> str | None:
    """Try the simplest patterns: single year, year range, slash dates."""
    # Already valid ISO-like date — pass through unchanged.
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s

    # Single four-digit year
    if m := _SIMPLE_SINGLE_YEAR_RE.match(s):
        return m.group("year")

    # Simple range 1234-5678
    if m := _SIMPLE_RANGE_RE.match(s):
        return f"{m.group('first')}/{m.group('second')}"

    # Slash range 1234/5678
    if m := _SIMPLE_SLASH_RANGE_RE.match(s):
        return s

    # dd-mm-yyyy (after dots converted to dashes)
    if m := _DD_MM_YYYY_RE.match(s):
        return (
            f"{m.group('year')}-"
            f"{int(m.group('month')):02d}-"
            f"{int(m.group('day')):02d}"
        )

    # dd/mm/yyyy
    if m := _SLASH_DIVIDED_RE.match(s):
        return (f"{m.group('year')}-"
                f"{m.group('month')}-{m.group('day')}")

    # Alternative: NNNNNN/NN
    if m := _ALT_DIVIDED_RE.match(s):
        y = m.group("year")
        mo = m.group("month")
        return f"{y}-{mo}"

    # Alternative: NNNN----
    if m := _ALT_DASHED_RE.match(s):
        y = m.group("year")
        mo = m.group("month")
        if mo == "--":
            return y
        return f"{y}-{mo}"

    return None


def _day_ordinal_to_int(day_str: str) -> int:
    """Strip ordinal/abbreviated day suffix (st|nd|rd|th|d) and return the numeric day."""
    return int(re.sub(r"(?:st|nd|rd|th)$|d$", "", day_str, flags=re.IGNORECASE))


def _coerce_month_name_date(s: str) -> str | None:
    """Handle dates with spelled-out month names, e.g. 'August 22, 1785'."""
    if m := _MONTH_NAME_RE.match(s):
        month = m.group("month").lower()
        month_num = _MONTHS.index(month) + 1
        return (
            f"{m.group('year')}-"
            f"{month_num:02d}-"
            f"{_day_ordinal_to_int(m.group('day')):02d}"
        )

    if m := _MONTH_NAME_DD_RE.match(s):
        month = m.group("month").lower()
        month_num = _MONTHS.index(month) + 1
        return (
            f"{m.group('year')}-"
            f"{month_num:02d}-"
            f"{_day_ordinal_to_int(m.group('day')):02d}"
        )

    if m := _MONTH_NAME_COMMA_RE.match(s):
        month = m.group("month").lower()
        month_num = _MONTHS.index(month) + 1
        return (
            f"{m.group('year')}-"
            f"{month_num:02d}-"
            f"{_day_ordinal_to_int(m.group('day')):02d}"
        )

    if m := _MONTH_YEAR_RE.match(s):
        month = m.group("month").lower()
        month_num = _MONTHS.index(month) + 1
        return f"{m.group('year')}-{month_num:02d}"

    return None


def _coerce_century_expression(s: str) -> str | None:
    """Handle century-related expressions."""
    # Century dashes: 17-- or 17??
    if m := _CENTURY_DASHES_RE.match(s):
        century = int(m.group(1))
        start = (century - 1) * 100 + 1
        return f"{start:04d}/{start + 99:04d}"

    # Century range: 18/19 (18th-19th century overlap)
    if m := _CENTURY_TRUNCATED_RE.match(s):
        first = (int(m.group("first")) - 1) * 100 + 1
        second = int(m.group("second")) * 100
        return f"{first:04d}/{second:04d}"

    # Short century notation: 16th c. or 16C
    if m := _CENTURY_SHORT_RE.match(s):
        return _century_to_edtf(int(m.group("century")))

    # English century notation: "16th century, second half" | "18th century"
    if m := _CENTURY_EN_RE.match(s):
        century_num = int(m.group("century"))
        adj1 = m.group("adj1")
        adj2 = m.group("adj2")

        if adj1 is None:
            return _century_to_edtf(century_num)

        century_start = (century_num - 1) * 100
        adj1 = adj1.lower()

        if adj2:
            result = _parse_century_fraction(century_start, adj1, adj2)
        else:
            result = _parse_century_adjective(century_start, adj1)

        if result:
            return f"{result[0]:04d}/{result[1]:04d}"

    # Code notation: 18.2d (18th century, 2nd decade), 19.in (19th, beginning)
    if m := _CENTURY_CODE_RE.match(s):
        century_num = int(m.group("century"))
        century_start = (century_num - 1) * 100
        adj1 = m.group("adj1").lower()
        adj2 = m.group("adj2")

        if adj2:
            result = _parse_century_fraction(century_start, adj1, adj2)
        else:
            result = _parse_century_adjective(century_start, adj1)

        if result:
            return f"{result[0] + 1:04d}/{result[1]:04d}"
        # Fallback: treat as full century
        return _century_to_edtf(century_num)

    return None


def _coerce_approximate_boundaries(s: str) -> str | None:
    """Handle 'circa', 'ca.', 'before', 'after', etc."""
    # Circa range: ca. 1780-1790  → 1780~/1790~
    if m := _CIRCA_RANGE_RE.match(s):
        return f"{m.group('first')}~/{m.group('second')}~"

    # Circa / approximate single year
    if m := _CIRCA_RE.match(s):
        return f"{m.group('year')}~"

    if s.lower().startswith("circa "):
        year_part = s[6:].strip()
        if year_part.isdigit() and len(year_part) == 4:
            return f"{year_part}~"

    # Not after / before
    if m := _BEFORE_RE.match(s):
        return f"/{m.group('year')}"

    # Not before / after / since
    if m := _AFTER_RE.match(s):
        return f"{m.group('year')}/"

    return None


def _coerce_birth_death(s: str) -> str | None:
    """Handle birth/death date gap markers (*, +)."""
    stripped = s.rstrip("*+")
    if stripped != s and len(stripped) == 4 and stripped.isdigit():
        year = int(stripped)
        if s.endswith("*"):
            return f"{year}/"            # open end (birth)
        if s.endswith("+"):
            return f"/{year}"            # open start (death)
    return None


def _coerce_unusual_year(s: str) -> str | None:
    """Handle mushed-together dates and other odd formats."""
    # 1800s → 1800/1899 (century implied by trailing s)
    if re.match(r"^\d{4}s$", s):
        # Interpret as a century, e.g. "1800s" = 18th century
        year_start = int(s[:4])
        return f"{year_start}/{year_start + 99}"

    # Cleaned integer standing alone
    if s.isdigit() and len(s) == 4:
        return s

    return None


# -------------------------------------------------------------------------- #
# Public API
# -------------------------------------------------------------------------- #


def is_no_date(statement: str) -> bool:
    """Return whether *statement* is a known "no date" marker."""
    return statement in NO_DATE_VALUES


def coerce(statement: str) -> str | None:
    """Coerce a free-form date string into a valid EDTF string.

    Returns ``None`` if the string:
    - is a known "no date" marker, or
    - cannot be coerced into a valid EDTF representation.

    The result should be fed to :func:`datelib.parse` for full validation.

    Examples
    --------
    >>> coerce("circa 1850")
    '1850~'
    >>> coerce("18th century")
    '1701/1800'
    >>> coerce("s.a.")
    None
    """
    if is_no_date(statement):
        return None

    s = _simplify(statement)
    if s is None:
        return None

    # Prevent nonsense leading with Roman numeral-looking strings.
    # "XVI-XVIII" and "Año X" are known no-date markers; month names (April,
    # August) must be allowed through.
    if re.match(r"^Año\s", s) or re.match(r"^[XVILCDM]+(-[XVILCDM]+)?$", s):
        return None

    # 1. Simple formats (single year, range, slash dates) — must come first
    if result := _coerce_simple(s):
        return result

    # 1.5. Month-name dates (e.g. "August 22, 1785")
    if result := _coerce_month_name_date(s):
        return result

    # 2. Approximate / boundary markers (before/after/circa)
    if result := _coerce_approximate_boundaries(s):
        return result

    # 3. Birth/death markers
    if result := _coerce_birth_death(s):
        return result

    # 4. Century expressions (the richest family of patterns)
    if result := _coerce_century_expression(s):
        return result

    # 5. Mushed-together / unusual year formats
    if result := _coerce_unusual_year(s):
        return result

    return None
