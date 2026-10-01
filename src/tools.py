"""Tool definitions and schemas for Claude bank reconciliation agent.

Defines four tools:
1. get_item(item_id): Returns the full row for a bank_id or ledger_id, or {"error": "not found"}.
2. find_by_amount(amount_cents, side): Returns all unmatched rows on that side with that exact amount.
3. sum_items(item_ids): Returns the exact integer-cents sum of those ids (error if any id does not exist).
4. submit_reconciliation: Final submission tool conforming to the reconciliation output schema.
"""

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union


# ==============================================================================
# ANTHROPIC TOOL SCHEMAS
# ==============================================================================

GET_ITEM_SCHEMA: Dict[str, Any] = {
    "name": "get_item",
    "description": "Look up and return the complete transaction row for a given bank_id or ledger_id. Returns an error if not found.",
    "input_schema": {
        "type": "object",
        "properties": {
            "item_id": {
                "type": "string",
                "description": "The transaction ID to look up (e.g. 'BNK-1001' or 'GL-2001').",
            }
        },
        "required": ["item_id"],
    },
}

FIND_BY_AMOUNT_SCHEMA: Dict[str, Any] = {
    "name": "find_by_amount",
    "description": "Find all currently unmatched transactions on the specified side ('bank' or 'ledger') having an exact integer-cents amount.",
    "input_schema": {
        "type": "object",
        "properties": {
            "amount_cents": {
                "type": "integer",
                "description": "The exact transaction amount in integer cents.",
            },
            "side": {
                "type": "string",
                "enum": ["bank", "ledger"],
                "description": "The side to search ('bank' or 'ledger').",
            },
        },
        "required": ["amount_cents", "side"],
    },
}

SUM_ITEMS_SCHEMA: Dict[str, Any] = {
    "name": "sum_items",
    "description": "Compute the exact integer-cents sum of a list of transaction IDs (bank or ledger). Returns an error if any ID does not exist.",
    "input_schema": {
        "type": "object",
        "properties": {
            "item_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of transaction IDs to sum.",
            }
        },
        "required": ["item_ids"],
    },
}

SUBMIT_RECONCILIATION_SCHEMA: Dict[str, Any] = {
    "name": "submit_reconciliation",
    "description": "Submit the completed bank reconciliation result. This concludes the reconciliation run.",
    "input_schema": {
        "type": "object",
        "properties": {
            "matches": {
                "type": "array",
                "description": "Matched groups between bank and ledger.",
                "items": {
                    "type": "object",
                    "properties": {
                        "bank_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of bank transaction IDs.",
                        },
                        "ledger_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of general ledger transaction IDs.",
                        },
                        "confidence": {
                            "type": "number",
                            "description": "Confidence score between 0.0 and 1.0.",
                        },
                        "reason": {
                            "type": "string",
                            "description": "Explanation of why these transactions match.",
                        },
                    },
                    "required": ["bank_ids", "ledger_ids"],
                },
            },
            "reconciling_items": {
                "type": "array",
                "description": "Items causing variance between bank and book.",
                "items": {
                    "type": "object",
                    "properties": {
                        "item_id": {"type": "string"},
                        "side": {"type": "string", "enum": ["bank", "ledger"]},
                        "category": {
                            "type": "string",
                            "enum": [
                                "outstanding_check",
                                "deposit_in_transit",
                                "bank_fee_unbooked",
                                "interest_unbooked",
                                "nsf_return",
                                "duplicate_ledger",
                                "transposition_error",
                                "sign_error",
                                "prior_period_item",
                            ],
                        },
                        "amount_cents": {"type": "integer"},
                        "reason": {"type": "string"},
                    },
                    "required": ["item_id", "side", "category", "amount_cents"],
                },
            },
            "flagged_for_human": {
                "type": "array",
                "description": "Items requiring human investigation.",
                "items": {
                    "type": "object",
                    "properties": {
                        "ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "reason": {"type": "string"},
                    },
                    "required": ["ids", "reason"],
                },
            },
            "proposed_journal_entries": {
                "type": "array",
                "description": "Draft journal entries for unbooked items.",
                "items": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string"},
                        "lines": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "account": {"type": "string"},
                                    "debit_cents": {"type": "integer"},
                                    "credit_cents": {"type": "integer"},
                                },
                                "required": ["account", "debit_cents", "credit_cents"],
                            },
                        },
                        "status": {"type": "string", "enum": ["pending_approval"]},
                    },
                    "required": ["description", "lines", "status"],
                },
            },
            "tie_out": {
                "type": "object",
                "properties": {
                    "adjusted_bank_cents": {"type": ["integer", "null"]},
                    "adjusted_book_cents": {"type": ["integer", "null"]},
                    "difference_cents": {"type": ["integer", "null"]},
                    "can_prove": {"type": "boolean"},
                },
                "required": ["can_prove"],
            },
            "memo": {"type": "string", "description": "Summary memo explaining reconciliation outcome."},
        },
        "required": [
            "matches",
            "reconciling_items",
            "flagged_for_human",
            "proposed_journal_entries",
            "tie_out",
            "memo",
        ],
    },
}

ALL_TOOLS: List[Dict[str, Any]] = [
    GET_ITEM_SCHEMA,
    FIND_BY_AMOUNT_SCHEMA,
    SUM_ITEMS_SCHEMA,
    SUBMIT_RECONCILIATION_SCHEMA,
]


# ==============================================================================
# TOOL IMPLEMENTATION & CONTEXT
# ==============================================================================

