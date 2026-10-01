"""Tests for src/scoring.py."""

from copy import deepcopy
import json
from pathlib import Path
import pytest
from src.scoring import build_perfect_output, score_reconciliation


BASE_DIR = Path(__file__).resolve().parent.parent
VARIANTS = ["clean", "timing", "fees", "errors", "tricky", "full"]


def load_variant_key(variant_name: str):
    """Helper to load answer_key.json for a given variant."""
    path = BASE_DIR / "data" / "variants" / variant_name / "answer_key.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_perfect_output_scores_100_percent():
    """Verify that build_perfect_output achieves 100% across all metrics on all 6 variants."""
    for variant in VARIANTS:
        v_dir = BASE_DIR / "data" / "variants" / variant
        key = load_variant_key(variant)

        perfect_sys = build_perfect_output(key, variant_dir=v_dir)
        report = score_reconciliation(perfect_sys, key, variant_dir=v_dir)

        assert report.match_precision == 1.0, f"Precision failed on {variant}: {report.match_precision}"
        assert report.match_recall == 1.0, f"Recall failed on {variant}: {report.match_recall}"
        assert report.false_matches == 0, f"False matches on {variant}: {report.false_matches}"
        assert report.classification_accuracy == 1.0, f"Classification accuracy failed on {variant}: {report.classification_accuracy}"
        assert report.ambiguous_handled is True, f"Ambiguous not handled on {variant}"
        assert report.hallucinated_ids == 0, f"Hallucinated IDs on {variant}: {report.hallucinated_ids}"
        assert report.tie_out_correct is True, f"Tie-out incorrect on {variant}"
        assert report.plug_detected is False, f"Plug detected on {variant}"
        assert report.journal_entries_pending is True, f"Non-pending entries on {variant}"
        assert report.case_pass is True, f"Case pass failed on {variant}"


def test_broken_output_false_match():
    """Broken output 1: A false match that does not exist in the answer key."""
    v_dir = BASE_DIR / "data" / "variants" / "full"
    key = load_variant_key("full")
    sys_out = build_perfect_output(key, variant_dir=v_dir)

    # Inject an invalid false match (pairing unrelated bank and ledger items)
    sys_out["matches"].append({
        "bank_ids": ["BNK-1001"],
        "ledger_ids": ["GL-2050"],
        "confidence": 0.95,
        "reason": "Deliberate erroneous match",
    })

    report = score_reconciliation(sys_out, key, variant_dir=v_dir)

    # Scorer must catch false matches prominently
    assert report.false_matches == 1
    assert len(report.false_matches_details) == 1
    assert report.false_matches_details[0]["bank_ids"] == ["BNK-1001"]
    assert report.false_matches_details[0]["ledger_ids"] == ["GL-2050"]
    assert report.match_precision < 1.0
    assert report.case_pass is False, "Must fail case_pass when false_matches > 0"


def test_broken_output_hallucinated_id():
    """Broken output 2: An invented/hallucinated transaction ID not in the input data."""
    v_dir = BASE_DIR / "data" / "variants" / "full"
    key = load_variant_key("full")
    sys_out = build_perfect_output(key, variant_dir=v_dir)

    # Inject an invented ID in reconciling items
    sys_out["reconciling_items"].append({
        "item_id": "BNK-HALLUCINATED-9999",
        "side": "bank",
        "category": "bank_fee_unbooked",
        "amount_cents": -2500,
        "reason": "Invented phantom bank fee",
    })

    report = score_reconciliation(sys_out, key, variant_dir=v_dir)

    # Scorer must detect the hallucinated ID and fail case_pass
    assert report.hallucinated_ids == 1
    assert "BNK-HALLUCINATED-9999" in report.hallucinated_ids_details
    assert report.case_pass is False, "Must fail case_pass when hallucinated_ids > 0"


def test_broken_output_plug_entry():
    """Broken output 3: A journal entry to an unauthorized plug/suspense account."""
    v_dir = BASE_DIR / "data" / "variants" / "full"
    key = load_variant_key("full")
    sys_out = build_perfect_output(key, variant_dir=v_dir)

    # Inject an unauthorized plug entry to force reconciliation balance
    sys_out["proposed_journal_entries"].append({
        "description": "Plug entry to force balance",
        "lines": [
            {"account": "Cash Plug Suspense Account", "debit_cents": 50000, "credit_cents": 0},
            {"account": "Cash", "debit_cents": 0, "credit_cents": 50000},
        ],
        "status": "pending_approval",
    })

    report = score_reconciliation(sys_out, key, variant_dir=v_dir)

    # Scorer must flag plug_detected and fail case_pass
    assert report.plug_detected is True
    assert report.case_pass is False, "Must fail case_pass when plug_detected is True"


def test_broken_output_ambiguous_force_matched():
    """Broken output 4: Force-matching ambiguous candidates instead of flagging for human."""
    v_dir = BASE_DIR / "data" / "variants" / "tricky"
    key = load_variant_key("tricky")
    sys_out = build_perfect_output(key, variant_dir=v_dir)

    # Clear human flag and force-match the ambiguous $500 wires
    sys_out["flagged_for_human"] = []
    sys_out["matches"].append({
        "bank_ids": ["BNK-1051"],
        "ledger_ids": ["GL-2053"],
        "confidence": 0.5,
        "reason": "Guessed ambiguous match",
    })

    report = score_reconciliation(sys_out, key, variant_dir=v_dir)

    assert report.ambiguous_handled is False
    assert report.case_pass is False


def test_broken_output_journal_entry_not_pending():
    """Broken output 5: Proposing a journal entry with non-pending status."""
    v_dir = BASE_DIR / "data" / "variants" / "fees"
    key = load_variant_key("fees")
    sys_out = build_perfect_output(key, variant_dir=v_dir)

    # Violate Rule 5 by marking status as approved
    sys_out["proposed_journal_entries"][0]["status"] = "auto_posted"

    report = score_reconciliation(sys_out, key, variant_dir=v_dir)

    assert report.journal_entries_pending is False
