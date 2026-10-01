"""Money handling module for bank reconciliation.

Follows project rules:
1. All money is stored as integer cents. Never use floats for arithmetic.
2. Uses Decimal for exact parsing and rounding.
"""

from decimal import Decimal, ROUND_HALF_UP
import re
from typing import Union


def to_cents(value: Union[str, int, float, Decimal]) -> int:
    """Convert a string (e.g. '1,540.25', '-$12.00', '($12.00)') or a number into integer cents.

    Uses Decimal for precision and never uses float arithmetic.
    Rounds half-up to the nearest cent when fractional cents (e.g. 3 decimals) are provided.

    Args:
        value: The dollar amount as a string, int, float, or Decimal.

    Returns:
        The amount in integer cents.

    Raises:
        TypeError: If the value type is not supported.
        ValueError: If the string cannot be parsed as a monetary amount.
    """
    if isinstance(value, bool):
        raise TypeError(f"Unsupported boolean value for to_cents: {value}")

    if isinstance(value, (int, float, Decimal)):
        # Convert through string representation to prevent float representation artifacts
        decimal_val = Decimal(str(value))
    elif isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Cannot convert empty string to cents")

        # Accounting format: parentheses denote negative numbers, e.g. ($12.00) or (12.00)
        is_negative = False
        if cleaned.startswith("(") and cleaned.endswith(")"):
            is_negative = True
            cleaned = cleaned[1:-1].strip()

        # Remove currency symbol
        cleaned = cleaned.replace("$", "").strip()

        # Check for leading minus or plus sign
        if cleaned.startswith("-"):
            is_negative = not is_negative
            cleaned = cleaned[1:].strip()
        elif cleaned.startswith("+"):
            cleaned = cleaned[1:].strip()

        # Check again in case minus appeared after currency symbol, e.g. "$ -12.00"
        if cleaned.startswith("-"):
            is_negative = not is_negative
            cleaned = cleaned[1:].strip()

        # Remove thousand-separator commas
        cleaned = cleaned.replace(",", "")

        if not cleaned:
            raise ValueError(f"Invalid monetary string: '{value}'")

        try:
            decimal_val = Decimal(cleaned)
        except Exception as err:
            raise ValueError(f"Could not parse monetary string '{value}': {err}") from err

        if is_negative:
            decimal_val = -decimal_val
    else:
        raise TypeError(f"Unsupported type for to_cents: {type(value).__name__}")

    # Convert dollar Decimal to cents using Decimal multiplication and round half-up
    cents_decimal = (decimal_val * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(cents_decimal)


def fmt(cents: int) -> str:
    """Format an integer cents amount into a standard currency string.

    Examples:
        fmt(154025) -> "$1,540.25"
        fmt(-1200) -> "-$12.00"
        fmt(0) -> "$0.00"

    Args:
        cents: Amount in integer cents. Floats are rejected to enforce Rule 1.

    Returns:
        Formatted currency string with thousands separators.

    Raises:
        TypeError: If cents is not an integer.
    """
    if type(cents) is not int:
        raise TypeError(f"cents must be an integer, got {type(cents).__name__}")

    is_negative = cents < 0
    abs_cents = abs(cents)
    dollars = abs_cents // 100
    remainder = abs_cents % 100

    sign = "-" if is_negative else ""
    return f"{sign}${dollars:,}.{remainder:02d}"
