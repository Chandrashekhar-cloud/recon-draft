"""Tests for src/tieout.py."""

import json
from pathlib import Path
import pytest
from src.tieout import calculate_tie_out, tie_out


BASE_DIR = Path(__file__).resolve().parent.parent
VARIANTS = ["clean", "timing", "fees", "errors", "tricky", "full"]


def test_tieout_on_every_variant_answer_key():
    """Verify calculate_tie_out produces difference_cents == 0 for all 6 variant answer keys."""
    for variant in VARIANTS:
        answer_key_path = BASE_DIR / "data" / "variants" / variant / "answer_key.json"
        assert answer_key_path.is_file(), f"Missing answer_key.json for {variant}"

        with open(answer_key_path, "r", encoding="utf-8") as f:
            answer_key = json.load(f)

        balances = answer_key["balances"]
        reconciling_items = answer_key["reconciling_items"]

        result = calculate_tie_out(balances, reconciling_items)

        # Mathematical tie-out condition must be strictly 0
        assert result["difference_cents"] == 0, f"Variant '{variant}' failed tie-out with diff {result['difference_cents']}"
        assert result["is_tied_out"] is True

        # Must match expected adjusted balances from answer key
        expected_bank = answer_key["tie_out"]["adjusted_bank_cents"]
        expected_book = answer_key["tie_out"]["adjusted_book_cents"]
        assert result["adjusted_bank_cents"] == expected_bank
        assert result["adjusted_book_cents"] == expected_book
        assert result["adjusted_bank_cents"] == result["adjusted_book_cents"]

        # Verify human-readable proof lines are present and structured
        proof = result["proof"]
        assert len(proof) > 10
        assert "=== BANK RECONCILIATION TIE-OUT PROOF ===" in proof[0]
        assert any("Adjusted Bank Balance:" in line for line in proof)
        assert any("Adjusted Book Balance:" in line for line in proof)
        assert any("TIED OUT" in line for line in proof)


def test_tieout_catches_unreconciled_variance():
    """Verify that calculate_tie_out correctly reports non-zero difference when variance exists."""
    balances = {
        "bank_closing_cents": 1000000,
        "book_closing_cents": 900000,  # $1,000 difference
    }
    reconciling_items = []  # No items to reconcile the $1,000 gap

    result = calculate_tie_out(balances, reconciling_items)

    assert result["difference_cents"] == 100000
    assert result["is_tied_out"] is False
    assert any("UNRECONCILED VARIANCE: $1,000.00" in line for line in result["proof"])


def test_tieout_alias():
    """Verify tie_out is an alias for calculate_tie_out."""
    balances = {"bank_closing_cents": 50000, "book_closing_cents": 50000}
    res = tie_out(balances, [])
    assert res["difference_cents"] == 0
    assert res["is_tied_out"] is True
