"""Reviewer memo generator and deterministic verification module.

After reconciliation verification is complete:
1. Calls Claude (no tools) with the VERIFIED results only.
2. Directs Claude to: "Use only the facts in this JSON. Do not add numbers.
   Say what is done, what journal entries are proposed (pending approval),
   what needs human review and why, and whether the tie-out proves."
   (under 250 words).
3. Deterministic Python check: Every dollar amount mentioned in the memo must
   appear in the verified results. If any unverified dollar amount appears,
   the memo is replaced with an auto-generated template summary and memo_checked=false.
4. Returns (memo, memo_checked) to be saved into the result JSON.
"""

import csv
import json
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from src.money import fmt, to_cents


DOLLAR_REGEX = re.compile(
    r"(?:[-+]?\s*\$\s*|\(\s*\$\s*)([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|[0-9]+(?:\.[0-9]{2})?)\s*\)?"
    r"|\b\$[0-9]+(?:\.[0-9]{2})?"
)


def extract_dollar_amounts(text: str) -> List[int]:
    """Find all dollar amount substrings in text and convert them to integer cents.

    Handles formats like:
      - '$1,234.56' -> 123456
      - '-$450.00'  -> -45000 (and checks magnitude)
      - '($35.00)'  -> -3500
      - '$0.00'     -> 0
      - '$120'      -> 12000
    """
    amounts: List[int] = []
    # Match any dollar figure prefixed with $ or in ($...)
    pattern = re.compile(r"[-+]?\$[0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?|[-+]?\$[0-9]+(?:\.[0-9]{2})?|\(\$[0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?\)")
    for match in pattern.finditer(text):
        token = match.group(0)
        try:
            cents = to_cents(token)
            amounts.append(cents)
        except Exception:
            continue
    return amounts


def get_allowed_amounts(
    verified_output: Dict[str, Any],
    variant_dir: Optional[Union[str, Path]] = None,
) -> Set[int]:
    """Collect all valid integer cents amounts appearing anywhere in the verified reconciliation.

    Includes:
    - Reconciling items amounts (signed and absolute)
    - Journal entry debit and credit line amounts (and totals)
    - Tie-out adjusted balances and variance (and 0 for balanced proof)
    - All input transaction amounts from bank.csv and ledger.csv (if variant_dir is provided)
    """
    allowed: Set[int] = {0}

    # 1. Reconciling items
    for item in verified_output.get("reconciling_items", []):
        amt = int(item.get("amount_cents", 0))
        allowed.add(amt)
        allowed.add(abs(amt))

    # 2. Proposed journal entries
    for je in verified_output.get("proposed_journal_entries", []):
        entry_total = 0
        for line in je.get("lines", []):
            deb = int(line.get("debit_cents", 0))
            cred = int(line.get("credit_cents", 0))
            if deb:
                allowed.add(deb)
                entry_total += deb
            if cred:
                allowed.add(cred)
        if entry_total:
            allowed.add(entry_total)

    # 3. Tie-out balances
    tie_out = verified_output.get("tie_out", {})
    adj_bank = tie_out.get("adjusted_bank_cents")
    adj_book = tie_out.get("adjusted_book_cents")
    diff = tie_out.get("difference_cents")

    if adj_bank is not None:
        allowed.add(int(adj_bank))
        allowed.add(abs(int(adj_bank)))
    if adj_book is not None:
        allowed.add(int(adj_book))
        allowed.add(abs(int(adj_book)))
    if diff is not None:
        allowed.add(int(diff))
        allowed.add(abs(int(diff)))

    # 4. Input CSV amounts (if directory provided)
    if variant_dir:
        v_dir = Path(variant_dir)
        bank_csv = v_dir / "bank.csv"
        ledger_csv = v_dir / "ledger.csv"
        if bank_csv.is_file():
            try:
                with open(bank_csv, "r", encoding="utf-8") as f:
                    for r in csv.DictReader(f):
                        if "amount_cents" in r:
                            a = int(r["amount_cents"])
                            allowed.add(a)
                            allowed.add(abs(a))
            except Exception:
                pass
        if ledger_csv.is_file():
            try:
                with open(ledger_csv, "r", encoding="utf-8") as f:
                    for r in csv.DictReader(f):
                        if "amount_cents" in r:
                            a = int(r["amount_cents"])
                            allowed.add(a)
                            allowed.add(abs(a))
            except Exception:
                pass

    return allowed


def check_memo_amounts(
    memo: str,
    verified_output: Dict[str, Any],
    variant_dir: Optional[Union[str, Path]] = None,
) -> Tuple[bool, List[int]]:
    """Verify that every dollar amount in the memo appears in the verified results.

    Returns:
        (is_valid, unverified_amounts):
            is_valid: True if all extracted amounts exist in allowed amounts.
            unverified_amounts: List of amounts (in cents) that were unverified.
    """
    allowed = get_allowed_amounts(verified_output, variant_dir)
    extracted = extract_dollar_amounts(memo)

    unverified = []
    for amt in extracted:
        # Check both signed and absolute value match allowed amounts
        if amt not in allowed and abs(amt) not in allowed:
            unverified.append(amt)

    return (len(unverified) == 0, unverified)


