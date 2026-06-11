# datelib

A type-safe, correct Extended Date/Time Format (EDTF) parser for Python.

## Features

- **Correctness first**: Matches elm-edtf parity, strong static typing
- **Pure Python**: No heavy parsing dependencies
- **Result-based API**: `Ok(parsed) | Err(error)` instead of exceptions
- **Optional natlang module**: Convert natural language to EDTF strings
- **Optional humanize module**: Render EDTF dates in human-readable form

## Quick Start

```python
import datelib

result = datelib.parse("1984-06~")
# Ok(Date(year=1984, month=6, approximate=True))

result = datelib.parse("not a date")
# Err(ParseError(...))
```

## Installation

```bash
pip install datelib
# With natural language support:
pip install datelib[natlang]
```
