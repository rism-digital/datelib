"""
Benchmark: antequem vs. python-edtf (pyparsing-based parser)

Usage:
    uv run python benchmarks/compare.py

Compares strict parsing performance across a representative set of EDTF strings.
Also checks that both libraries succeed / fail on the same inputs (correctness
smoke test).
"""

from __future__ import annotations

import time

# --- python-edtf (pyparsing) ---
import edtf as python_edtf

# --- antequem (our implementation) ---
import antequem


# Representative test corpus covering Level 0 and Level 1
TEST_STRINGS: list[str] = [
    # Level 0: Plain dates
    "1985",
    "1985-04",
    "1985-04-12",
    # Level 1: Long years, negative years
    "Y170000002",
    "-1985",
    "-1985-04",
    # Level 1: Seasons
    "2001-21",
    "2001-22",
    "2001-23",
    "2001-24",
    # Level 1: Uncertainty / approximation
    "1984?",
    "2004-06~",
    "2004-06-11%",
    "1984?~",
    "201X~",
    # Level 1: Unspecified (masked) digits
    "201X",
    "20XX",
    "2004-XX",
    "1985-04-XX",
    "1985-XX-XX",
    # Level 1: Intervals
    "1964/2008",
    "2004-06/2006-08",
    "2004-02-01/2005-02-08",
    "1985/..",
    "../1985",
    "1985/",
    "/1985",
    "1984?/2004~",
    # Invalid inputs (should be rejected fast)
    "not a date",
    "",
    "1985-13-01",
    "2015-02-29",
]

# Number of iterations per string
N_ITERATIONS: int = 1_000


def bench_python_edtf(strings: list[str], n: int) -> float:
    """Run python-edtf parsing *n* times over the given strings."""
    start = time.perf_counter()
    for _ in range(n):
        for s in strings:
            try:
                python_edtf.parse_edtf(s)
            except Exception:
                pass
    end = time.perf_counter()
    return end - start


def bench_antequem(strings: list[str], n: int) -> float:
    """Run antequem parsing *n* times over the given strings."""
    start = time.perf_counter()
    for _ in range(n):
        for s in strings:
            antequem.parse(s)
    end = time.perf_counter()
    return end - start


def correctness_check(strings: list[str]) -> None:
    """Ensure both libraries agree on valid/invalid for every string."""
    print("\n--- Correctness smoke test ---")
    mismatches = 0
    for s in strings:
        py_ok = False
        try:
            python_edtf.parse_edtf(s)
            py_ok = True
        except Exception:
            pass

        antequem_ok = antequem.is_valid(s)

        if py_ok != antequem_ok:
            mismatches += 1
            status = "PASS" if py_ok else "FAIL"
            antequem_status = "PASS" if antequem_ok else "FAIL"
            print(
                f"  MISMATCH: {s!r:25s}  python-edtf={status}  antequem={antequem_status}"
            )

    if mismatches == 0:
        print("  All strings agree on validity.")
    else:
        print(f"  {mismatches}/{len(strings)} strings disagree.")


def main() -> None:
    print("=" * 60)
    print("EDTF Parser Benchmark")
    print("=" * 60)
    print(f"Iterations per string: {N_ITERATIONS:,}")
    print(f"Test corpus size:      {len(TEST_STRINGS)} strings")
    print()

    # Warm-up (JIT-like effects are not expected, but let's be fair)
    bench_python_edtf(TEST_STRINGS, 100)
    bench_antequem(TEST_STRINGS, 100)

    # Actual benchmark
    py_duration = bench_python_edtf(TEST_STRINGS, N_ITERATIONS)
    antequem_duration = bench_antequem(TEST_STRINGS, N_ITERATIONS)

    total_calls = len(TEST_STRINGS) * N_ITERATIONS

    print("--- Results ---")
    print(f"  python-edtf (pyparsing): {py_duration:.3f}s "
          f"({total_calls / py_duration:,.0f} parses/sec)")
    print(f"  antequem (pure Python):    {antequem_duration:.3f}s "
          f"({total_calls / antequem_duration:,.0f} parses/sec)")
    print()

    if antequem_duration < py_duration:
        speedup = py_duration / antequem_duration
        print(f"  antequem is {speedup:.1f}x faster than python-edtf")
    else:
        slowdown = antequem_duration / py_duration
        print(f"  antequem is {slowdown:.1f}x slower than python-edtf")

    correctness_check(TEST_STRINGS)
    print()


if __name__ == "__main__":
    main()
