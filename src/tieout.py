"""Mathematical tie-out calculator for bank reconciliation.

Strictly follows docs/TIEOUT_RULES.md:
  Adjusted bank = bank closing + deposits in transit - outstanding checks (+/- bank errors)
  Adjusted book = book closing - unbooked bank fees - NSF returns + unbooked interest (+/- book errors)
  The two adjusted balances must be equal (difference_cents == 0).

Project Rule 2: Python does all arithmetic, matching of exact items, tie-out math and verification.
The LLM must never compute this.
"""

from typing import Any, Dict, List, Tuple
from src.money import fmt


def calculate_tie_out(
    balances: Dict[str, Any],
    reconciling_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Calculate the tie-out balances and generate a human-readable proof.

    Args:
        balances: Dictionary containing at least:
            - 'bank_closing_cents': ending bank balance in integer cents
            - 'book_closing_cents': ending general ledger cash balance in integer cents
        reconciling_items: List of reconciling items per docs/SCHEMA.md.

    Returns:
        Dict containing:
            - 'adjusted_bank_cents': integer cents
            - 'adjusted_book_cents': integer cents
            - 'difference_cents': integer cents (adjusted_bank - adjusted_book)
            - 'is_tied_out': bool (difference_cents == 0)
            - 'proof': List[str] containing formatted step-by-step tie-out proof lines.
    """
    bank_closing = int(balances["bank_closing_cents"])
    book_closing = int(balances["book_closing_cents"])

    # Group reconciling items by category
    deposits_in_transit: List[Dict[str, Any]] = []
    outstanding_checks: List[Dict[str, Any]] = []
    bank_errors: List[Dict[str, Any]] = []

    unbooked_fees: List[Dict[str, Any]] = []
    nsf_returns: List[Dict[str, Any]] = []
    unbooked_interest: List[Dict[str, Any]] = []
    book_errors: List[Dict[str, Any]] = []

    for item in reconciling_items:
        cat = item.get("category", "")
        side = item.get("side", "")
        amt = int(item.get("amount_cents", 0))

        if side == "ledger" and cat == "deposit_in_transit":
            deposits_in_transit.append(item)
        elif side == "ledger" and cat == "outstanding_check":
            outstanding_checks.append(item)
        elif side == "bank" and cat in ("bank_fee_unbooked",):
            unbooked_fees.append(item)
        elif side == "bank" and cat in ("nsf_return",):
            nsf_returns.append(item)
        elif side == "bank" and cat in ("interest_unbooked",):
            unbooked_interest.append(item)
        elif side == "ledger" and cat in ("transposition_error", "duplicate_ledger", "sign_error"):
            book_errors.append(item)
        elif side == "bank" and cat == "bank_error":
            bank_errors.append(item)
        else:
            raise ValueError(f"Unrecognized reconciling item: category='{cat}', side='{side}'")

    # Sum magnitudes and adjustments
    sum_deposits = sum(abs(int(i["amount_cents"])) for i in deposits_in_transit)
    sum_outstanding = sum(abs(int(i["amount_cents"])) for i in outstanding_checks)
    sum_bank_errors = sum(int(i["amount_cents"]) for i in bank_errors)

    sum_fees = sum(abs(int(i["amount_cents"])) for i in unbooked_fees)
    sum_nsf = sum(abs(int(i["amount_cents"])) for i in nsf_returns)
    sum_interest = sum(abs(int(i["amount_cents"])) for i in unbooked_interest)
    sum_book_errors = sum(int(i["amount_cents"]) for i in book_errors)

    # Standard formulas from docs/TIEOUT_RULES.md
    adjusted_bank = bank_closing + sum_deposits - sum_outstanding + sum_bank_errors
    adjusted_book = book_closing - sum_fees - sum_nsf + sum_interest + sum_book_errors
    difference = adjusted_bank - adjusted_book

    # Construct step-by-step human-readable proof
    proof: List[str] = []
    proof.append("=== BANK RECONCILIATION TIE-OUT PROOF ===")
    proof.append("")
    proof.append("1. BANK SIDE ADJUSTMENTS:")
    proof.append(f"   Bank closing balance:              {fmt(bank_closing):>15}  ({bank_closing:,} cents)")
    proof.append(f"   + Deposits in transit ({len(deposits_in_transit)} item(s)):   {fmt(sum_deposits):>15}  (+{sum_deposits:,} cents)")
    for d in deposits_in_transit:
        proof.append(f"     * [{d['item_id']}] {fmt(abs(int(d['amount_cents'])))}")
    proof.append(f"   - Outstanding checks ({len(outstanding_checks)} item(s)):    {fmt(sum_outstanding):>15}  (-{sum_outstanding:,} cents)")
    for c in outstanding_checks:
        proof.append(f"     * [{c['item_id']}] {fmt(abs(int(c['amount_cents'])))}")
    if bank_errors:
        proof.append(f"   +/- Bank errors ({len(bank_errors)} item(s)):          {fmt(sum_bank_errors):>15}  ({sum_bank_errors:+,} cents)")
        for be in bank_errors:
            proof.append(f"     * [{be['item_id']}] {be['category']}: {fmt(int(be['amount_cents']))}")
    proof.append("   " + "-" * 55)
    proof.append(f"   = Adjusted bank balance:           {fmt(adjusted_bank):>15}  ({adjusted_bank:,} cents)")
    proof.append("")

    proof.append("2. BOOK (LEDGER) SIDE ADJUSTMENTS:")
    proof.append(f"   Book closing balance:              {fmt(book_closing):>15}  ({book_closing:,} cents)")
    proof.append(f"   - Unbooked bank fees ({len(unbooked_fees)} item(s)):    {fmt(sum_fees):>15}  (-{sum_fees:,} cents)")
    for f_item in unbooked_fees:
        proof.append(f"     * [{f_item['item_id']}] {fmt(abs(int(f_item['amount_cents'])))}")
    proof.append(f"   - NSF returned checks ({len(nsf_returns)} item(s)):   {fmt(sum_nsf):>15}  (-{sum_nsf:,} cents)")
    for n in nsf_returns:
        proof.append(f"     * [{n['item_id']}] {fmt(abs(int(n['amount_cents'])))}")
    proof.append(f"   + Unbooked interest ({len(unbooked_interest)} item(s)):     {fmt(sum_interest):>15}  (+{sum_interest:,} cents)")
    for i_item in unbooked_interest:
        proof.append(f"     * [{i_item['item_id']}] {fmt(abs(int(i_item['amount_cents'])))}")
    if book_errors:
        proof.append(f"   +/- Book errors/adjustments ({len(book_errors)} item(s)): {fmt(sum_book_errors):>15}  ({sum_book_errors:+,} cents)")
        for b_err in book_errors:
            proof.append(f"     * [{b_err['item_id']}] {b_err['category']}: {fmt(int(b_err['amount_cents']))}")
    proof.append("   " + "-" * 55)
    proof.append(f"   = Adjusted book balance:           {fmt(adjusted_book):>15}  ({adjusted_book:,} cents)")
    proof.append("")

    proof.append("3. TIE-OUT VERIFICATION:")
    proof.append(f"   Adjusted Bank Balance:             {fmt(adjusted_bank):>15}")
    proof.append(f"   Adjusted Book Balance:             {fmt(adjusted_book):>15}")
    proof.append(f"   Variance / Difference:             {fmt(difference):>15}  ({difference} cents)")
    status_str = "TIED OUT (difference is exactly $0.00)" if difference == 0 else f"UNRECONCILED VARIANCE: {fmt(difference)}"
    proof.append(f"   Status:                            {status_str}")

    return {
        "adjusted_bank_cents": adjusted_bank,
        "adjusted_book_cents": adjusted_book,
        "difference_cents": difference,
        "is_tied_out": difference == 0,
        "proof": proof,
    }


def tie_out(
    balances: Dict[str, Any],
    reconciling_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Convenience alias for calculate_tie_out."""
    return calculate_tie_out(balances, reconciling_items)
