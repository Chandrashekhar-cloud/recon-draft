"""Tests for src/money.py."""

from decimal import Decimal
import pytest
from src.money import to_cents, fmt


def test_zero_one_plus_zero_two():
    """Verify standard floating point hazard cases produce exact cents with Decimal."""
    # 0.1 + 0.2 in floats evaluates to 0.30000000000000004
    # With to_cents, 10 cents + 20 cents must equal 30 cents exactly
    cents_a = to_cents("0.1")
    cents_b = to_cents("0.2")
    assert cents_a == 10
    assert cents_b == 20
    assert cents_a + cents_b == 30

    # Also test numeric inputs
    assert to_cents(0.1) == 10
    assert to_cents(0.2) == 20
    assert to_cents(0.1) + to_cents(0.2) == 30

    # 0.01 + 0.02
    assert to_cents("0.01") == 1
    assert to_cents("0.02") == 2
    assert to_cents("0.01") + to_cents("0.02") == 3

    # Common precision bug with 29.99 * 100 in floats
    assert to_cents("29.99") == 2999
    assert to_cents(29.99) == 2999


def test_negatives():
    """Verify various negative formats convert properly and format correctly."""
    # Different string formats of negative amounts
    assert to_cents("-$12.00") == -1200
    assert to_cents("$-12.00") == -1200
    assert to_cents("-12.00") == -1200
    assert to_cents("($12.00)") == -1200
    assert to_cents("(12.00)") == -1200
    assert to_cents("-$0.05") == -5
    assert to_cents("-0.05") == -5

    # Numbers
    assert to_cents(-12) == -1200
    assert to_cents(-12.5) == -1250
    assert to_cents(Decimal("-12.00")) == -1200

    # Negative formatting with fmt()
    assert fmt(-1200) == "-$12.00"
    assert fmt(-5) == "-$0.05"
    assert fmt(-1) == "-$0.01"
    assert fmt(-154025) == "-$1,540.25"


def test_commas():
    """Verify thousand-separated numbers are parsed and formatted properly."""
    assert to_cents("1,540.25") == 154025
    assert to_cents("$1,540.25") == 154025
    assert to_cents("1,234,567.89") == 123456789
    assert to_cents("$1,234,567.89") == 123456789
    assert to_cents("-$1,234,567.89") == -123456789
    assert to_cents("($1,234,567.89)") == -123456789

    # fmt outputs with commas
    assert fmt(154025) == "$1,540.25"
    assert fmt(123456789) == "$1,234,567.89"
    assert fmt(-123456789) == "-$1,234,567.89"


def test_three_decimals_rounding():
    """Verify rounding of 3 decimals uses round-half-up to nearest cent."""
    # Positive 3 decimals: 0.005 rounds up to 0.01, 0.004 rounds down to 0.00
    assert to_cents("10.005") == 1001
    assert to_cents("10.004") == 1000
    assert to_cents("0.005") == 1
    assert to_cents("0.004") == 0
    assert to_cents("1.235") == 124
    assert to_cents("1.234") == 123

    # Negative 3 decimals: round half away from zero
    assert to_cents("-10.005") == -1001
    assert to_cents("-10.004") == -1000
    assert to_cents("-0.005") == -1
    assert to_cents("-0.004") == 0

    # Numeric input with 3 decimals
    assert to_cents(10.005) == 1001
    assert to_cents(10.004) == 1000


def test_zero_and_edge_cases():
    """Verify 0, small amounts, and basic types."""
    assert to_cents("0") == 0
    assert to_cents("0.00") == 0
    assert to_cents("$0.00") == 0
    assert to_cents(0) == 0
    assert fmt(0) == "$0.00"

    assert to_cents("0.05") == 5
    assert fmt(5) == "$0.05"
    assert to_cents("0.99") == 99
    assert fmt(99) == "$0.99"


def test_fmt_rejects_floats():
    """Rule 1: Never use floats for money. fmt must enforce integer cents."""
    with pytest.raises(TypeError):
        fmt(12.5)  # type: ignore

    with pytest.raises(TypeError):
        fmt("1200")  # type: ignore

    with pytest.raises(TypeError):
        fmt(True)  # type: ignore


def test_to_cents_invalid_input():
    """Invalid strings and types should raise descriptive errors."""
    with pytest.raises(ValueError):
        to_cents("")

    with pytest.raises(ValueError):
        to_cents("abc")

    with pytest.raises(ValueError):
        to_cents("$")

    with pytest.raises(TypeError):
        to_cents(None)  # type: ignore

    with pytest.raises(TypeError):
        to_cents(True)  # type: ignore
