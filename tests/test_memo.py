"""Unit tests for src/memo.py reviewer memo generator and verification."""

import json
from pathlib import Path
import pytest

from src.memo import (
    build_template_memo,
    check_memo_amounts,
    extract_dollar_amounts,
    generate_reviewer_memo,
    get_allowed_amounts,
)
from src.scoring import build_perfect_output


BASE_DIR = Path(__file__).resolve().parent.parent
FULL_DIR = BASE_DIR / "data" / "variants" / "full"


@pytest.fixture
def sample_verified_output():
    with open(FULL_DIR / "answer_key.json", "r", encoding="utf-8") as f:
        ak = json.load(f)
    return build_perfect_output(ak, variant_dir=FULL_DIR)


def test_extract_dollar_amounts():
    """Verify extract_dollar_amounts correctly extracts integer cents from currency strings."""
    text = (
        "We reconciled $1,234.56 of items. Unbooked fees were $40.00 and interest was $55.20. "
        "A returned check cost -$480.00, or ($480.00) in accounting notation. The variance is $0.00."
    )
    extracted = extract_dollar_amounts(text)
    assert 123456 in extracted
    assert 4000 in extracted
    assert 5520 in extracted
    assert -48000 in extracted or 48000 in [abs(x) for x in extracted]
    assert 0 in extracted


def test_get_allowed_amounts(sample_verified_output):
    """Verify get_allowed_amounts collects amounts from reconciling items, JEs, and tie_out."""
    allowed = get_allowed_amounts(sample_verified_output, FULL_DIR)
    # Check 0 is always allowed
    assert 0 in allowed
    # Check fee amount ($40.00 -> 4000)
    assert 4000 in allowed
    # Check interest amount ($55.20 -> 5520)
    assert 5520 in allowed
    # Check tie_out balance ($87,723.65 -> 8772365)
    assert 8772365 in allowed


def test_check_memo_amounts_valid(sample_verified_output):
    """Verify check_memo_amounts passes when all amounts exist in verified results."""
    valid_memo = (
        "Reconciliation complete. Unbooked fee of $40.00 and interest of $55.20 were identified. "
        "Draft journal entries are pending approval. Adjusted balance is $87,723.65 with $0.00 variance."
    )
    is_valid, unverified = check_memo_amounts(valid_memo, sample_verified_output, FULL_DIR)
    assert is_valid is True
    assert len(unverified) == 0


def test_check_memo_amounts_catches_unverified_amount(sample_verified_output):
    """Verify check_memo_amounts catches hallucinated/unverified amounts."""
    bad_memo = (
        "Reconciliation complete. We also noticed an unexpected fee of $99,999.00 not in the records."
    )
    is_valid, unverified = check_memo_amounts(bad_memo, sample_verified_output, FULL_DIR)
    assert is_valid is False
    assert 9999900 in unverified


def test_build_template_memo_contents(sample_verified_output):
    """Verify build_template_memo covers matches, proposed JEs, flagged items, and tie-out."""
    template = build_template_memo(sample_verified_output)
    assert "matched transaction groups" in template
    assert "Proposed Journal Entries" in template
    assert "pending approval" in template
    assert "Items Requiring Human Review" in template
    assert "Tie-Out Status: Proved" in template


def test_generate_reviewer_memo_replaces_invalid_and_sets_memo_checked_false(sample_verified_output, monkeypatch):
    """Verify generate_reviewer_memo replaces memo with template summary if unverified amount is present."""
    from unittest.mock import MagicMock
    from src.llm import LLMResponse

    # Simulate Claude inventing an unverified dollar amount ($123,456.78)
    bad_response = LLMResponse(
        content="We reconciled the accounts. Invented balance of $123,456.78 was discovered.",
        input_tokens=500,
        output_tokens=60,
        elapsed_seconds=0.7,
        model="claude-3-5-sonnet-20241022",
    )

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")

    from unittest.mock import patch
    with patch("src.llm.call_claude", return_value=bad_response):
        memo_text, memo_checked = generate_reviewer_memo(sample_verified_output, FULL_DIR, mock=False)
        assert memo_checked is False
        assert "$123,456.78" not in memo_text
        assert "Reconciliation Review:" in memo_text  # Replaced with template


def test_generate_reviewer_memo_valid_in_mock_mode(sample_verified_output):
    """Verify mock mode generates compliant memo with memo_checked=True."""
    memo_text, memo_checked = generate_reviewer_memo(sample_verified_output, FULL_DIR, mock=True)
    assert memo_checked is True
    assert len(memo_text.split()) <= 250
    assert "Tie-Out Status" in memo_text
