"""Recursive-descent EDTF parser.

Supports Level 0 and Level 1 features, with parity to elm-edtf.
"""

from datelib.result import Err, Ok, ParseError, Result
from datelib.types import (
    EDTF,
    Month,
    YM,
    YMD,
    ConcreteValue,
    DateAnnotated,
    Endpoint,
    Interval,
    L1Season,
    LongYear,
    SeasonValue,
    UnspecifiedValue,
    Y,
)

# --------------------------------------------------------------------------- #
# Low-level primitives
# --------------------------------------------------------------------------- #


def _take(s: str, pos: int, n: int) -> Result[str, ParseError]:
    """Take exactly *n* characters from *s* at *pos*."""
    if pos + n > len(s):
        return Err(
            ParseError(
                f"Expected {n} characters but reached end of string", pos, s
            )
        )
    return Ok(s[pos : pos + n])


def _consume(s: str, pos: int, expected: str) -> Result[int, ParseError]:
    """Consume *expected* at *pos*; return new position on success."""
    end = pos + len(expected)
    if end > len(s) or s[pos:end] != expected:
        return Err(
            ParseError(
                f"Expected {expected!r} at position {pos}", pos, s
            )
        )
    return Ok(end)


def _parse_int_n(
    s: str, pos: int, n: int, *, allow_x: bool = False
) -> Result[tuple[int | str, int], ParseError]:
    """Parse exactly *n* digits (or X if allowed) starting at *pos*.

    Returns the parsed string (to preserve X placeholders) and the new position.
    """
    text, new_pos = s[pos : pos + n], pos + n
    if new_pos > len(s):
        return Err(ParseError(f"Expected {n} characters", pos, s))
    if allow_x:
        valid = text.replace("X", "").isdigit() and text.count("X") <= n
        if not valid:
            return Err(
                ParseError(
                    f"Expected {n} digit/X characters, got {text!r}",
                    pos,
                    s,
                )
            )
    else:
        if not text.isdigit():
            return Err(
                ParseError(
                    f"Expected {n} digits, got {text!r}", pos, s
                )
            )
    return Ok((text, new_pos))


def _parse_int_digits(s: str, pos: int) -> Result[tuple[int, int], ParseError]:
    """Parse a run of digits starting at *pos*."""
    start = pos
    while pos < len(s) and s[pos].isdigit():
        pos += 1
    if pos == start:
        return Err(ParseError("Expected one or more digits", start, s))
    return Ok((int(s[start:pos]), pos))


# --------------------------------------------------------------------------- #
# Year parsers
# --------------------------------------------------------------------------- #


def _parse_year(s: str, pos: int) -> Result[tuple[Y | LongYear, int], ParseError]:
    """Parse a standard year, negative year, or long year."""
    # Try long year first: Y ±NNNNN+
    if pos < len(s) and s[pos] == "Y":
        return _parse_long_year(s, pos)

    # Try negative year first
    if pos < len(s) and s[pos] == "-":
        return _parse_negative_year(s, pos)

    # Standard positive year: 4 digits
    result = _parse_int_n(s, pos, 4, allow_x=False)
    if result.is_err:
        return result.map_err(lambda e: e)
    text, new_pos = result.unwrap()
    return Ok((Y(int(text)), new_pos))


def _parse_negative_year(
    s: str, pos: int
) -> Result[tuple[Y | LongYear, int], ParseError]:
    """Parse a negative year: -NNNN (but not -0000)."""
    if s[pos] != "-":
        return Err(ParseError("Expected '-'", pos, s))
    new_pos = pos + 1
    if new_pos + 4 > len(s):
        return Err(ParseError("Expected 4 digits after '-", pos, s))
    digits = s[new_pos : new_pos + 4]
    if not digits.isdigit():
        return Err(
            ParseError(
                f"Expected digits after '-', got {digits!r}", pos, s
            )
        )
    if digits == "0000":
        return Err(
            ParseError(
                "Year -0000 is not permitted", pos, s
            )
        )
    return Ok((Y(-int(digits)), new_pos + 4))


