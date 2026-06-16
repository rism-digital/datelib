"""Extended Date/Time Format (EDTF) parser for Python."""

from datelib.bounds import lower_year, upper_year
from datelib.parser import is_valid, parse
from datelib.result import Err, Ok, ParseError, Result
from datelib.types import (
    EDTF,
    DateAnnotated,
    DateValue,
    Interval,
    ListEDTF,
    SeasonValue,
    UnspecifiedValue,
)

__all__ = [
    # Parser
    "parse",
    "is_valid",
    "lower_year",
    "upper_year",
    # Result
    "Result",
    "Ok",
    "Err",
    "ParseError",
    # Types
    "DateAnnotated",
    "DateValue",
    "EDTF",
    "Interval",
    "ListEDTF",
    "SeasonValue",
    "UnspecifiedValue",
]