class ReconciliationToolbox:
    """Manages transaction data for a single reconciliation variant and executes tools."""

    def __init__(
        self,
        bank_data: Union[str, Path, List[Dict[str, Any]]],
        ledger_data: Union[str, Path, List[Dict[str, Any]]],
        unmatched_bank_ids: Optional[Set[str]] = None,
        unmatched_ledger_ids: Optional[Set[str]] = None,
    ):
        # 1. Load Bank Data
        self.bank_rows: List[Dict[str, Any]] = []
        if isinstance(bank_data, (str, Path)):
            bank_path = Path(bank_data)
            if bank_path.is_file():
                with open(bank_path, "r", encoding="utf-8") as f:
                    self.bank_rows = list(csv.DictReader(f))
        elif isinstance(bank_data, list):
            self.bank_rows = [dict(r) for r in bank_data]

        for r in self.bank_rows:
            r["amount_cents"] = int(r["amount_cents"])
            if "running_balance_cents" in r and r["running_balance_cents"]:
                r["running_balance_cents"] = int(r["running_balance_cents"])

        self.bank_by_id: Dict[str, Dict[str, Any]] = {
            r["bank_id"]: r for r in self.bank_rows if "bank_id" in r
        }

        # 2. Load Ledger Data
        self.ledger_rows: List[Dict[str, Any]] = []
        if isinstance(ledger_data, (str, Path)):
            ledger_path = Path(ledger_data)
            if ledger_path.is_file():
                with open(ledger_path, "r", encoding="utf-8") as f:
                    self.ledger_rows = list(csv.DictReader(f))
        elif isinstance(ledger_data, list):
            self.ledger_rows = [dict(r) for r in ledger_data]

        for r in self.ledger_rows:
            r["amount_cents"] = int(r["amount_cents"])

        self.ledger_by_id: Dict[str, Dict[str, Any]] = {
            r["ledger_id"]: r for r in self.ledger_rows if "ledger_id" in r
        }

        # 3. Unmatched Trackers
        self.unmatched_bank_ids: Set[str] = (
            set(unmatched_bank_ids)
            if unmatched_bank_ids is not None
            else set(self.bank_by_id.keys())
        )
        self.unmatched_ledger_ids: Set[str] = (
            set(unmatched_ledger_ids)
            if unmatched_ledger_ids is not None
            else set(self.ledger_by_id.keys())
        )

    def get_item(self, item_id: str) -> Dict[str, Any]:
        """Return the full row for a bank_id or ledger_id, or {"error": "not found"}."""
        item_id_clean = str(item_id).strip()
        if item_id_clean in self.bank_by_id:
            row = dict(self.bank_by_id[item_id_clean])
            row["side"] = "bank"
            return row
        if item_id_clean in self.ledger_by_id:
            row = dict(self.ledger_by_id[item_id_clean])
            row["side"] = "ledger"
            return row
        return {"error": "not found"}

    def find_by_amount(self, amount_cents: int, side: str) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        """Return all unmatched rows on that side with that exact amount."""
        side_clean = str(side).strip().lower()
        if side_clean == "bank":
            matches = [
                dict(row)
                for b_id, row in self.bank_by_id.items()
                if b_id in self.unmatched_bank_ids and int(row["amount_cents"]) == int(amount_cents)
            ]
            return matches
        elif side_clean == "ledger":
            matches = [
                dict(row)
                for l_id, row in self.ledger_by_id.items()
                if l_id in self.unmatched_ledger_ids and int(row["amount_cents"]) == int(amount_cents)
            ]
            return matches
        else:
            return {"error": f"Invalid side '{side}'. Must be 'bank' or 'ledger'."}

    def sum_items(self, item_ids: List[str]) -> Dict[str, Any]:
        """Return the exact integer-cents sum of those ids (error if any id does not exist)."""
        if not isinstance(item_ids, (list, tuple)):
            return {"error": "item_ids must be a list of strings."}

        total_cents = 0
        resolved_items = []
        for iid in item_ids:
            item_str = str(iid).strip()
            item = self.get_item(item_str)
            if "error" in item:
                return {"error": f"Item '{item_str}' does not exist."}
            total_cents += int(item["amount_cents"])
            resolved_items.append({"id": item_str, "amount_cents": int(item["amount_cents"])})

        return {
            "sum_cents": total_cents,
            "count": len(item_ids),
            "items": resolved_items,
        }

    def execute(self, tool_name: str, tool_input: Dict[str, Any]) -> Any:
        """Dispatch a tool call by name with inputs."""
        if tool_name == "get_item":
            return self.get_item(tool_input.get("item_id", ""))
        elif tool_name == "find_by_amount":
            return self.find_by_amount(
                amount_cents=tool_input.get("amount_cents", 0),
                side=tool_input.get("side", ""),
            )
        elif tool_name == "sum_items":
            return self.sum_items(tool_input.get("item_ids", []))
        elif tool_name == "submit_reconciliation":
            return {"status": "submitted", "received": True}
        else:
            return {"error": f"Unknown tool: '{tool_name}'"}


# Standalone function helpers for direct invocation
def get_item(toolbox: ReconciliationToolbox, item_id: str) -> Dict[str, Any]:
    return toolbox.get_item(item_id)


def find_by_amount(toolbox: ReconciliationToolbox, amount_cents: int, side: str) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
    return toolbox.find_by_amount(amount_cents, side)


def sum_items(toolbox: ReconciliationToolbox, item_ids: List[str]) -> Dict[str, Any]:
    return toolbox.sum_items(item_ids)