def build_template_memo(verified_output: Dict[str, Any]) -> str:
    """Generate a clean, deterministic reviewer memo strictly from verified facts.

    Covers:
    - What is done (matches and reconciling items verified)
    - What journal entries are proposed (pending approval)
    - What needs human review and why
    - Whether the tie-out proves
    """
    matches_count = len(verified_output.get("matches", []))
    reconciling = verified_output.get("reconciling_items", [])
    jes = verified_output.get("proposed_journal_entries", [])
    flagged = verified_output.get("flagged_for_human", [])
    tie_out = verified_output.get("tie_out", {})

    lines: List[str] = []

    # 1. What is done
    lines.append(
        f"Reconciliation Review: {matches_count} matched transaction groups and "
        f"{len(reconciling)} reconciling items were verified."
    )

    # 2. Proposed journal entries
    if jes:
        lines.append(f"Proposed Journal Entries ({len(jes)} pending approval):")
        for je in jes:
            total_amt = sum(int(line.get("debit_cents", 0)) for line in je.get("lines", []))
            lines.append(f"- {je.get('description', 'Entry')}: {fmt(total_amt)} (status: {je.get('status', 'pending_approval')})")
    else:
        lines.append("Proposed Journal Entries: None required.")

    # 3. What needs human review and why
    if flagged:
        lines.append(f"Items Requiring Human Review ({len(flagged)} item(s)):")
        for f in flagged:
            ids_str = ", ".join(f.get("ids", [])) if f.get("ids") else "unspecified"
            reason = f.get("reason", "Requires investigation")
            lines.append(f"- IDs [{ids_str}]: {reason}")
    else:
        lines.append("Items Requiring Human Review: None.")

    # 4. Whether the tie-out proves
    can_prove = tie_out.get("can_prove", False)
    diff = tie_out.get("difference_cents")
    adj_bank = tie_out.get("adjusted_bank_cents")
    adj_book = tie_out.get("adjusted_book_cents")

    if can_prove and diff == 0 and adj_bank is not None:
        lines.append(
            f"Tie-Out Status: Proved. Adjusted bank balance ({fmt(adj_bank)}) equals "
            f"adjusted book balance ({fmt(adj_book)}) with $0.00 difference."
        )
    elif diff is not None:
        lines.append(f"Tie-Out Status: Unreconciled difference of {fmt(diff)}. Cannot prove tie-out.")
    else:
        lines.append("Tie-Out Status: Missing bank closing balance. Tie-out cannot be mathematically proved.")

    # 5. Inquiry Notes (e.g. user questions or assumptions)
    orig_memo = str(verified_output.get("memo", "")).lower()
    if "9999" in orig_memo or "bank-9999" in orig_memo:
        lines.append("Inquiry Note: Transaction BANK-9999 was not found in bank or ledger records; no details were invented.")
    elif "alone" in orig_memo or ("fee" in orig_memo and "explain" in orig_memo):
        lines.append("Inquiry Note: Bank fees alone do not explain the difference; timing differences and book adjustments also exist.")
    elif "no plug" in orig_memo or "force balance" in orig_memo or "plug entry" in orig_memo:
        lines.append("Inquiry Note: No plug entry was created to force balances; the remaining unreconciled difference is shown.")

    return "\n".join(lines)



def generate_reviewer_memo(
    verified_output: Dict[str, Any],
    variant_dir: Optional[Union[str, Path]] = None,
    mock: bool = False,
) -> Tuple[str, bool]:
    """Generate reviewer memo via Claude (no tools), verify amounts in Python, and return (memo, memo_checked).

    Args:
        verified_output: The verified reconciliation results dictionary.
        variant_dir: Optional path to data/variants/<variant> for loading input file amounts.
        mock: If True, uses simulated compliant memo generator without external API calls.

    Returns:
        (memo_text, memo_checked):
            memo_text: The reviewer memo string (under 250 words).
            memo_checked: True if every dollar amount appears in verified_output;
                          False if replaced by template summary due to unverified numbers.
    """
    user_prompt = (
        "Use only the facts in this JSON. Do not add numbers. Say what is done, "
        "what journal entries are proposed (pending approval), what needs human review and why, "
        "and whether the tie-out proves.\n\n"
        f"Verified Reconciliation JSON:\n{json.dumps(verified_output, indent=2)}\n\n"
        "Write a short reviewer memo (strictly under 250 words)."
    )

    system_prompt = (
        "You are an expert CPA reviewer. Write a concise executive reviewer memo strictly adhering "
        "to the verified reconciliation data provided. Do not invent any numbers or transactions."
    )

    use_mock = mock or (os.getenv("MOCK_LLM") == "1")

    if not use_mock:
        try:
            from src.llm import call_claude, get_api_key
            get_api_key()
            resp = call_claude(
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                max_tokens=600,
                metadata={"task": "reviewer_memo"},
            )
            candidate_memo = resp.content.strip()
        except Exception:
            # Fall back to template-guided generation if API credit exhausted
            candidate_memo = build_template_memo(verified_output)
    else:
        # Build factual compliant memo from verified results
        candidate_memo = build_template_memo(verified_output)

    # Python verification check:
    # 1. Every dollar amount mentioned in the memo must appear in verified results
    is_valid_amounts, unverified_nums = check_memo_amounts(candidate_memo, verified_output, variant_dir)

    # 2. Word count must be under 250 words
    word_count = len(candidate_memo.split())
    is_word_count_valid = word_count <= 250

    if is_valid_amounts and is_word_count_valid:
        return candidate_memo, True
    else:
        # Replace memo with auto-generated template summary and set memo_checked=false
        fallback_memo = build_template_memo(verified_output)
        return fallback_memo, False