def _parse_long_year(s: str, pos: int) -> Result[tuple[LongYear, int], ParseError]:
    """Parse a long year: Y ±NNNNN+ (≥5 digits total after optional sign)."""
    if s[pos] != "Y":
        return Err(ParseError("Expected 'Y'", pos, s))
    new_pos = pos + 1
    if new_pos >= len(s):
        return Err(ParseError("Expected digits after 'Y'", pos, s))

    negative = False
    if s[new_pos] == "-":
        negative = True
        new_pos += 1

    result = _parse_int_digits(s, new_pos)
    if result.is_err:
        return result.map_err(lambda e: e)
    digits, new_pos = result.unwrap()
    if digits < 10_000:
        return Err(
            ParseError(
                f"Long year must be ≥5 digits, got {digits}",
                pos,
                s,
            )
        )
    return Ok((LongYear(-digits if negative else digits), new_pos))


# --------------------------------------------------------------------------- #
# Unspecified (masked) year parser
# --------------------------------------------------------------------------- #


def _parse_unspecified_year(
    s: str, pos: int
) -> Result[tuple[UnspecifiedValue, int], ParseError]:
    """Parse an unspecified year: 4 chars with 1–2 rightmost Xs."""
    if pos + 4 > len(s):
        return Err(ParseError("Expected 4 chars for year", pos, s))
    text = s[pos : pos + 4]

    # Count trailing Xs
    x_count = 0
    for i in range(3, -1, -1):
        if text[i] == "X":
            x_count += 1
        else:
            break

    if x_count == 0 or x_count > 2:
        return Err(
            ParseError(
                "Expected 1 or 2 trailing Xs for unspecified year",
                pos,
                s,
            )
        )

    prefix = text[: 4 - x_count]
    if not prefix.isdigit():
        return Err(
            ParseError(
                f"Expected digits before X, got {text!r}",
                pos,
                s,
            )
        )

    return Ok((UnspecifiedValue(year=text), pos + 4))


# --------------------------------------------------------------------------- #
# Month / season / day parsers
# --------------------------------------------------------------------------- #


def _parse_month(s: str, pos: int) -> Result[tuple[int | str, int], ParseError]:
    """Parse a month: 01–12 or XX."""
    if pos + 2 > len(s):
        return Err(ParseError("Expected month (2 chars)", pos, s))
    text = s[pos : pos + 2]
    if text == "XX":
        return Ok((text, pos + 2))
    if not text.isdigit():
        return Err(ParseError(f"Expected month digits or XX, got {text!r}", pos, s))
    month = int(text)
    if month < 1 or month > 12:
        return Err(
            ParseError(f"Month must be 01–12, got {month}", pos, s)
        )
    return Ok((month, pos + 2))


def _parse_season(s: str, pos: int) -> Result[tuple[L1Season, int], ParseError]:
    """Parse a season code: 21–24."""
    if pos + 2 > len(s):
        return Err(ParseError("Expected season code (2 chars)", pos, s))
    text = s[pos : pos + 2]
    if not text.isdigit():
        return Err(
            ParseError(f"Expected season code, got {text!r}", pos, s)
        )
    code = int(text)
    match code:
        case 21:
            return Ok((L1Season.Spring, pos + 2))
        case 22:
            return Ok((L1Season.Summer, pos + 2))
        case 23:
            return Ok((L1Season.Autumn, pos + 2))
        case 24:
            return Ok((L1Season.Winter, pos + 2))
        case _:
            return Err(ParseError(f"Unknown season code {code}", pos, s))


def _parse_day(s: str, pos: int) -> Result[tuple[int | str, int], ParseError]:
    """Parse a day: 01–31 or XX."""
    if pos + 2 > len(s):
        return Err(ParseError("Expected day (2 chars)", pos, s))
    text = s[pos : pos + 2]
    if text == "XX":
        return Ok((text, pos + 2))
    if not text.isdigit():
        return Err(ParseError(f"Expected day digits or XX, got {text!r}", pos, s))
    day = int(text)
    if day < 1 or day > 31:
        return Err(ParseError(f"Day must be 01–31, got {day}", pos, s))
    return Ok((day, pos + 2))


# --------------------------------------------------------------------------- #
# Date value parser (concrete value without qualifiers)
# --------------------------------------------------------------------------- #


