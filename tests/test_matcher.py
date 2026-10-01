"""Tests for src/matcher.py."""

from pathlib import Path
import pandas as pd
import pytest
from src.matcher import match_transactions, MatchResult


BASE_DIR = Path(__file__).resolve().parent.parent


def test_matcher_clean_variant_matches_everything():
    """Verify that on the 'clean' variant, the matcher resolves 100% of rows without leftovers."""
    variant_dir = BASE_DIR / "data" / "variants" / "clean"
    bank_csv = variant_dir / "bank.csv"
    ledger_csv = variant_dir / "ledger.csv"

    bank_df = pd.read_csv(bank_csv)
    ledger_df = pd.read_csv(ledger_csv)

    result = match_transactions(bank_csv, ledger_csv)

    # All 49 rows should be matched
    assert len(result.matched_pairs) == 49
    assert len(result.unmatched_bank) == 0
    assert len(result.unmatched_ledger) == 0
    assert len(result.ambiguous_candidates) == 0

    # Total resolved rows equals total input rows
    assert 2 * len(result.matched_pairs) == len(bank_df) + len(ledger_df)

    # Check reason strings on matched pairs
    for pair in result.matched_pairs:
        assert "Exact unique match" in pair["reason"]
        assert pair["date_diff_days"] <= 3
        assert pair["amount_cents"] == pair["bank_row"]["amount_cents"]
        assert pair["amount_cents"] == pair["ledger_row"]["amount_cents"]


def test_matcher_does_not_modify_inputs():
    """Verify that the matcher leaves caller data completely unchanged."""
    variant_dir = BASE_DIR / "data" / "variants" / "clean"
    bank_df = pd.read_csv(variant_dir / "bank.csv")
    ledger_df = pd.read_csv(variant_dir / "ledger.csv")

    bank_copy = bank_df.copy(deep=True)
    ledger_copy = ledger_df.copy(deep=True)

    match_transactions(bank_df, ledger_df)

    pd.testing.assert_frame_equal(bank_df, bank_copy)
    pd.testing.assert_frame_equal(ledger_df, ledger_copy)


def test_matcher_ambiguous_identical_amounts():
    """Verify that multiple candidates for the same amount/window are put into ambiguous_candidates."""
    bank_rows = [
        {"bank_id": "B1", "date": "2026-09-18", "description": "WIRE 500", "amount_cents": -50000, "running_balance_cents": 100000},
        {"bank_id": "B2", "date": "2026-09-18", "description": "WIRE 500", "amount_cents": -50000, "running_balance_cents": 50000},
    ]
    ledger_rows = [
        {"ledger_id": "L1", "date": "2026-09-18", "memo": "Contractor A", "amount_cents": -50000, "reference": "REF1", "type": "transfer"},
        {"ledger_id": "L2", "date": "2026-09-18", "memo": "Contractor B", "amount_cents": -50000, "reference": "REF2", "type": "transfer"},
    ]

    res = match_transactions(bank_rows, ledger_rows)

    assert len(res.matched_pairs) == 0
    assert len(res.unmatched_bank) == 0
    assert len(res.unmatched_ledger) == 0
    assert len(res.ambiguous_candidates) == 1

    group = res.ambiguous_candidates[0]
    assert group["amount_cents"] == -50000
    assert set(group["bank_ids"]) == {"B1", "B2"}
    assert set(group["ledger_ids"]) == {"L1", "L2"}


def test_matcher_date_window_boundary():
    """Verify that matches beyond 3 calendar days are rejected."""
    bank_rows = [
        {"bank_id": "B1", "date": "2026-09-01", "description": "ACH", "amount_cents": 10000, "running_balance_cents": 10000},
        {"bank_id": "B2", "date": "2026-09-05", "description": "ACH", "amount_cents": 20000, "running_balance_cents": 30000},
    ]
    ledger_rows = [
        # Exactly 3 days diff (Sep 01 vs Sep 04) -> matches
        {"ledger_id": "L1", "date": "2026-09-04", "memo": "Invoice 1", "amount_cents": 10000, "reference": "INV1", "type": "ach"},
        # 4 days diff (Sep 05 vs Sep 01) -> does NOT match
        {"ledger_id": "L2", "date": "2026-09-01", "memo": "Invoice 2", "amount_cents": 20000, "reference": "INV2", "type": "ach"},
    ]

    res = match_transactions(bank_rows, ledger_rows)

    assert len(res.matched_pairs) == 1
    assert res.matched_pairs[0]["bank_id"] == "B1"
    assert res.matched_pairs[0]["ledger_id"] == "L1"

    assert len(res.unmatched_bank) == 1
    assert res.unmatched_bank[0]["bank_id"] == "B2"

    assert len(res.unmatched_ledger) == 1
    assert res.unmatched_ledger[0]["ledger_id"] == "L2"
