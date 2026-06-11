"""Coerce a wide range of natural language and messy date formats into EDTF.

Based on patterns from the MuscatPlus indexer ``datelib.py``.

Examples of supported inputs::

    "circa 1850"   -> "1850~"
    "ca. 1800"     -> "1800~"
    "18th century" -> "1701/1800"
    "18th c."      -> "1701/1800"
    "18/19"        -> "1701/1900"
    "1850-1860"    -> "1850/1860"
    "between 1790 and 1800" -> "1790/1800"
    "s.a."         -> None (represents 'no date')
    "17.3q"        -> "1651/1675" (17th century, 3rd quarter)
    "1800s"        -> "1800/1899"
    "1850*"        -> "1850/"
    "before 1900"  -> "/1900"
    "after 1800"   -> "1800/"
    "12/1850"      -> "1850-12"
    "1.1.1850"     -> "1850-01-01"

The design philosophy is: be generous going in, and return ``None`` when we
can't make sense of the string. Callers can then feed the resulting EDTF
string to :func:`datelib.parse` for full validation and AST construction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
import re

from datelib.parser import is_valid

try:
    from dateutil import parser as dateutil_parser
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    dateutil_parser = None


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


_MONTHS: list[str] = [
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
]
_MONTHS_RE = "|".join(_MONTHS)
_MONTH_TO_NUMBER = {month: index for index, month in enumerate(_MONTHS, start=1)}

_MONTH_NAME_RE = re.compile(
    rf"^(?P<month>{_MONTHS_RE})\s+"
    rf"(?P<day>\d{{1,2}}(?:st|nd|rd|th|d)?),?\s+"
    rf"(?P<year>\d{{4}})$",
    re.IGNORECASE,
)
_DAY_MONTH_NAME_RE = re.compile(
    rf"^(?P<day>\d{{1,2}}(?:st|nd|rd|th|d)?)\s+"
    rf"(?P<month>{_MONTHS_RE})\s+"
    rf"(?P<year>\d{{4}})$",
    re.IGNORECASE,
)
_MONTH_NAME_COMMA_RE = re.compile(
    rf"^(?P<month>{_MONTHS_RE}),\s+"
    rf"(?P<day>\d{{1,2}}(?:st|nd|rd|th|d)?)\s+"
    rf"(?P<year>\d{{4}})$",
    re.IGNORECASE,
)
_MONTH_YEAR_RE = re.compile(
    rf"^(?P<month>{_MONTHS_RE})\s+(?P<year>\d{{4}})$",
    re.IGNORECASE,
)
_EMBEDDED_MONTH_PATTERNS = (
    re.compile(
        rf"\b(?P<month>{_MONTHS_RE})\s+"
        rf"(?P<day>\d{{1,2}}(?:st|nd|rd|th|d)?),?\s+"
        rf"(?P<year>\d{{4}})\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b(?P<day>\d{{1,2}}(?:st|nd|rd|th|d)?)\s+"
        rf"(?P<month>{_MONTHS_RE})\s+"
        rf"(?P<year>\d{{4}})\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b(?P<month>{_MONTHS_RE}),\s+"
        rf"(?P<day>\d{{1,2}}(?:st|nd|rd|th|d)?)\s+"
        rf"(?P<year>\d{{4}})\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b(?P<month>{_MONTHS_RE})\s+(?P<year>\d{{4}})\b",
        re.IGNORECASE,
    ),
)

_YEAR_RE = re.compile(r"\b(?P<year>\d{4})(?:s)?\b")
_YEAR_OR_MONTH_SUFFIX_RE = re.compile(r"(?P<year>\d{3,4})[cpqa!]\b", re.IGNORECASE)
_SIMPLE_YEAR_RE = re.compile(r"^(?P<year>\d{4})$")
_SIMPLE_RANGE_RE = re.compile(r"^(?P<first>\d{4})-(?P<second>\d{4})$")
_SIMPLE_SLASH_RANGE_RE = re.compile(r"^(?P<first>\d{4})/(?P<second>\d{4})$")
_DATE_YMD_RE = re.compile(r"^(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})$")
_DATE_DMY_DASH_RE = re.compile(r"^(?P<day>\d{1,2})-(?P<month>\d{1,2})-(?P<year>\d{4})$")
_DATE_DMY_SLASH_RE = re.compile(r"^(?P<day>\d{2})/(?P<month>\d{2})/(?P<year>\d{4})$")
_LEADING_MUSHED_DATE_RE = re.compile(
    r"^(?P<year>\d{4})(?P<month>\d{2})(?P<day>\d{2})(?=\s|\(|\[|,|;|:)"
)
_ALT_DIVIDED_RE = re.compile(r"^(?P<year>\d{4})(?P<month>\d{2})/(?P<day>\d{2})$")
_ALT_DASHED_RE = re.compile(r"^(?P<year>\d{4})(?P<month>-{2}|\d{2})--$")
_MUSHED_YEAR_RE = re.compile(r"^(?P<year>\d{4})\d{4}$")
_MUSHED_RANGE_RE = re.compile(r"^(?P<first>\d{4})\d{4}-(?P<second>\d{4})\d{4}$")
_MULTI_YEAR_RE = re.compile(
    r"^(?P<first>\d{4})-\d{2}-\d{2}-(?P<second>\d{4})-\d{2}-\d{2}$"
)
_ZERO_DAY_RE = re.compile(r"^(?P<year>\d{4})-\d{2}-(00|xx)$", re.IGNORECASE)
_CENTURY_DASHES_RE = re.compile(r"^(?P<century>\d{2})(?:--|\?\?)$")
_CENTURY_TRUNCATED_RE = re.compile(r"^(?P<first>\d{2})/(?P<second>\d{2})$")
_CENTURY_SHORT_RE = re.compile(
    r"^(?P<century>\d{2})(?:th|st|rd|nd)?\s*(?:[Cc]\.?|sc\.?)?$"
)
_CENTURY_EN_RE = re.compile(
    r"^(?P<century>\d{1,2})(?:th|st|rd|nd) "
    r"century(?:, (?P<adj1>\w+)(?: (?P<adj2>\w+))?)?$",
    re.IGNORECASE,
)
_CENTURY_CODE_RE = re.compile(
    r"^(?P<century>\d{2})\.(?P<adj1>[\diesm])(?P<adj2>[dqhtnxce])?$"
)
_PREFIX_SPACE_RE = re.compile(
    r"(ca\.?|c\.|circa|um|approx\.?|approximately|around|about)(\d)",
    re.IGNORECASE,
)
_STRIP_WRAPPERS_RE = re.compile(r'^[\s"\[\]]+|[\s"\[\]]+$')
_SC_SUFFIX_RE = re.compile(r"\.sc$", re.IGNORECASE)
_ROMAN_NUMERAL_RE = re.compile(r"^[XVILCDM]+(?:-[XVILCDM]+)?$", re.IGNORECASE)

_BETWEEN_KEYWORDS = ("between", "entre", " bis ", " et ", "von", "vor")
_OPEN_START_PREFIXES = ("not after ", "avant ", "before ", "earlier ", "vor ")
_OPEN_END_PREFIXES = (
    "not before ",
    "since ",
    "after ",
    "past ",
    "later ",
    "apres ",
    "après ",
    "nach ",
)
_APPROX_PREFIXES = (
    "ca. ",
    "ca ",
    "c. ",
    "circa ",
    "um ",
    "approx. ",
    "approx ",
    "approximately ",
    "around ",
    "about ",
)
_QUALIFIER_PREFIXES = (
    "copied in ",
    "copied on ",
    "copied about ",
    "copied ",
    "copied",
    "copiedin ",
    "copiedon ",
    "copy ",
    "copia ",
    "copia",
    "see ",
    "from ",
    "dated ",
)


@dataclass(slots=True)
class NormalizedDateText:
    raw: str
    text: str

    @property
    def lowered(self) -> str:
        return self.text.lower()

    @property
    def years(self) -> list[str]:
        return [match.group("year") for match in _YEAR_RE.finditer(self.text)]

    @property
    def has_month_name(self) -> bool:
        return any(month in self.lowered for month in _MONTHS)


def _strip_day_suffix(day_str: str) -> int:
    return int(re.sub(r"(?:st|nd|rd|th|d)$", "", day_str, flags=re.IGNORECASE))


def _finalize_candidate(candidate: str | None) -> str | None:
    if candidate is None:
        return None
    return candidate if is_valid(candidate) else None


def _normalize_input(statement: str) -> NormalizedDateText | None:
    if statement in NO_DATE_VALUES:
        return None

    text = statement.strip()
    if text.startswith("-"):
        text = text[1:]

    text = _STRIP_WRAPPERS_RE.sub("", text)

    lowered = text.lower()
    for prefix in _QUALIFIER_PREFIXES:
        if lowered.startswith(prefix):
            text = text[len(prefix):].lstrip(",;: ")
            lowered = text.lower()
            break

    text = text.replace("\u2012", "-").replace("\u2013", "-")
    text = re.sub(r"\s*-\s*", "-", text)
    text = re.sub(r"\s*/\s*", "/", text)
    text = _PREFIX_SPACE_RE.sub(r"\1 \2", text)

    if _CENTURY_DASHES_RE.match(text):
        return NormalizedDateText(raw=statement, text=text)

    text = text.replace("(?)", "?")
    text = text.replace("?", "")

    if re.match(r"^(\d{1,2}\.)?(\d{1,2})\.(\d{4})(-(\d{1,2}\.)?(\d{1,2})\.(\d{4}))?$", text):
        text = text.replace(".", "-")

    text = re.sub(r"[()]", "", text)
    text = re.sub(r"\s+", " ", text).strip(" ,;:")
    lowered = text.lower()
    text = lowered.replace("not after", "before").replace("not before", "after")

    return NormalizedDateText(raw=statement, text=text.strip())


def _parse_month_match(match: re.Match[str]) -> str:
    month = _MONTH_TO_NUMBER[match.group("month").lower()]
    year = match.group("year")
    day = match.groupdict().get("day")
    if day is None:
        return f"{year}-{month:02d}"
    return f"{year}-{month:02d}-{_strip_day_suffix(day):02d}"


def _detect_direct_numeric_forms(value: NormalizedDateText) -> str | None:
    s = value.text

    if _DATE_YMD_RE.match(s):
        return s

    if m := _SIMPLE_YEAR_RE.match(s):
        return m.group("year")

    if m := _SIMPLE_RANGE_RE.match(s):
        return f"{m.group('first')}/{m.group('second')}"

    if m := _SIMPLE_SLASH_RANGE_RE.match(s):
        return f"{m.group('first')}/{m.group('second')}"

    if m := _DATE_DMY_DASH_RE.match(s):
        return (
            f"{m.group('year')}-"
            f"{int(m.group('month')):02d}-"
            f"{int(m.group('day')):02d}"
        )

    if m := _DATE_DMY_SLASH_RE.match(s):
        return (
            f"{m.group('year')}-"
            f"{int(m.group('month')):02d}-"
            f"{int(m.group('day')):02d}"
        )

    if m := _LEADING_MUSHED_DATE_RE.match(s):
        return f"{m.group('year')}-{m.group('month')}-{m.group('day')}"

    if m := _ALT_DIVIDED_RE.match(s):
        return f"{m.group('year')}-{m.group('month')}"

    if m := _ALT_DASHED_RE.match(s):
        month = m.group("month")
        return m.group("year") if month == "--" else f"{m.group('year')}-{month}"

    return None


def _detect_month_name_forms(value: NormalizedDateText) -> str | None:
    for pattern in (_MONTH_NAME_RE, _DAY_MONTH_NAME_RE, _MONTH_NAME_COMMA_RE, _MONTH_YEAR_RE):
        if match := pattern.match(value.text):
            return _parse_month_match(match)
    return None


def _detect_approximate_or_open_ranges(value: NormalizedDateText) -> str | None:
    s = value.text
    lowered = value.lowered

    for prefix in _APPROX_PREFIXES:
        if lowered.startswith(prefix):
            remainder = s[len(prefix):].strip()
            if m := _SIMPLE_RANGE_RE.match(remainder):
                return f"{m.group('first')}~/{m.group('second')}~"
            if m := _SIMPLE_YEAR_RE.match(remainder):
                return f"{m.group('year')}~"
            return None

    for prefix in _OPEN_START_PREFIXES:
        if lowered.startswith(prefix):
            year = s[len(prefix):].strip()
            if _SIMPLE_YEAR_RE.match(year):
                return f"/{year}"

    for prefix in _OPEN_END_PREFIXES:
        if lowered.startswith(prefix):
            year = s[len(prefix):].strip()
            if _SIMPLE_YEAR_RE.match(year):
                return f"{year}/"

    return None


def _parse_numeric_ordinal(ordinal: str) -> int | None:
    ordinal_map = {
        "1st": 1,
        "2nd": 2,
        "3rd": 3,
        "4th": 4,
    }
    mapped = ordinal_map.get(ordinal)
    if mapped is not None:
        return mapped
    clean = ordinal.rstrip("stndrh")
    if clean.isdigit():
        return int(clean)
    return None


def _parse_century_fraction(
    century_start: int,
    ordinal: str,
    period: str,
) -> tuple[int, int] | None:
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

    multiplier: int | None
    if ordinal.isdigit():
        multiplier = int(ordinal)
    else:
        multiplier = _parse_numeric_ordinal(ordinal)
        if multiplier is None:
            multiplier = {
                "first": 1,
                "i": 1,
                "second": 2,
                "third": 3,
                "fourth": 4,
                "last": divider,
                "e": divider,
                "s": divider,
                "m": divider,
            }.get(ordinal.lower())

    if multiplier is None or multiplier < 1 or multiplier > divider:
        return None

    period_years = math.floor(100 / divider)
    return (
        century_start + (multiplier - 1) * period_years,
        century_start + multiplier * period_years,
    )


def _parse_century_adjective(century_start: int, adjective: str) -> tuple[int, int] | None:
    if adjective in ("beginning", "start", "early"):
        return century_start, century_start + _EARLY_CENTURY_END
    if adjective in ("late", "end"):
        return century_start + _LATE_CENTURY_START, century_start + 100
    if adjective == "middle":
        return century_start + 25, century_start + 75
    return None


def _century_to_edtf(century: int) -> str:
    start = (century - 1) * 100 + 1
    end = century * 100
    return f"{start:04d}/{end:04d}"


def _detect_century_forms(value: NormalizedDateText) -> str | None:
    s = value.text

    if m := _CENTURY_DASHES_RE.match(s):
        century = int(m.group("century"))
        start = (century - 1) * 100 + 1
        return f"{start:04d}/{start + 99:04d}"

    if m := _CENTURY_TRUNCATED_RE.match(s):
        first = (int(m.group("first")) - 1) * 100 + 1
        second = int(m.group("second")) * 100
        return f"{first:04d}/{second:04d}"

    if m := _CENTURY_SHORT_RE.match(s):
        return _century_to_edtf(int(m.group("century")))

    if m := _CENTURY_EN_RE.match(s):
        century_num = int(m.group("century"))
        adj1 = m.group("adj1")
        adj2 = m.group("adj2")
        if adj1 is None:
            return _century_to_edtf(century_num)

        century_start = (century_num - 1) * 100
        result = (
            _parse_century_fraction(century_start, adj1.lower(), adj2)
            if adj2
            else _parse_century_adjective(century_start, adj1.lower())
        )
        if result:
            return f"{result[0]:04d}/{result[1]:04d}"
        return None

    if m := _CENTURY_CODE_RE.match(s):
        century_num = int(m.group("century"))
        century_start = (century_num - 1) * 100
        adj1 = m.group("adj1").lower()
        adj2 = m.group("adj2")
        result = (
            _parse_century_fraction(century_start, adj1, adj2)
            if adj2
            else _parse_century_adjective(century_start, adj1)
        )
        if result:
            return f"{result[0] + 1:04d}/{result[1]:04d}"
        return _century_to_edtf(century_num)

    if _SC_SUFFIX_RE.search(s):
        stripped = _SC_SUFFIX_RE.sub("", s).strip()
        return _detect_century_forms(NormalizedDateText(raw=value.raw, text=stripped))

    return None


def _detect_compact_mushed_forms(value: NormalizedDateText) -> str | None:
    s = value.text

    if m := _YEAR_OR_MONTH_SUFFIX_RE.fullmatch(s):
        return m.group("year")

    if m := _ZERO_DAY_RE.match(s):
        return m.group("year")

    if m := _MUSHED_RANGE_RE.match(s):
        return f"{m.group('first')}/{m.group('second')}"

    if m := _MULTI_YEAR_RE.match(s):
        return f"{m.group('first')}/{m.group('second')}"

    if m := _MUSHED_YEAR_RE.match(s):
        return m.group("year")

    if re.match(r"^\d{4}s$", s):
        year_start = int(s[:4])
        return f"{year_start}/{year_start + 99}"

    if match := re.match(r"^(?P<range>\d{4}-\d{4})\s+.+$", s):
        return f"{match.group('range')[:4]}/{match.group('range')[-4:]}"

    if match := re.match(r"^(?P<year>\d{4})\s+.+$", s):
        return match.group("year")

    return None


def _detect_birth_death_markers(value: NormalizedDateText) -> str | None:
    stripped = value.text.rstrip("*+")
    if stripped != value.text and len(stripped) == 4 and stripped.isdigit():
        if value.text.endswith("*"):
            return f"{stripped}/"
        if value.text.endswith("+"):
            return f"/{stripped}"
    return None


def _detect_embedded_year_or_range(value: NormalizedDateText) -> str | None:
    lowered = value.lowered
    years = value.years

    for pattern in _EMBEDDED_MONTH_PATTERNS:
        if match := pattern.search(value.text):
            return _parse_month_match(match)

    if len(years) >= 2 and any(keyword in f" {lowered} " for keyword in _BETWEEN_KEYWORDS):
        return f"{years[0]}/{years[1]}"

    if len(years) == 1 and value.has_month_name:
        return years[0]

    if len(years) == 1:
        return years[0]

    if len(years) >= 2:
        return f"{years[0]}/{years[1]}"

    return None


def _fallback_fuzzy_single_date(value: NormalizedDateText) -> str | None:
    if dateutil_parser is None:
        return None
    if len(value.years) != 1 or not value.has_month_name:
        return None
    if any(marker in value.lowered for marker in ("century", ".sc", "/", "17--", "17??")):
        return None

    try:
        parsed = dateutil_parser.parse(
            value.text,
            fuzzy=True,
            dayfirst=True,
            default=datetime(1900, 1, 1),
        )
    except (OverflowError, TypeError, ValueError):  # pragma: no cover - optional path
        return None

    year = value.years[0]
    if parsed.year != int(year):
        return None

    if re.search(r"\b\d{1,2}(?:st|nd|rd|th|d)?\b", value.text, re.IGNORECASE):
        return f"{parsed.year:04d}-{parsed.month:02d}-{parsed.day:02d}"

    return f"{parsed.year:04d}-{parsed.month:02d}"


# -------------------------------------------------------------------------- #
# Public API
# -------------------------------------------------------------------------- #


def is_no_date(statement: str) -> bool:
    """Return whether *statement* is a known "no date" marker."""
    return statement in NO_DATE_VALUES


def coerce(statement: str) -> str | None:
    """Coerce a free-form date string into a valid EDTF string."""
    if is_no_date(statement):
        return None

    value = _normalize_input(statement)
    if value is None or not value.text:
        return None

    if value.lowered.startswith("año ") or _ROMAN_NUMERAL_RE.match(value.text):
        return None

    detectors = (
        _detect_direct_numeric_forms,
        _detect_month_name_forms,
        _detect_approximate_or_open_ranges,
        _detect_birth_death_markers,
        _detect_century_forms,
        _detect_compact_mushed_forms,
        _detect_embedded_year_or_range,
        _fallback_fuzzy_single_date,
    )

    for detector in detectors:
        if candidate := detector(value):
            if result := _finalize_candidate(candidate):
                return result

    return None
