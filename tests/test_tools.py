"""Unit tests for src/tools.py."""

from pathlib import Path
import pytest

from src.tools import (
    ALL_TOOLS,
    FIND_BY_AMOUNT_SCHEMA,
    GET_ITEM_SCHEMA,
    ReconciliationToolbox,
    SUBMIT_RECONCILIATION_SCHEMA,
    SUM_ITEMS_SCHEMA,
)


BASE_DIR = Path(__file__).resolve().parent.parent
CLEAN_DIR = BASE_DIR / "data" / "variants" / "clean"


@pytest.fixture
def clean_toolbox():
    """Create a ReconciliationToolbox instance on the clean variant."""
    return ReconciliationToolbox(
        bank_data=CLEAN_DIR / "bank.csv",
        ledger_data=CLEAN_DIR / "ledger.csv",
        unmatched_bank_ids={"BNK-1001", "BNK-1012"},
        unmatched_ledger_ids={"GL-2001", "GL-2012"},
    )


def test_tool_schemas_structure():
    """Verify tool schemas have required Anthropic format and names."""
    tool_names = {t["name"] for t in ALL_TOOLS}
    assert tool_names == {"get_item", "find_by_amount", "sum_items", "submit_reconciliation"}
    for t in ALL_TOOLS:
        assert "description" in t
        assert "input_schema" in t
        assert t["input_schema"]["type"] == "object"


def test_get_item_found_and_not_found(clean_toolbox):
    """Verify get_item returns the row or error if not found."""
    # Bank row found
    bank_item = clean_toolbox.get_item("BNK-1001")
    assert bank_item["bank_id"] == "BNK-1001"
    assert bank_item["amount_cents"] == -450000
    assert bank_item["side"] == "bank"

    # Ledger row found
    ledger_item = clean_toolbox.get_item("GL-2001")
    assert ledger_item["ledger_id"] == "GL-2001"
    assert ledger_item["amount_cents"] == -450000
    assert ledger_item["side"] == "ledger"

    # Not found
    not_found = clean_toolbox.get_item("NONEXISTENT-999")
    assert not_found == {"error": "not found"}


def test_find_by_amount(clean_toolbox):
    """Verify find_by_amount searches unmatched rows on the given side."""
    # Find rent check (-450000) on bank side
    bank_results = clean_toolbox.find_by_amount(-450000, "bank")
    assert isinstance(bank_results, list)
    assert len(bank_results) == 1
    assert bank_results[0]["bank_id"] == "BNK-1001"

    # Find rent check (-450000) on ledger side
    ledger_results = clean_toolbox.find_by_amount(-450000, "ledger")
    assert isinstance(ledger_results, list)
    assert len(ledger_results) == 1
    assert ledger_results[0]["ledger_id"] == "GL-2001"

    # Unmatched filter test: item not in unmatched set should not return
    clean_toolbox.unmatched_bank_ids.remove("BNK-1001")
    empty_results = clean_toolbox.find_by_amount(-450000, "bank")
    assert len(empty_results) == 0

    # Invalid side
    err_res = clean_toolbox.find_by_amount(-450000, "invalid_side")
    assert "error" in err_res


def test_sum_items(clean_toolbox):
    """Verify sum_items computes exact integer cents sum or returns error."""
    # Valid IDs
    res = clean_toolbox.sum_items(["BNK-1001", "BNK-1012"])
    assert res["count"] == 2
    assert res["sum_cents"] == -450000 + (-184050)

    # Invalid ID in list returns error
    err_res = clean_toolbox.sum_items(["BNK-1001", "FAKE-ID"])
    assert "error" in err_res
    assert "FAKE-ID" in err_res["error"]


def test_execute_dispatch(clean_toolbox):
    """Verify execute dispatches to tool methods."""
    res1 = clean_toolbox.execute("get_item", {"item_id": "BNK-1001"})
    assert res1["bank_id"] == "BNK-1001"

    res2 = clean_toolbox.execute("submit_reconciliation", {})
    assert res2.get("status") == "submitted"
