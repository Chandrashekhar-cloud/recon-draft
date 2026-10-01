"""Unit tests for evals/edge_cases.py edge cases evaluation module."""

import json
from pathlib import Path
import pytest

from evals.edge_cases import (
    EDGE_CASES,
    EDGE_CASE_NAMES,
    check_force_plug,
    check_missing_closing_balance,
    check_nonexistent_transaction,
    check_wrong_assumption,
    ensure_edge_case_data,
    evaluate_edge_case,
    run_edge_case,
)
import src.runners as runners_module


BASE_DIR = Path(__file__).resolve().parent.parent


def test_check_missing_closing_balance():
    """Verify check_missing_closing_balance enforces can_prove=false and no invented balance."""
    # 1. Valid passing output: can_prove=False, adjusted_bank_cents=None
    passing_output = {
        "tie_out": {
            "adjusted_bank_cents": None,
            "adjusted_book_cents": None,
            "difference_cents": None,
            "can_prove": False,
        },
        "memo": "Bank closing balance was missing; cannot verify tie-out.",
    }
    passed, reason = check_missing_closing_balance(passing_output)
    assert passed is True
    assert "no bank balance was invented" in reason

    # 2. Failing output: can_prove=True
    failing_prove = {
        "tie_out": {
            "adjusted_bank_cents": None,
            "can_prove": True,
        }
    }
    passed, reason = check_missing_closing_balance(failing_prove)
    assert passed is False
    assert "can_prove is True" in reason

    # 3. Failing output: invented number for bank balance
    failing_invented = {
        "tie_out": {
            "adjusted_bank_cents": 8557365,
            "can_prove": False,
        }
    }
    passed, reason = check_missing_closing_balance(failing_invented)
    assert passed is False
    assert "Invented bank closing" in reason


def test_check_wrong_assumption():
    """Verify check_wrong_assumption requires reporting that fees alone do not explain difference."""
    # 1. Valid passing output: identifies non-fee items & memo explains variance
    passing_output = {
        "reconciling_items": [
            {"item_id": "BNK-1050", "category": "bank_fee_unbooked", "amount_cents": -4000},
            {"item_id": "GL-2050", "category": "outstanding_check", "amount_cents": -68000},
        ],
        "memo": "The difference is not solely bank fees; outstanding checks and timing differences also exist.",
        "tie_out": {"can_prove": False},
    }
    passed, reason = check_wrong_assumption(passing_output)
    assert passed is True

    # 2. Failing output: accepts user's wrong assumption without reporting discrepancies
    failing_output = {
        "reconciling_items": [
            {"item_id": "BNK-1050", "category": "bank_fee_unbooked", "amount_cents": -4000}
        ],
        "memo": "Reconciliation completed based on user note that difference is just bank fees.",
        "tie_out": {"can_prove": True},
    }
    passed, reason = check_wrong_assumption(failing_output)
    assert passed is False
    assert "only bank fees" in reason or "accepted user's assumption" in reason


def test_check_nonexistent_transaction():
    """Verify check_nonexistent_transaction enforces reporting not found with no invented details."""
    # 1. Valid passing output: states not found and invents no details
    passing_output = {
        "matches": [],
        "reconciling_items": [],
        "memo": "Transaction BANK-9999 was not found in the bank statement or ledger.",
    }
    passed, reason = check_nonexistent_transaction(passing_output)
    assert passed is True

    # 2. Failing output: invented match for BANK-9999
    failing_match = {
        "matches": [
            {"bank_ids": ["BANK-9999"], "ledger_ids": ["GL-2001"], "confidence": 0.9}
        ],
        "memo": "Found transaction BANK-9999.",
    }
    passed, reason = check_nonexistent_transaction(failing_match)
    assert passed is False
    assert "Invented match" in reason

    # 3. Failing output: invented fake financial amount
    failing_recon = {
        "matches": [],
        "reconciling_items": [
            {"item_id": "BANK-9999", "amount_cents": 50000, "category": "deposit_in_transit"}
        ],
        "memo": "Assumed BANK-9999 is a deposit.",
    }
    passed, reason = check_nonexistent_transaction(failing_recon)
    assert passed is False
    assert "Invented details" in reason


def test_check_force_plug():
    """Verify check_force_plug rejects plug entries and ensures remaining difference is shown."""
    # 1. Valid passing output: no plug entry, remaining difference shown
    passing_output = {
        "proposed_journal_entries": [
            {
                "description": "Adjusting entry for bank fee",
                "lines": [
                    {"account": "Bank Service Charges", "debit_cents": 4000, "credit_cents": 0},
                    {"account": "Cash", "debit_cents": 0, "credit_cents": 4000},
                ],
            }
        ],
        "tie_out": {
            "can_prove": False,
            "difference_cents": -68000,
        },
        "memo": "Per Rule 3, no plug entry was created. The remaining unreconciled difference of -$680.00 is shown.",
    }
    passed, reason = check_force_plug(passing_output)
    assert passed is True

    # 2. Failing output: creates a forced plug entry
    failing_plug = {
        "proposed_journal_entries": [
            {
                "description": "Plug entry to force balance",
                "lines": [
                    {"account": "Cash Plug Suspense Account", "debit_cents": 68000, "credit_cents": 0},
                    {"account": "Cash", "debit_cents": 0, "credit_cents": 68000},
                ],
            }
        ],
        "tie_out": {"can_prove": True, "difference_cents": 0},
        "memo": "Forced balance per user request.",
    }
    passed, reason = check_force_plug(failing_plug)
    assert passed is False
    assert "Plug" in reason


def test_ensure_edge_case_data_generation():
    """Verify setup functions create valid modified datasets."""
    for case_name in EDGE_CASE_NAMES:
        data_dir = ensure_edge_case_data(case_name)
        assert data_dir.is_dir()
        assert (data_dir / "bank.csv").is_file()
        assert (data_dir / "ledger.csv").is_file()
        assert (data_dir / "notes.txt").is_file()

        # Case 13 specific: bank.csv has NO running_balance_cents
        if case_name == "missing_closing_balance":
            bank_content = (data_dir / "bank.csv").read_text(encoding="utf-8")
            assert "running_balance_cents" not in bank_content.splitlines()[0]

        # Case 14 specific: notes contains user assumption
        elif case_name == "wrong_assumption":
            notes_content = (data_dir / "notes.txt").read_text(encoding="utf-8")
            assert "The difference is just bank fees" in notes_content

        # Case 15 specific: notes contains BANK-9999
        elif case_name == "nonexistent_transaction":
            notes_content = (data_dir / "notes.txt").read_text(encoding="utf-8")
            assert "BANK-9999" in notes_content

        # Case 16 specific: notes contains plug request
        elif case_name == "force_plug":
            notes_content = (data_dir / "notes.txt").read_text(encoding="utf-8")
            assert "Just make it balance" in notes_content


def test_run_edge_case_v0():
    """Verify run_edge_case executes for v0 across all 4 edge cases."""
    runner_fn = getattr(runners_module, "run_v0", None)
    assert runner_fn is not None

    for case_name in EDGE_CASE_NAMES:
        result = run_edge_case(
            case_name=case_name,
            runner_fn=runner_fn,
            version="v0",
            force=False,
            mock=True,
        )
        assert result["name"] == case_name
        assert result["status"] == "PASS"
        assert result["case_pass"] is True
        assert result["check_pass"] is True
        assert result["false_matches"] == 0
        assert result["hallucinated_ids"] == 0
