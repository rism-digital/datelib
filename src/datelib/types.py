"""AST types for EDTF parsed values.

These types mirror the design of elm-edtf, using dataclasses for clarity
and strong static typing.
"""

import enum
from dataclasses import dataclass
from typing import Literal


class Month(enum.IntEnum):
    """ISO-8601 month values."""

    January = 1
    February = 2
    March = 3
    April = 4
    May = 5
    June = 6
    July = 7
    August = 8
    September = 9
    October = 10
    November = 11
    December = 12


class L1Season(enum.IntEnum):
    """Level 1 season codes (independent of hemisphere)."""

    Spring = 21
    Summer = 22
    Autumn = 23
    Winter = 24


class L2Season(enum.IntEnum):
    """Level 2 season and sub-year grouping codes."""

    Spring = 21
    Summer = 22
    Autumn = 23
    Winter = 24
    Spring_NH = 25
    Summer_NH = 26
    Autumn_NH = 27
    Winter_NH = 28
    Spring_SH = 29
    Summer_SH = 30
    Autumn_SH = 31
    Winter_SH = 32
    Quarter_1 = 33
    Quarter_2 = 34
    Quarter_3 = 35
    Quarter_4 = 36
    Quadrimester_1 = 37
    Quadrimester_2 = 38
    Quadrimester_3 = 39
    Semestral_1 = 40
    Semestral_2 = 41


# --------------------------------------------------------------------------- #
# Concrete date values (no qualification or approximation)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class YMD:
    """A year-month-day date."""

    year: int
    month: Month
    day: int


@dataclass(frozen=True, slots=True)
class YM:
    """A year-month date (reduced precision)."""

    year: int
    month: Month


@dataclass(frozen=True, slots=True)
class Y:
    """A year-only date (reduced precision)."""

    year: int


@dataclass(frozen=True, slots=True)
class LongYear:
    """A year with more than four digits, prefixed with Y."""

    year: int


type DateValue = YMD | YM | Y | LongYear


# --------------------------------------------------------------------------- #
# Season and unspecified values
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class SeasonValue:
    """A season reference, e.g., 2001-21 for Spring 2001."""

    year: int
    season: L1Season | L2Season


@dataclass(frozen=True, slots=True)
class UnspecifiedValue:
    """A date with unspecified digits marked by X."""

    year: str | None = None  # e.g., "201X", "20XX", "XXXX"
    month: str | None = None  # e.g., "0X", "1X", "XX"
    day: str | None = None  # e.g., "0X", "1X", "XX"

    def __post_init__(self) -> None:
        if not any((self.year, self.month, self.day)):
            raise ValueError("UnspecifiedValue must have at least one component")


type ConcreteValue = DateValue | SeasonValue | UnspecifiedValue


# --------------------------------------------------------------------------- #
# Qualified / annotated value (Level 1 uncertainty and approximation)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class DateAnnotated:
    """A value that may carry uncertainty (~) or approximation (?) qualifiers.

    Level 1 qualifiers apply to the entire value.
    """

    value: ConcreteValue
    uncertain: bool = False
    approximate: bool = False


# --------------------------------------------------------------------------- #
# Interval (Level 0 and Level 1)
# --------------------------------------------------------------------------- #

type Endpoint = DateAnnotated | Literal["open", "unknown"] | None


@dataclass(frozen=True, slots=True)
class Interval:
    """A date interval with lower and upper bounds.

    Each endpoint may be a qualified date, the keyword "open" (..),
    "unknown" (/ at one end), or absent (None — treated as unknown).
    """

    lower: Endpoint
    upper: Endpoint


# --------------------------------------------------------------------------- #
# Consecutive range (Level 2, e.g., 1990..1999)
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Consecutive:
    """A consecutive range expressed with double dots."""

    lower: DateValue | None
    upper: DateValue | None


# --------------------------------------------------------------------------- #
# List (Level 2, choice [ ] or inclusive { })
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ListEDTF:
    """A list of EDTF values.

    ``is_choice`` distinguishes ``[a, b]`` (choice) from ``{a, b}`` (inclusive).
    """

    members: list["EDTF"]
    is_choice: bool


# --------------------------------------------------------------------------- #
# Top-level EDTF union type
# --------------------------------------------------------------------------- #

type EDTF = DateAnnotated | Interval | Consecutive | ListEDTF