def _parse_date_value(
    s: str, pos: int
) -> Result[tuple[ConcreteValue, int], ParseError]:
    """Parse a concrete date value (YMD, YM, Y, season, or unspecified)."""
    year_value: DateValue | UnspecifiedValue
    year_pos: int

    unspecified_result = _parse_unspecified_year(s, pos)
    if unspecified_result.is_ok:
        year_value, year_pos = unspecified_result.unwrap()
    else:
        year_result = _parse_year(s, pos)
        if year_result.is_err:
            return year_result.map_err(lambda e: e)
        year_value, year_pos = year_result.unwrap()

    # If nothing follows, return the year value
    if year_pos >= len(s) or s[year_pos] != "-":
        return Ok((year_value, year_pos))

    dash_pos = year_pos + 1  # after '-'

    # Try season first (21-24 immediately after '-')
    season_result = _parse_season(s, dash_pos)
    if season_result.is_ok:
        season, season_pos = season_result.unwrap()
        # Season consumes the rest; no day after season
        if isinstance(year_value, Y):
            return Ok(
                (
                    SeasonValue(year=year_value.year, season=season),
                    season_pos,
                )
            )
        return Err(
            ParseError("Long years cannot have seasons", dash_pos, s)
        )

    # Try month
    month_result = _parse_month(s, dash_pos)
    if month_result.is_err:
        # Not a month, so this must just be a year (with a stray hyphen?)
        # Return the year value up to the hyphen
        return Ok((year_value, year_pos))

    month, month_pos = month_result.unwrap()

    if isinstance(year_value, UnspecifiedValue):
        year_str = year_value.year
        if year_str is None:
            return Err(ParseError("Unspecified year missing year text", pos, s))

        # If month is XX and nothing follows, return YM with unspecified month
        if month == "XX" and (month_pos >= len(s) or s[month_pos] != "-"):
            return Ok((UnspecifiedValue(year=year_str, month="XX"), month_pos))

        if month_pos >= len(s) or s[month_pos] != "-":
            month_str = "XX" if month == "XX" else f"{month:02d}"
            return Ok((UnspecifiedValue(year=year_str, month=month_str), month_pos))

        day_pos = month_pos + 1
        day_result = _parse_day(s, day_pos)
        if day_result.is_err:
            return day_result.map_err(lambda e: e)
        day, day_pos = day_result.unwrap()

        month_str = "XX" if month == "XX" else f"{month:02d}"
        day_str = "XX" if day == "XX" else f"{day:02d}"
        return Ok(
            (
                UnspecifiedValue(
                    year=year_str,
                    month=month_str,
                    day=day_str,
                ),
                day_pos,
            )
        )

    # If no day follows, return YM
    if month_pos >= len(s) or s[month_pos] != "-":
        if isinstance(year_value, (Y, LongYear)):
            if isinstance(year_value, LongYear):
                return Err(
                    ParseError("Long year with month not supported", pos, s)
                )
            if month == "XX":
                return Ok(
                    (
                        UnspecifiedValue(
                            year=str(year_value.year), month="XX"
                        ),
                        month_pos,
                    )
                )
            return Ok(
                (YM(year=year_value.year, month=Month(month)), month_pos)
            )
        return Err(ParseError("Invalid year value for YM", pos, s))

    # Parse day
    day_pos = month_pos + 1
    day_result = _parse_day(s, day_pos)
    if day_result.is_err:
        return day_result.map_err(lambda e: e)
    day, day_pos = day_result.unwrap()

    if not isinstance(year_value, (Y, LongYear)):
        return Err(ParseError("Invalid year value for YMD", pos, s))

    if isinstance(year_value, LongYear):
        return Err(ParseError("Long year with day not supported", pos, s))

    # If day is XX, return unspecified day
    if day == "XX":
        month_str = "XX" if month == "XX" else f"{month:02d}"
        return Ok(
            (
                UnspecifiedValue(
                    year=str(year_value.year),
                    month=month_str,
                    day="XX",
                ),
                day_pos,
            )
        )

    return Ok(
        (YMD(year=year_value.year, month=Month(month), day=day), day_pos)
    )


# --------------------------------------------------------------------------- #
# Uncertainty / approximation qualifiers
# --------------------------------------------------------------------------- #


def _parse_qualifiers(
    s: str, pos: int
) -> Result[tuple[tuple[bool, bool], int], ParseError]:
    """Parse trailing uncertainty/approximation flags.

    Returns (uncertain, approximate), new_position.
    """
    uncertain = False
    approximate = False
    while pos < len(s) and s[pos] in "?~%":
        char = s[pos]
        if char == "?":
            uncertain = True
        elif char == "~":
            approximate = True
        elif char == "%":
            uncertain = True
            approximate = True
        pos += 1
    return Ok(((uncertain, approximate), pos))


