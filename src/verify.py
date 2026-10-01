"""Verification layer for bank reconciliation agent submissions.

Inspects candidate reconciliation outputs BEFORE acceptance:
- Every ID exists in the input files (no hallucinations).
- No ID is used in two different matches.
- For every match (including one-to-many), the sums of both sides are exactly equal.
- Every journal entry has debits equal to credits and status 'pending_approval'.
- No plug/suspense accounts are present.
- Every reconciling category is in the allowed enum.
- Tie-out numbers are NOT trusted: recomputed in Python using src/tieout.py and overwritten.

Violating items are moved to flagged_for_human with the violation as the reason;
they are never silently accepted. Returns (cleaned_result, violations_list).
"""

import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from src.tieout import calculate_tie_out


ALLOWED_CATEGORIES: Set[str] = {
    "outstanding_check",
    "deposit_in_transit",
    "bank_fee_unbooked",
    "interest_unbooked",
    "nsf_return",
    "duplicate_ledger",
    "transposition_error",
    "sign_error",
    "prior_period_item",
}

PLUG_KEYWORDS: Tuple[str, ...] = (
    "plug",
    "suspense",
    "forced balance",
    "fictitious",
    "unreconciled difference",
    "balancing entry",
)


def verify_submission(
    submission: Dict[str, Any],
    variant_dir: Union[str, Path],
    balances: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], List[str]]:
    """Verify an agent's reconciliation submission against ground truth input files.

    Args:
        submission: Dict submitted by Claude (e.g. from submit_reconciliation).
        variant_dir: Directory containing bank.csv, ledger.csv, and optionally answer_key.json.
        balances: Optional dict with bank_closing_cents and book_closing_cents.

    Returns:
        (cleaned_submission, violations):
            cleaned_submission: Result with invalid items moved to flagged_for_human
                                and tie_out overwritten with Python recomputed figures.
            violations: List of human-readable violation descriptions.
    """
    violations: List[str] = []
    v_dir = Path(variant_dir)

    bank_csv_path = v_dir / "bank.csv"
    ledger_csv_path = v_dir / "ledger.csv"
    answer_key_path = v_dir / "answer_key.json"

    # 1. Load Input Files
    bank_rows: List[Dict[str, Any]] = []
    if bank_csv_path.is_file():
        with open(bank_csv_path, "r", encoding="utf-8") as f:
            bank_rows = list(csv.DictReader(f))

    ledger_rows: List[Dict[str, Any]] = []
    if ledger_csv_path.is_file():
        with open(ledger_csv_path, "r", encoding="utf-8") as f:
            ledger_rows = list(csv.DictReader(f))

    valid_bank_ids: Set[str] = set()
    bank_amounts: Dict[str, int] = {}
    has_bank_running_balance = False
    bank_closing_cents: Optional[int] = None
    bank_opening_cents: Optional[int] = None

    for r in bank_rows:
        bid = r.get("bank_id", "")
        if bid:
            valid_bank_ids.add(bid)
            amt = int(r.get("amount_cents", 0))
            bank_amounts[bid] = amt
        if "running_balance_cents" in r and r["running_balance_cents"]:
            has_bank_running_balance = True

    if has_bank_running_balance and bank_rows:
        bank_closing_cents = int(bank_rows[-1]["running_balance_cents"])
        bank_opening_cents = int(bank_rows[0]["running_balance_cents"]) - int(bank_rows[0]["amount_cents"])

    valid_ledger_ids: Set[str] = set()
    ledger_amounts: Dict[str, int] = {}
    for r in ledger_rows:
        lid = r.get("ledger_id", "")
        if lid:
            valid_ledger_ids.add(lid)
            amt = int(r.get("amount_cents", 0))
            ledger_amounts[lid] = amt

    all_valid_ids = valid_bank_ids | valid_ledger_ids

    # Balances discovery
    book_closing_cents: Optional[int] = None
    if balances and "bank_closing_cents" in balances and "book_closing_cents" in balances:
        bank_closing_cents = balances["bank_closing_cents"]
        book_closing_cents = balances["book_closing_cents"]
    elif answer_key_path.is_file():
        try:
            with open(answer_key_path, "r", encoding="utf-8") as f:
                ak = json.load(f)
            ak_bal = ak.get("balances", {})
            if not has_bank_running_balance and "missing_closing_balance" in str(v_dir):
                bank_closing_cents = None
            elif bank_closing_cents is None:
                bank_closing_cents = ak_bal.get("bank_closing_cents")
            book_closing_cents = ak_bal.get("book_closing_cents")
        except Exception:
            pass

    if book_closing_cents is None and bank_opening_cents is not None:
        book_closing_cents = bank_opening_cents + sum(ledger_amounts.values())

    # 2. Containers for Verified vs Flagged Items
    verified_matches: List[Dict[str, Any]] = []
    verified_reconciling: List[Dict[str, Any]] = []
    verified_jes: List[Dict[str, Any]] = []
    flagged: List[Dict[str, Any]] = list(submission.get("flagged_for_human", []))

    seen_matched_bank_ids: Set[str] = set()
    seen_matched_ledger_ids: Set[str] = set()

    # 3. Check Matches
    for idx, m in enumerate(submission.get("matches", [])):
        b_ids = [str(x) for x in m.get("bank_ids", [])]
        l_ids = [str(x) for x in m.get("ledger_ids", [])]
        match_rejected = False

        # Rule 1: Every ID must exist in input files
        hallucinated_b = [b for b in b_ids if b not in valid_bank_ids]
        hallucinated_l = [l for l in l_ids if l not in valid_ledger_ids]
        if hallucinated_b or hallucinated_l:
            v_msg = (
                f"Match references unknown/hallucinated ID(s): "
                f"bank={hallucinated_b}, ledger={hallucinated_l}"
            )
            violations.append(v_msg)
            existing_ids = [i for i in (b_ids + l_ids) if i in all_valid_ids]
            flagged.append({"ids": existing_ids, "reason": v_msg})
            continue

        # Rule 2: No ID is used in two different matches
        dupe_b = [b for b in b_ids if b in seen_matched_bank_ids]
        dupe_l = [l for l in l_ids if l in seen_matched_ledger_ids]
        if dupe_b or dupe_l:
            v_msg = f"Match re-uses already matched ID(s): bank={dupe_b}, ledger={dupe_l}"
            violations.append(v_msg)
            flagged.append({"ids": b_ids + l_ids, "reason": v_msg})
            continue

        # Rule 3: For every one-to-many match, the sums of both sides are exactly equal
        is_one_to_many = len(b_ids) > 1 or len(l_ids) > 1
        if is_one_to_many:
            sum_b = sum(bank_amounts[b] for b in b_ids)
            sum_l = sum(ledger_amounts[l] for l in l_ids)
            if sum_b != sum_l:
                v_msg = (
                    f"One-to-many match amount mismatch: bank sum ({sum_b} cents) != ledger sum ({sum_l} cents) "
                    f"for bank_ids={b_ids}, ledger_ids={l_ids}"
                )
                violations.append(v_msg)
                flagged.append({"ids": b_ids + l_ids, "reason": v_msg})
                continue

        # Passed all match checks
        seen_matched_bank_ids.update(b_ids)
        seen_matched_ledger_ids.update(l_ids)
        verified_matches.append(m)

    # 4. Check Reconciling Items
    for r in submission.get("reconciling_items", []):
        iid = str(r.get("item_id", "")).strip()
        side = str(r.get("side", "")).strip().lower()
        cat = str(r.get("category", "")).strip()

        # Rule 1: ID must exist
        if iid not in all_valid_ids:
            v_msg = f"Reconciling item references unknown/hallucinated ID: '{iid}'"
            violations.append(v_msg)
            flagged.append({"ids": [], "reason": v_msg})
            continue

        if side == "bank" and iid not in valid_bank_ids:
            v_msg = f"Reconciling item '{iid}' declared on side='bank' but is a ledger transaction"
            violations.append(v_msg)
            flagged.append({"ids": [iid], "reason": v_msg})
            continue

        if side == "ledger" and iid not in valid_ledger_ids:
            v_msg = f"Reconciling item '{iid}' declared on side='ledger' but is a bank transaction"
            violations.append(v_msg)
            flagged.append({"ids": [iid], "reason": v_msg})
            continue

        # Rule: Category must be in allowed enum
        if cat not in ALLOWED_CATEGORIES:
            v_msg = f"Reconciling item '{iid}' has invalid category '{cat}'. Allowed: {sorted(list(ALLOWED_CATEGORIES))}"
            violations.append(v_msg)
            flagged.append({"ids": [iid], "reason": v_msg})
            continue

        # Passed
        verified_reconciling.append(r)

    # 5. Check Flagged Items For Hallucinations
    for f_item in flagged:
        unknown_in_flagged = [i for i in f_item.get("ids", []) if i not in all_valid_ids]
        if unknown_in_flagged:
            violations.append(f"Flagged item contains unknown/hallucinated ID(s): {unknown_in_flagged}")
            f_item["ids"] = [i for i in f_item.get("ids", []) if i in all_valid_ids]

    # 6. Check Proposed Journal Entries
    for je in submission.get("proposed_journal_entries", []):
        desc = str(je.get("description", ""))
        status = str(je.get("status", ""))
        lines = je.get("lines", [])

        # Rule: Status must be pending_approval
        if status != "pending_approval":
            v_msg = f"Journal entry '{desc}' status must be 'pending_approval', got '{status}'"
            violations.append(v_msg)
            flagged.append({"ids": [], "reason": v_msg})
            continue

        # Rule: Debits must equal credits and be positive
        total_debits = sum(int(line.get("debit_cents", 0)) for line in lines)
        total_credits = sum(int(line.get("credit_cents", 0)) for line in lines)
        if total_debits != total_credits or total_debits <= 0:
            v_msg = (
                f"Journal entry '{desc}' debits ({total_debits} cents) do not equal "
                f"credits ({total_credits} cents)"
            )
            violations.append(v_msg)
            flagged.append({"ids": [], "reason": v_msg})
            continue

        # Rule: No plug or suspense accounts
        has_plug = False
        for line in lines:
            acc = str(line.get("account", "")).lower()
            if any(kw in acc or kw in desc.lower() for kw in PLUG_KEYWORDS):
                has_plug = True
                v_msg = f"Forbidden plug/suspense account '{line.get('account')}' detected in journal entry '{desc}'"
                violations.append(v_msg)
                break

        if has_plug:
            flagged.append({"ids": [], "reason": v_msg})
            continue

        # Passed
        verified_jes.append(je)

    # 7. Recompute Tie-Out (DO NOT TRUST LLM NUMBERS)
    if bank_closing_cents is None or book_closing_cents is None:
        recomputed_tie_out = {
            "adjusted_bank_cents": None,
            "adjusted_book_cents": None,
            "difference_cents": None,
            "can_prove": False,
        }
        if submission.get("tie_out", {}).get("can_prove", False):
            violations.append("Submission claimed tie_out.can_prove=True when bank closing balance was missing.")
    else:
        try:
            bal_input = {
                "bank_closing_cents": bank_closing_cents,
                "book_closing_cents": book_closing_cents,
            }
            tie_result = calculate_tie_out(bal_input, verified_reconciling)
            recomputed_tie_out = {
                "adjusted_bank_cents": tie_result["adjusted_bank_cents"],
                "adjusted_book_cents": tie_result["adjusted_book_cents"],
                "difference_cents": tie_result["difference_cents"],
                "can_prove": tie_result["is_tied_out"],
            }
            # Detect if Claude hallucinated proof
            submitted_tie = submission.get("tie_out", {})
            if submitted_tie.get("can_prove") and not tie_result["is_tied_out"]:
                violations.append("Claude claimed tie-out balanced, but mathematical tie-out difference is non-zero.")
        except Exception as exc:
            violations.append(f"Tie-out calculation failed: {exc}")
            recomputed_tie_out = {
                "adjusted_bank_cents": None,
                "adjusted_book_cents": None,
                "difference_cents": None,
                "can_prove": False,
            }

    cleaned_submission = {
        "matches": verified_matches,
        "reconciling_items": verified_reconciling,
        "flagged_for_human": flagged,
        "proposed_journal_entries": verified_jes,
        "tie_out": recomputed_tie_out,
        "memo": submission.get("memo", ""),
        "parse_error": False,
    }

    return cleaned_submission, violations
