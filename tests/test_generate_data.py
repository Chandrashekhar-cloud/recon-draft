"""Tests for src/generate_data.py."""

from pathlib import Path
import pytest
from src.generate_data import VARIANTS, build_variant, verify_tie_out


def test_all_variants_tie_out():
    """Verify all 6 variants build without error and strictly satisfy tie-out equality."""
    for variant in VARIANTS:
        bank_rows, ledger_rows, notes, answer_key = build_variant(variant)

        # Basic constraints
        assert len(bank_rows) >= 45
        assert len(ledger_rows) >= 45
        assert len(notes) > 20

        # Check balances structure
        balances = answer_key["balances"]
        assert balances["bank_opening_cents"] > 0
        assert balances["book_opening_cents"] > 0
        assert balances["bank_closing_cents"] > 0
        assert balances["book_closing_cents"] > 0

        # Check tie out
        tie_out = answer_key["tie_out"]
        assert tie_out["difference_cents"] == 0
        assert tie_out["adjusted_bank_cents"] == tie_out["adjusted_book_cents"]

        # Run strict rule verification
        verify_tie_out(answer_key)


def test_generated_files_exist():
    """Verify that all files are created in data/variants/<name>/."""
    base_dir = Path(__file__).resolve().parent.parent
    for variant in VARIANTS:
        variant_dir = base_dir / "data" / "variants" / variant
        assert (variant_dir / "bank.csv").is_file(), f"Missing bank.csv for {variant}"
        assert (variant_dir / "ledger.csv").is_file(), f"Missing ledger.csv for {variant}"
        assert (variant_dir / "notes.txt").is_file(), f"Missing notes.txt for {variant}"
        assert (variant_dir / "answer_key.json").is_file(), f"Missing answer_key.json for {variant}"


def test_tie_out_catches_imbalance():
    """Verify that verify_tie_out raises an AssertionError if an artificial discrepancy is introduced."""
    _, _, _, answer_key = build_variant("clean")
    # Tamper with adjusted_bank
    answer_key["tie_out"]["adjusted_bank_cents"] += 100
    with pytest.raises(AssertionError):
        verify_tie_out(answer_key)