# --------------------------------------------------------------------------- #
# Annotated date (concrete value + optional qualifiers)
# --------------------------------------------------------------------------- #


def _parse_date_annotated(
    s: str, pos: int
) -> Result[tuple[DateAnnotated, int], ParseError]:
    """Parse a concrete value with optional uncertainty/approximation."""
    val_result = _parse_date_value(s, pos)
    if val_result.is_err:
        return val_result.map_err(lambda e: e)
    value, val_pos = val_result.unwrap()

    # Parse trailing qualifiers
    qual_result = _parse_qualifiers(s, val_pos)
    if qual_result.is_err:
        return qual_result.map_err(lambda e: e)
    (uncertain, approximate), end_pos = qual_result.unwrap()

    return Ok(
        (DateAnnotated(value=value, uncertain=uncertain, approximate=approximate), end_pos)
    )


# --------------------------------------------------------------------------- #
# Interval parser
# --------------------------------------------------------------------------- #


def _parse_endpoint(
    s: str, pos: int, *, allow_empty: bool = False
) -> Result[tuple[Endpoint, int], ParseError]:
    """Parse an interval endpoint.

    Returns DateAnnotated, "open" (..), "unknown" (empty), or None.
    """
    if allow_empty and pos >= len(s):
        return Ok(("unknown", pos))

    if pos + 2 <= len(s) and s[pos : pos + 2] == "..":
        return Ok(("open", pos + 2))

    if pos < len(s) and s[pos] == "/":
        # Empty lower endpoint → unknown start
        return Ok(("unknown", pos))

    # Try parsing as a date
    result = _parse_date_annotated(s, pos)
    if result.is_ok:
        return result

    return Err(ParseError("Expected endpoint (date, .., or /)", pos, s))


def _parse_interval(
    s: str, pos: int
) -> Result[tuple[Interval, int], ParseError]:
    """Parse an interval: endpoint '/' endpoint."""
    # Try to parse lower endpoint
    lower_result = _parse_endpoint(s, pos, allow_empty=True)
    if lower_result.is_err:
        return lower_result.map_err(lambda e: e)
    lower, after_lower = lower_result.unwrap()

    # Must have '/'
    slash_result = _consume(s, after_lower, "/")
    if slash_result.is_err:
        return slash_result.map_err(lambda e: e)
    after_slash = slash_result.unwrap()

    # Parse upper endpoint
    upper_result = _parse_endpoint(s, after_slash, allow_empty=True)
    if upper_result.is_err:
        return upper_result.map_err(lambda e: e)
    upper, after_upper = upper_result.unwrap()

    return Ok((Interval(lower=lower, upper=upper), after_upper))


# --------------------------------------------------------------------------- #
# Top-level entry point
# --------------------------------------------------------------------------- #


def parse(s: str) -> Result[EDTF, ParseError]:
    """Parse an EDTF string and return the AST.

    Examples
    --------
    >>> result = parse("1984-06~")
    >>> result.is_ok
    True
    >>> result = parse("not a date")
    >>> result.is_err
    True
    """
    if not s:
        return Err(ParseError("Empty input string", 0, s))

    s = s.strip()

    # Try interval first (only if the string contains '/' to avoid polluting
    # errors for non-interval inputs)
    if "/" in s:
        interval_result = _parse_interval(s, 0)
        if interval_result.is_ok:
            value, end_pos = interval_result.unwrap()
            if end_pos == len(s):
                return Ok(value)
            return Err(
                ParseError(
                    f"Unexpected trailing characters at position {end_pos}",
                    end_pos,
                    s,
                )
            )
        return Err(interval_result.unwrap_err())

    # Try single date/season/unspecified
    date_result = _parse_date_annotated(s, 0)
    if date_result.is_ok:
        value, end_pos = date_result.unwrap()
        if end_pos == len(s):
            return Ok(value)
        return Err(
            ParseError(
                f"Unexpected trailing characters at position {end_pos}",
                end_pos,
                s,
            )
        )

    return Err(date_result.unwrap_err())


def is_valid(s: str) -> bool:
    """Return whether *s* is a valid EDTF string."""
    return parse(s).is_ok
