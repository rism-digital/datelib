"""Result type for parsing operations."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar, Generic, TypeVar

T = TypeVar("T")
U = TypeVar("U")
E = TypeVar("E")


@dataclass(frozen=True, slots=True)
class ParseError:
    """Error information from a failed parse."""

    message: str
    position: int
    input_string: str

    def __str__(self) -> str:
        return f"Parse error at position {self.position}: {self.message}"


@dataclass(frozen=True, slots=True)
class Ok(Generic[T]):
    """A successful parse result containing the parsed value."""

    is_ok: ClassVar[bool] = True
    is_err: ClassVar[bool] = False
    value: T

    def unwrap(self) -> T:
        return self.value

    def unwrap_err(self) -> E:
        raise ValueError(f"Called unwrap_err on Ok value: {self.value}")

    def map(self, f: Callable[[T], U]) -> "Ok[U]":
        return Ok(f(self.value))

    def map_err(self, _f: Callable[[E], object]) -> "Ok[T]":
        return self

    def __repr__(self) -> str:
        return f"Ok({self.value!r})"


@dataclass(frozen=True, slots=True)
class Err(Generic[E]):
    """A failed parse result containing the error."""

    is_ok: ClassVar[bool] = False
    is_err: ClassVar[bool] = True
    value: E

    def unwrap(self) -> T:
        raise ValueError(f"Called unwrap on an Err value: {self.value}")

    def unwrap_err(self) -> E:
        return self.value

    def map(self, _f: Callable[[T], U]) -> "Err[E]":
        return self

    def map_err(self, f: Callable[[E], U]) -> "Err[U]":
        return Err(f(self.value))

    def __repr__(self) -> str:
        return f"Err({self.value!r})"


type Result[T, E] = Ok[T] | Err[E]
