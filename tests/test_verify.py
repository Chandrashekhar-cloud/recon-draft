"""Unit tests for src/verify.py verification layer."""

from copy import deepcopy
import json
from pathlib import Path
import pytest

from src.scoring import build_perfect_output
from src.verify import verify_submission


BASE_DIR = Path(__file__).resolve().parent.parent
FULL_DIR = BASE_DIR / "data" / "variants" / "full"
CLEAN_DIR = BASE_DIR / "data" / "variants" / "clean"


@pytest.fixture
def perfect_full_submission():
    with open(FULL_DIR / "answer_key.json", "r", encoding="utf-8") as f:
        ak = json.load(f)
    return build_perfect_output(ak, variant_dir=FULL_DIR)


def test_verify_perfect_submission_passes(perfect_full_submission):
    """Verify ground-truth submission has 0 violations and tie_out is verified."""
    cleaned, violations = verify_submission(deepcopy(perfect_full_submission), FULL_DIR)
    assert len(violations) == 0
    assert cleaned["tie_out"]["can_prove"] is True
    assert cleaned["tie_out"]["difference_cents"] == 0
    assert len(cleaned["matches"]) == len(perfect_full_submission["matches"])


def test_verify_catches_hallucinated_id(perfect_full_submission):
    """Verify unknown IDs in matches and reconciling items are caught and moved to flagged."""
    sub = deepcopy(perfect_full_submission)
    sub["matches"].append({
        "bank_ids": ["FAKE-BNK-999"],
        "ledger_ids": ["GL-2001"],
        "confidence": 1.0,
        "reason": "Hallucinated match",
    })
    sub["reconciling_items"].append({
        "item_id": "FAKE-RECON-888",
        "side": "bank",
        "category": "bank_fee_unbooked",
        "amount_cents": -500,
        "reason": "Fake fee",
    })

    cleaned, violations = verify_submission(sub, FULL_DIR)
    assert any("FAKE-BNK-999" in v for v in violations)
    assert any("FAKE-RECON-888" in v for v in violations)
    assert not any("FAKE-BNK-999" in m["bank_ids"] for m in cleaned["matches"])
    assert not any(r["item_id"] == "FAKE-RECON-888" for r in cleaned["reconciling_items"])


def test_verify_catches_duplicate_match_id(perfect_full_submission):
    """Verify an ID cannot be used in two different matches."""
    sub = deepcopy(perfect_full_submission)
    # Repeat GL-2001 in another match
    sub["matches"].append({
        "bank_ids": ["BNK-1002"],
        "ledger_ids": ["GL-2001"],
        "confidence": 0.9,
        "reason": "Duplicate match attempt",
    })

    cleaned, violations = verify_submission(sub, FULL_DIR)
    assert any("already matched" in v for v in violations)


def test_verify_catches_one_to_many_sum_mismatch(perfect_full_submission):
    """Verify one-to-many matches where bank sum != ledger sum are rejected and flagged."""
    sub = deepcopy(perfect_full_submission)
    # Remove existing matches containing these IDs so they are not caught as duplicates
    sub["matches"] = [
        m for m in sub["matches"]
        if "BNK-1001" not in m["bank_ids"] and "GL-2002" not in m["ledger_ids"] and "GL-2003" not in m["ledger_ids"]
    ]
    # Pair 1 bank with 2 ledger where sum does not match
    sub["matches"].append({
        "bank_ids": ["BNK-1001"],
        "ledger_ids": ["GL-2002", "GL-2003"],
        "confidence": 0.5,
        "reason": "Mismatched one-to-many",
    })

    cleaned, violations = verify_submission(sub, FULL_DIR)
    assert any("One-to-many match amount mismatch" in v for v in violations)


def test_verify_catches_invalid_reconciling_category(perfect_full_submission):
    """Verify reconciling item with invalid category is rejected."""
    sub = deepcopy(perfect_full_submission)
    sub["reconciling_items"].append({
        "item_id": "BNK-1001",
        "side": "bank",
        "category": "invalid_magic_category",
        "amount_cents": -450000,
        "reason": "Test category",
    })

    cleaned, violations = verify_submission(sub, FULL_DIR)
    assert any("invalid category" in v for v in violations)


def test_verify_catches_unbalanced_or_plug_journal_entry(perfect_full_submission):
    """Verify journal entries with unequal debits/credits or plug accounts are rejected."""
    sub = deepcopy(perfect_full_submission)
    original_je_count = len(sub["proposed_journal_entries"])

    # 1. Unbalanced debits != credits
    sub["proposed_journal_entries"].append({
        "description": "Unbalanced entry",
        "lines": [
            {"account": "Bank Fees", "debit_cents": 5000, "credit_cents": 0},
            {"account": "Cash", "debit_cents": 0, "credit_cents": 4000},
        ],
        "status": "pending_approval",
    })
    # 2. Plug account
    sub["proposed_journal_entries"].append({
        "description": "Forced Plug entry",
        "lines": [
            {"account": "Suspense / Plug Account", "debit_cents": 1000, "credit_cents": 0},
            {"account": "Cash", "debit_cents": 0, "credit_cents": 1000},
        ],
        "status": "pending_approval",
    })

    cleaned, violations = verify_submission(sub, FULL_DIR)
    assert any("debits (5000 cents) do not equal credits" in v for v in violations)
    assert any("plug/suspense account" in v for v in violations)
    assert len(cleaned["proposed_journal_entries"]) == original_je_count


def test_verify_recomputes_tie_out_and_ignores_claimed_numbers(perfect_full_submission):
    """Verify tie-out numbers submitted by Claude are never trusted and are recomputed."""
    sub = deepcopy(perfect_full_submission)
    # Claude submits bogus tie-out numbers
    sub["tie_out"] = {
        "adjusted_bank_cents": 999999999,
        "adjusted_book_cents": 888888888,
        "difference_cents": 111111111,
        "can_prove": True,
    }

    cleaned, violations = verify_submission(sub, FULL_DIR)
    # Python recomputed tie_out overwrites Claude's numbers
    assert cleaned["tie_out"]["difference_cents"] == 0
    assert cleaned["tie_out"]["adjusted_bank_cents"] != 999999999
    assert cleaned["tie_out"]["can_prove"] is True

