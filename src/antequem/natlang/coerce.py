"""Coerce a wide range of natural language and messy date formats into EDTF.

Based on patterns from the MuscatPlus indexer ``antequem.py``.

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
    "1811a"        -> "/1811"
    "1811p"        -> "1811/"
    "before 1900"  -> "/1900"
    "after 1800"   -> "1800/"
    "12/1850"      -> "1850-12"
    "1.1.1850"     -> "1850-01-01"

The design philosophy is: be generous going in, and return ``None`` when we
can't make sense of the string. Callers can then feed the resulting EDTF
string to :func:`antequem.parse` for full validation and AST construction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
import re

from antequem.parser import is_valid

try:
    from dateutil import parser as dateutil_parser
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    dateutil_parser = None


# -------------------------------------------------------------------------- #
# Constants
# -------------------------------------------------------------------------- #

_EARLY_CENTURY_END: int = 10
_LATE_CENTURY_START: int = 90
_MONTH_LENGTHS = [0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

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

_YEAR_RE = re.compile(r"\b(?P<year>\d{4})s?\b")
_SINGLE_ERA_YEAR_RE = re.compile(
    r"^(?P<year>\d{1,4})\s*(?P<era>bce|bc|ce|ad)$",
    re.IGNORECASE,
)
_ERA_YEAR_RANGE_RE = re.compile(
    r"^(?P<first>\d{1,4})\s*(?P<first_era>bce|bc|ce|ad)\s*-\s*"
    r"(?P<second>\d{1,4})(?:\s*(?P<second_era>bce|bc|ce|ad))?$",
    re.IGNORECASE,
)
_YEAR_OR_MONTH_SUFFIX_RE = re.compile(
    r"^(?P<year>\d{3,4})(?P<mark>[cpqa!])\.?$",
    re.IGNORECASE,
)
_MASKED_YEAR_WITH_SUFFIX_RE = re.compile(r"^(?P<year>\d{3})\?(?=-)")
_YEAR_LIFE_MARKER_RE = re.compile(
    r"^(?P<year>\d{4})(?P<mark>[ac])?(?P<life>[*+])$",
    re.IGNORECASE,
)
_APPROXIMATE_YEAR_RANGE_RE = re.compile(
    r"^(?P<first>\d{3,4})(?P<first_mark>[ac]?)[-/](?P<second>\d{3,4})(?P<second_mark>[ac]?)$",
    re.IGNORECASE,
)
_APPROXIMATE_ERA_YEAR_RANGE_RE = re.compile(
    r"^(?P<first>\d{3,4})(?P<first_mark>[ac]?)[-/](?P<second>\d{3,4})(?P<second_mark>[ac]?)\s*"
    r"(?P<era>bce|bc|ce|ad)$",
    re.IGNORECASE,
)
_UNSPECIFIED_DECADE_SHORTHAND_RE = re.compile(r"^(?P<prefix>\d{3})-$")
_DATE_DMY_WITH_YEAR_SUFFIX_RE = re.compile(
    r"^(?P<day>\d{1,2})(?P<sep>[-/])(?P<month>\d{1,2})(?P=sep)(?P<year>\d{4})(?P<mark>[acpq!])\.?$",
    re.IGNORECASE,
)
_LEADING_MUSHED_DATE_RANGE_RE = re.compile(
    r"^(?P<first_year>\d{4})(?P<first_month>\d{2})(?P<first_day>\d{2})-"
    r"(?P<second_year>\d{4})(?P<second_month>\d{2})(?P<second_day>\d{2})"
    r"(?=[\s([,;:])"
)
_PREFIX_SPACE_RE = re.compile(
    r"(ca\.?|c\.?|circa|um|approx\.?|approximately|around|about)(\d)",
    re.IGNORECASE,
)
_ROMAN_NUMERAL_RE = re.compile(r"^[XVILCDM]+(?:-[XVILCDM]+)?$", re.IGNORECASE)
_DOTTED_DATE_RE = re.compile(
    r"^(\d{1,2}\.)?(\d{1,2})\.(\d{4}[acpq!]?)"
    r"(-(\d{1,2}\.)?(\d{1,2})\.(\d{4}[acpq!]?)?)?$",
    re.IGNORECASE,
)
_ORDINAL_DAY_RE = re.compile(r"\b\d{1,2}(?:st|nd|rd|th|d)\b", re.IGNORECASE)

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
    "c ",
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
    lowered: str
    has_month_name: bool
    digit_count: int
    starts_with_four_digits: bool
    _spaced_lowered: str | None = None
    _years: list[str] | None = None

    @property
    def spaced_lowered(self) -> str:
        value = self._spaced_lowered
        if value is None:
            value = f" {self.lowered} "
            self._spaced_lowered = value
        return value

    @property
    def years(self) -> list[str]:
        value = self._years
        if value is None:
            value = [match.group("year") for match in _YEAR_RE.finditer(self.text)]
            self._years = value
        return value


def _strip_day_suffix(day_str: str) -> int:
    end = 0
    while end < len(day_str) and day_str[end].isdigit():
        end += 1
    return int(day_str[:end])


def _is_simple_year(text: str) -> bool:
    return len(text) == 4 and text.isdigit()


def _parse_simple_range(text: str, separator: str = "-") -> tuple[str, str] | None:
    if len(text) != 9 or text[4] != separator:
        return None
    first = text[:4]
    second = text[5:]
    if first.isdigit() and second.isdigit():
        return first, second
    return None


def _is_leap_year(year: int) -> bool:
    return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)


def _days_in_month(year: int, month: int) -> int:
    if month == 2 and _is_leap_year(year):
        return 29
    return _MONTH_LENGTHS[month]


def _fast_validate_year(text: str) -> bool:
    return len(text) == 4 and text.isdigit()


def _fast_validate_unspecified_year(text: str) -> bool:
    if len(text) != 4:
        return False
    suffix_len = len(text) - len(text.rstrip("X"))
    if suffix_len not in {1, 2}:
        return False
    return text[: 4 - suffix_len].isdigit()


def _fast_validate_year_month(text: str) -> bool:
    if len(text) != 7 or text[4] != "-" or not text[:4].isdigit() or not text[5:7].isdigit():
        return False
    month = int(text[5:7])
    return 1 <= month <= 12


def _fast_validate_year_month_day(text: str) -> bool:
    if (
        len(text) != 10
        or text[4] != "-"
        or text[7] != "-"
        or not text[:4].isdigit()
        or not text[5:7].isdigit()
        or not text[8:10].isdigit()
    ):
        return False
    year = int(text[:4])
    month = int(text[5:7])
    if not 1 <= month <= 12:
        return False
    day = int(text[8:10])
    return 1 <= day <= _days_in_month(year, month)


def _fast_validate_point_candidate(text: str) -> bool:
    bare = text.removesuffix("~")
    return (
        _fast_validate_year(bare)
        or _fast_validate_unspecified_year(bare)
        or _fast_validate_year_month(bare)
        or _fast_validate_year_month_day(bare)
    )


def _fast_validate_interval_candidate(text: str) -> bool | None:
    if "/" not in text:
        return None
    lower, upper = text.split("/", 1)
    if "/" in upper:
        return None
    if not lower:
        return _fast_validate_point_candidate(upper)
    if not upper:
        return _fast_validate_point_candidate(lower)
    return _fast_validate_point_candidate(lower) and _fast_validate_point_candidate(upper)


def _fast_validate_candidate(text: str) -> bool:
    interval_valid = _fast_validate_interval_candidate(text)
    if interval_valid is not None:
        return interval_valid
    return _fast_validate_point_candidate(text)


def _finalize_candidate(candidate: str | None) -> str | None:
    if candidate is None:
        return None
    if _fast_validate_candidate(candidate):
        return candidate
    return candidate if is_valid(candidate) else None


def _build_normalized_date_text(raw: str, text: str) -> NormalizedDateText:
    lowered = text.lower()
    return NormalizedDateText(
        raw=raw,
        text=text,
        lowered=lowered,
        has_month_name=any(month in lowered for month in _MONTHS),
        digit_count=sum(ch.isdigit() for ch in text),
        starts_with_four_digits=len(text) >= 4 and text[:4].isdigit(),
    )


def _trim_wrapper_chars(text: str) -> str:
    return text.strip(' \t\r\n"[]')


def _replace_unicode_dashes(text: str) -> str:
    if "\u2012" not in text and "\u2013" not in text:
        return text
    return text.replace("\u2012", "-").replace("\u2013", "-")


def _compact_separators(text: str) -> str:
    chars: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in "-/":
            while chars and chars[-1].isspace():
                chars.pop()
            chars.append(ch)
            i += 1
            while i < n and text[i].isspace():
                i += 1
            continue
        chars.append(ch)
        i += 1
    return "".join(chars)


def _strip_parentheses_and_collapse_whitespace(text: str) -> str:
    chars: list[str] = []
    previous_space = False
    for ch in text:
        if ch in "()[]":
            continue
        if ch.isspace():
            if not previous_space:
                chars.append(" ")
                previous_space = True
            continue
        chars.append(ch)
        previous_space = False
    return "".join(chars).strip(" ,;:")


def _normalize_input(statement: str) -> NormalizedDateText | None:
    if statement in NO_DATE_VALUES:
        return None

    text = statement.strip()
    if text.startswith("-"):
        candidate = text[1:].strip()
        if len(candidate) == 4 and candidate.isdigit():
            return _build_normalized_date_text(statement, f"before {candidate}")

    text = _trim_wrapper_chars(text)

    lowered = text.lower()
    for prefix in _QUALIFIER_PREFIXES:
        if lowered.startswith(prefix):
            text = text[len(prefix):].lstrip(",;: ")
            text.lower()
            break

    text = _replace_unicode_dashes(text)
    text = _compact_separators(text)
    text = _PREFIX_SPACE_RE.sub(r"\1 \2", text)
    text = _MASKED_YEAR_WITH_SUFFIX_RE.sub(r"\g<year>X", text)

    if len(text) == 4 and text[:2].isdigit() and text[2:] in {"--", "??"}:
        return _build_normalized_date_text(statement, text)

    if len(text) == 4 and text[:2].isdigit() and text[2:].lower() == "uu":
        return _build_normalized_date_text(statement, f"{text[:2]}XX")

    if len(text) == 4 and text[:3].isdigit() and text[3] == "?":
        return _build_normalized_date_text(statement, f"{text[:3]}X")

    text = text.replace("(?)", "?")
    text = text.replace("?", "")

    if _DOTTED_DATE_RE.match(text):
        text = text.replace(".", "-")

    text = _strip_parentheses_and_collapse_whitespace(text)
    lowered = text.lower()
    text = lowered.replace("not after", "before").replace("not before", "after")

    return _build_normalized_date_text(statement, text.strip())


def _parse_month_match(match: re.Match[str]) -> str:
    month = _MONTH_TO_NUMBER[match.group("month").lower()]
    year = match.group("year")
    day = match.groupdict().get("day")
    if day is None:
        return f"{year}-{month:02d}"
    return f"{year}-{month:02d}-{_strip_day_suffix(day):02d}"


def _to_astronomical_year(year_text: str, era_text: str) -> str:
    year = int(year_text)
    era = era_text.lower()
    if era in {"ce", "ad"}:
        return f"{year:04d}"
    astronomical = year - 1
    if astronomical == 0:
        return "0000"
    return f"-{astronomical:04d}"


def _apply_suffix_mark(candidate: str, mark: str) -> str | None:
    normalized_mark = mark.lower()
    if normalized_mark == "a":
        return f"/{candidate}"
    if normalized_mark == "p":
        return f"{candidate}/"
    if normalized_mark == "c":
        return f"{candidate}~"
    if normalized_mark in {"q", "!"}:
        return candidate
    return None


def _parse_boundary_value(text: str) -> str | None:
    if len(text) == 4 and text.isdigit():
        return text
    if (
        len(text) == 10
        and text[4] == "-"
        and text[7] == "-"
        and text[:4].isdigit()
        and text[5:7].isdigit()
        and text[8:10].isdigit()
    ):
        return text
    if len(text) == 8 and text.isdigit():
        if text[6:8] != "00":
            return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
        return f"{text[:4]}-{text[4:6]}"
    if len(text) > 8 and text[:8].isdigit():
        next_char = text[8]
        if next_char in " ([,;:":
            if text[6:8] != "00":
                return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
            return f"{text[:4]}-{text[4:6]}"
    return None


def _format_compact_endpoint(year: str, month: str, day: str) -> str:
    if day == "00":
        return f"{year}-{month}"
    return f"{year}-{month}-{day}"


def _detect_direct_numeric_forms(value: NormalizedDateText) -> str | None:
    s = value.text
    year_head = s[:4].upper() if len(s) >= 4 else s

    if match := _ERA_YEAR_RANGE_RE.fullmatch(s):
        second_era = match.group("second_era") or "ce"
        first = _to_astronomical_year(match.group("first"), match.group("first_era"))
        second = _to_astronomical_year(match.group("second"), second_era)
        return f"{first}/{second}"

    if match := _SINGLE_ERA_YEAR_RE.fullmatch(s):
        return _to_astronomical_year(match.group("year"), match.group("era"))

    if m := _UNSPECIFIED_DECADE_SHORTHAND_RE.match(s):
        return f"{m.group('prefix')}X"

    if (
        len(s) == 10
        and s[4] == "-"
        and s[7] == "-"
        and s[:4].isdigit()
        and s[5:7].isdigit()
        and s[8:10].isdigit()
    ):
        return s

    if len(s) == 4 and s.isdigit():
        return s

    if len(s) == 4 and year_head[:3].isdigit() and year_head[3] == "X":
        return year_head

    if len(s) == 4 and year_head[:2].isdigit() and year_head[2:] == "XX":
        return year_head

    if (
        len(s) == 7
        and s[4] == "-"
        and (
            year_head.isdigit()
            or (year_head[:3].isdigit() and year_head[3] == "X")
            or (year_head[:2].isdigit() and year_head[2:] == "XX")
        )
        and s[5:7].isdigit()
    ):
        return f"{year_head}{s[4:]}"

    if (
        len(s) == 10
        and s[4] == "-"
        and s[7] == "-"
        and (
            year_head.isdigit()
            or (year_head[:3].isdigit() and year_head[3] == "X")
            or (year_head[:2].isdigit() and year_head[2:] == "XX")
        )
        and s[5:7].isdigit()
        and s[8:10].isdigit()
    ):
        return f"{year_head}{s[4:]}"

    if len(s) == 9 and s[4] == "-" and s[:4].isdigit() and s[5:].isdigit():
        return f"{s[:4]}/{s[5:]}"

    if len(s) == 9 and s[4] == "/" and s[:4].isdigit() and s[5:].isdigit():
        return f"{s[:4]}/{s[5:]}"

    if s.count("-") == 2:
        day, month, year = s.split("-")
        if (
            1 <= len(day) <= 2
            and 1 <= len(month) <= 2
            and len(year) == 4
            and day.isdigit()
            and month.isdigit()
            and year.isdigit()
        ):
            return f"{year}-{int(month):02d}-{int(day):02d}"

    if m := _DATE_DMY_WITH_YEAR_SUFFIX_RE.match(s):
        date = (
            f"{m.group('year')}-"
            f"{int(m.group('month')):02d}-"
            f"{int(m.group('day')):02d}"
        )
        return _apply_suffix_mark(date, m.group("mark"))

    if (
        len(s) == 10
        and s[:2].isdigit()
        and s[2] == "/"
        and s[3:5].isdigit()
        and s[5] == "/"
        and s[6:10].isdigit()
    ):
        return (
            f"{s[6:10]}-"
            f"{int(s[3:5]):02d}-"
            f"{int(s[:2]):02d}"
        )

    if m := _LEADING_MUSHED_DATE_RANGE_RE.match(s):
        return (
            f"{_format_compact_endpoint(m.group('first_year'), m.group('first_month'), m.group('first_day'))}/"
            f"{_format_compact_endpoint(m.group('second_year'), m.group('second_month'), m.group('second_day'))}"
        )

    if len(s) > 8 and s[:8].isdigit():
        next_char = s[8]
        if next_char in " ([,;:":
            if s[6:8] != "00":
                return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
            return f"{s[:4]}-{s[4:6]}"

    if len(s) == 9 and s[:6].isdigit() and s[6] == "/" and s[7:9].isdigit():
        return f"{s[:4]}-{s[4:6]}"

    if (
        len(s) == 8
        and s[:4].isdigit()
        and ((s[4:6].isdigit() and s[6:8] == "--") or s[4:6] == "--" and s[6:8] == "--")
    ):
        month = s[4:6]
        return s[:4] if month == "--" else f"{s[:4]}-{month}"

    return None


def _detect_month_name_forms(value: NormalizedDateText) -> str | None:
    if not value.has_month_name:
        return None
    for pattern in (_MONTH_NAME_RE, _DAY_MONTH_NAME_RE, _MONTH_NAME_COMMA_RE, _MONTH_YEAR_RE):
        if match := pattern.match(value.text):
            return _parse_month_match(match)
    return None


def _detect_approximate_or_open_ranges(value: NormalizedDateText) -> str | None:
    s = value.text
    lowered = value.lowered

    if m := _APPROXIMATE_ERA_YEAR_RANGE_RE.match(s):
        era = m.group("era")
        first = _to_astronomical_year(m.group("first"), era)
        second = _to_astronomical_year(m.group("second"), era)
        first_mark = "~" if m.group("first_mark") else ""
        second_mark = "~" if m.group("second_mark") else ""
        return f"{first}{first_mark}/{second}{second_mark}"

    if m := _APPROXIMATE_YEAR_RANGE_RE.match(s):
        first = m.group("first")
        second = m.group("second")
        first_mark = "~" if m.group("first_mark") else ""
        second_mark = "~" if m.group("second_mark") else ""
        return f"{first}{first_mark}/{second}{second_mark}"

    for prefix in _APPROX_PREFIXES:
        if lowered.startswith(prefix):
            remainder = s[len(prefix):].strip()
            if parsed_range := _parse_simple_range(remainder):
                first, second = parsed_range
                return f"{first}~/{second}~"
            if _is_simple_year(remainder):
                return f"{remainder}~"
            return None

    for prefix in _OPEN_START_PREFIXES:
        if lowered.startswith(prefix):
            boundary = _parse_boundary_value(s[len(prefix):].strip())
            if boundary:
                return f"/{boundary}"

    for prefix in _OPEN_END_PREFIXES:
        if lowered.startswith(prefix):
            boundary = _parse_boundary_value(s[len(prefix):].strip())
            if boundary:
                return f"{boundary}/"

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


def _parse_century_lead(text: str) -> tuple[int, str] | None:
    if not text or not text[0].isdigit():
        return None

    index = 0
    while index < len(text) and text[index].isdigit() and index < 2:
        index += 1

    if index == 0:
        return None

    century = int(text[:index])
    remainder = text[index:]
    lowered = remainder.lower()
    for suffix in ("th", "st", "rd", "nd"):
        if lowered.startswith(suffix):
            remainder = remainder[2:]
            break

    return century, remainder.strip()


def _detect_century_forms(value: NormalizedDateText) -> str | None:
    s = value.text
    lowered = value.lowered

    if lowered.endswith(".sc"):
        stripped = s[:-3].strip()
        if len(stripped) == 2 and stripped.isdigit():
            return _century_to_edtf(int(stripped))
        return _detect_century_forms(_build_normalized_date_text(value.raw, stripped))

    if len(s) == 4 and s[:2].isdigit() and s[2:] in {"--", "??"}:
        century = int(s[:2])
        start = (century - 1) * 100 + 1
        return f"{start:04d}/{start + 99:04d}"

    if not any(marker in lowered for marker in ("century", "c", "?", "/", ".", "--")):
        return None

    if (
        len(s) == 7
        and s[:2].isdigit()
        and s[2] == "."
        and s[3] == "/"
        and s[4:6].isdigit()
        and s[6] == "."
    ):
        first = int(s[:2])
        second = int(s[4:6])
        if second == first + 1:
            boundary = first * 100
            return f"{boundary - 10:04d}%/{boundary + 10:04d}%"

    if len(s) == 5 and s[:2].isdigit() and s[2] == "/" and s[3:5].isdigit():
        first = (int(s[:2]) - 1) * 100 + 1
        second = int(s[3:5]) * 100
        return f"{first:04d}/{second:04d}"

    if len(s) in {4, 5} and s[:2].isdigit() and s[2] == ".":
        century_num = int(s[:2])
        century_start = (century_num - 1) * 100
        adj1 = s[3].lower()
        adj2 = s[4].lower() if len(s) == 5 else None
        result = (
            _parse_century_fraction(century_start, adj1, adj2)
            if adj2
            else _parse_century_adjective(century_start, adj1)
        )
        if result:
            return f"{result[0] + 1:04d}/{result[1]:04d}"
        return _century_to_edtf(century_num)

    if parsed := _parse_century_lead(s):
        century_num, remainder = parsed
        remainder_lower = remainder.lower()
        if remainder_lower in {"", "c", "c.", "sc", "sc."}:
            return _century_to_edtf(century_num)

        if remainder_lower == "century":
            return _century_to_edtf(century_num)

        if remainder_lower.startswith("century,"):
            descriptor = remainder_lower[len("century,"):].strip()
            if not descriptor:
                return _century_to_edtf(century_num)

            century_start = (century_num - 1) * 100
            parts = descriptor.split(None, 1)
            if len(parts) == 2:
                result = _parse_century_fraction(century_start, parts[0], parts[1])
            else:
                result = _parse_century_adjective(century_start, parts[0])
            if result:
                return f"{result[0]:04d}/{result[1]:04d}"
            return None

    return None


def _detect_compact_mushed_forms(value: NormalizedDateText) -> str | None:
    s = value.text

    if len(s) == 4 and s[:3].isdigit() and s[3] == "?":
        return f"{s[:3]}X"

    if m := _YEAR_OR_MONTH_SUFFIX_RE.fullmatch(s):
        return _apply_suffix_mark(m.group("year"), m.group("mark"))

    if len(s) == 9 and s[:8].isdigit() and s[8].isalpha():
        candidate = _parse_boundary_value(s[:8])
        if candidate:
            return _apply_suffix_mark(candidate, s[8])

    if (
        len(s) == 10
        and s[:4].isdigit()
        and s[4] == "-"
        and s[5:7].isdigit()
        and s[7] == "-"
        and s[8:].lower() in {"00", "xx"}
    ):
        return s[:4]

    if (
        len(s) == 17
        and s[:4].isdigit()
        and s[4:6].isdigit()
        and s[6:8] == "00"
        and s[8] == "-"
        and s[9:13].isdigit()
        and s[13:15].isdigit()
        and s[15:17] == "00"
    ):
        return f"{s[:4]}-{s[4:6]}/{s[9:13]}-{s[13:15]}"

    if len(s) == 17 and s[:8].isdigit() and s[8] == "-" and s[9:].isdigit():
        return f"{s[:4]}/{s[9:13]}"

    if (
        len(s) == 21
        and s[:4].isdigit()
        and s[4] == "-"
        and s[5:7].isdigit()
        and s[7] == "-"
        and s[8:10].isdigit()
        and s[10] == "-"
        and s[11:15].isdigit()
        and s[15] == "-"
        and s[16:18].isdigit()
        and s[18] == "-"
        and s[19:21].isdigit()
    ):
        return f"{s[:4]}/{s[11:15]}"

    if len(s) == 8 and s.isdigit():
        return s[:4]

    if len(s) == 5 and s[:4].isdigit() and s[4] == "s":
        year_start = int(s[:4])
        return f"{year_start}/{year_start + 99}"

    if len(s) > 9 and s[:4].isdigit() and s[4] == "-" and s[5:9].isdigit() and s[9] == " ":
        return f"{s[:4]}/{s[5:9]}"

    if len(s) > 5 and s[:4].isdigit() and s[4] == " ":
        return s[:4]

    return None


def _detect_birth_death_markers(value: NormalizedDateText) -> str | None:
    if match := _YEAR_LIFE_MARKER_RE.fullmatch(value.text):
        year = match.group("year")
        suffix = "~" if match.group("mark") else ""
        if match.group("life") == "*":
            return f"{year}{suffix}/"
        return f"/{year}{suffix}"

    stripped = value.text.rstrip("*+")
    if stripped != value.text and len(stripped) == 4 and stripped.isdigit():
        if value.text.endswith("*"):
            return f"{stripped}/"
        if value.text.endswith("+"):
            return f"/{stripped}"
    return None


def _detect_embedded_year_or_range(value: NormalizedDateText) -> str | None:
    years = value.years
    if not years:
        return None

    if value.has_month_name:
        for pattern in _EMBEDDED_MONTH_PATTERNS:
            if match := pattern.search(value.text):
                return _parse_month_match(match)

    if len(years) >= 2 and any(keyword in value.spaced_lowered for keyword in _BETWEEN_KEYWORDS):
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

    if _ORDINAL_DAY_RE.search(value.text):
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

    if value.digit_count == 0 and not value.has_month_name:
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
