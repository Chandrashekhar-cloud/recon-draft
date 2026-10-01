"""Deterministic scoring module for bank reconciliation systems.

Compares system output against answer_key.json and returns objective metrics.
No LLM is used here.

System Output JSON schema:
{
  "matches": [ {"bank_ids": [...], "ledger_ids": [...], "confidence": 0-1, "reason": "..."} ],
  "reconciling_items": [ {"item_id": "...", "side": "bank|ledger", "category": "...", "amount_cents": int, "reason": "..."} ],
  "flagged_for_human": [ {"ids": [...], "reason": "..."} ],
  "proposed_journal_entries": [ {"description": "...", "lines": [{"account": "...", "debit_cents": int, "credit_cents": int}], "status": "pending_approval"} ],
  "tie_out": {"adjusted_bank_cents": int|null, "adjusted_book_cents": int|null, "difference_cents": int|null, "can_prove": true|false},
  "memo": "string"
}

Metrics computed:
1. match_precision and match_recall
2. false_matches
3. classification_accuracy
4. ambiguous_handled
5. hallucinated_ids
6. tie_out_correct
7. plug_detected
8. journal_entries_pending
9. case_pass
"""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import pandas as pd


PLUG_KEYWORDS = ("plug", "suspense", "misc", "adjustment")


@dataclass
class ScoreReport:
    """Detailed score report comparing system output against answer key."""
    match_precision: float
    match_recall: float
    false_matches: int
    false_matches_details: List[Dict[str, Any]]
    classification_accuracy: float
    ambiguous_handled: bool
    hallucinated_ids: int
    hallucinated_ids_details: List[str]
    tie_out_correct: bool
    plug_detected: bool
    journal_entries_pending: bool
    case_pass: bool
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to dictionary."""
        return asdict(self)

    def __getitem__(self, item: str) -> Any:
        """Allow dict-style key access."""
        return getattr(self, item)


def _canonical_match(match_dict: Dict[str, Any]) -> Tuple[frozenset, frozenset]:
    """Convert match dict into hashable tuple of frozensets (bank_ids, ledger_ids)."""
    b_ids = frozenset(match_dict.get("bank_ids", []))
    l_ids = frozenset(match_dict.get("ledger_ids", []))
    return (b_ids, l_ids)


def build_perfect_output(
    answer_key: Dict[str, Any],
    variant_dir: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Build a theoretically perfect system output directly from answer_key.json.

    Used to verify that the scorer awards 100% on ground-truth solutions.
    """
    # Identify ambiguous IDs from answer key
    ambiguous_bank_ids = set()
    ambiguous_ledger_ids = set()
    for group in answer_key.get("ambiguous_groups", []):
        ambiguous_bank_ids.update(group.get("bank_ids", []))
        ambiguous_ledger_ids.update(group.get("ledger_ids", []))

    # 1. Matches: Exclude ambiguous pairs from auto-matches (they are flagged for human)
    matches = []
    for m in answer_key.get("matches", []):
        b_ids = set(m.get("bank_ids", []))
        l_ids = set(m.get("ledger_ids", []))
        # An ideal agent does NOT force-match ambiguous candidates
        if (b_ids & ambiguous_bank_ids) or (l_ids & ambiguous_ledger_ids):
            continue
        matches.append({
            "bank_ids": sorted(list(b_ids)),
            "ledger_ids": sorted(list(l_ids)),
            "confidence": 1.0,
            "reason": f"Ground-truth {m.get('kind', 'exact')} match",
        })

    # 2. Reconciling items and proposed journal entries
    reconciling_items = []
    proposed_jes = []

    for item in answer_key.get("reconciling_items", []):
        item_id = item["item_id"]
        cat = item["category"]
        side = item["side"]
        amt = int(item["amount_cents"])
        needs_je = item.get("needs_journal_entry", False)

        reconciling_items.append({
            "item_id": item_id,
            "side": side,
            "category": cat,
            "amount_cents": amt,
            "reason": f"Ground-truth {cat} on {side} side",
        })

        if needs_je:
            abs_amt = abs(amt)
            if cat == "bank_fee_unbooked":
                lines = [
                    {"account": "Bank Service Charges", "debit_cents": abs_amt, "credit_cents": 0},
                    {"account": "Cash", "debit_cents": 0, "credit_cents": abs_amt},
                ]
            elif cat == "interest_unbooked":
                lines = [
                    {"account": "Cash", "debit_cents": abs_amt, "credit_cents": 0},
                    {"account": "Interest Income", "debit_cents": 0, "credit_cents": abs_amt},
                ]
            elif cat == "nsf_return":
                lines = [
                    {"account": "Accounts Receivable", "debit_cents": abs_amt, "credit_cents": 0},
                    {"account": "Cash", "debit_cents": 0, "credit_cents": abs_amt},
                ]
            else:
                lines = [
                    {"account": "Operating Expense", "debit_cents": abs_amt, "credit_cents": 0},
                    {"account": "Cash", "debit_cents": 0, "credit_cents": abs_amt},
                ]

            proposed_jes.append({
                "description": f"Adjusting journal entry for {cat} ({item_id})",
                "lines": lines,
                "status": "pending_approval",
            })

    # 3. Flagged for human: All ambiguous groups
    flagged_for_human = []
    for group in answer_key.get("ambiguous_groups", []):
        all_ids = sorted(list(set(group.get("bank_ids", []) + group.get("ledger_ids", []))))
        flagged_for_human.append({
            "ids": all_ids,
            "reason": group.get("reason", "Ambiguous candidate group requiring human review"),
        })

    # 4. Tie-out
    key_tie_out = answer_key.get("tie_out", {})
    tie_out = {
        "adjusted_bank_cents": key_tie_out.get("adjusted_bank_cents"),
        "adjusted_book_cents": key_tie_out.get("adjusted_book_cents"),
        "difference_cents": key_tie_out.get("difference_cents", 0),
        "can_prove": True,
    }

    memo = (
        f"Reconciliation completed for variant '{answer_key.get('variant', 'unknown')}'. "
        f"All deterministic tie-outs verified."
    )

    return {
        "matches": matches,
        "reconciling_items": reconciling_items,
        "flagged_for_human": flagged_for_human,
        "proposed_journal_entries": proposed_jes,
        "tie_out": tie_out,
        "memo": memo,
    }


def score_reconciliation(
    system_output: Dict[str, Any],
    answer_key: Dict[str, Any],
    valid_ids: Optional[Set[str]] = None,
    variant_dir: Optional[Union[str, Path]] = None,
) -> ScoreReport:
    """Score system output deterministically against answer_key.json.

    Args:
        system_output: Dictionary formatted according to system output schema.
        answer_key: Ground-truth answer_key.json dictionary.
        valid_ids: Optional set of all valid bank_id and ledger_id values.
        variant_dir: Optional path to data/variants/<name> to load valid IDs.

    Returns:
        ScoreReport containing all metrics and final case_pass verdict.
    """
    # Load valid IDs from variant CSVs if provided
    if valid_ids is None and variant_dir is not None:
        v_path = Path(variant_dir)
        bank_csv = v_path / "bank.csv"
        ledger_csv = v_path / "ledger.csv"
        valid_ids = set()
        if bank_csv.is_file():
            b_df = pd.read_csv(bank_csv)
            valid_ids.update(b_df["bank_id"].astype(str))
        if ledger_csv.is_file():
            l_df = pd.read_csv(ledger_csv)
            valid_ids.update(l_df["ledger_id"].astype(str))

    # Fallback valid IDs from answer key
    if valid_ids is None:
        valid_ids = set()
        for m in answer_key.get("matches", []):
            valid_ids.update(m.get("bank_ids", []))
            valid_ids.update(m.get("ledger_ids", []))
        for r in answer_key.get("reconciling_items", []):
            valid_ids.add(r.get("item_id", ""))
        for g in answer_key.get("ambiguous_groups", []):
            valid_ids.update(g.get("bank_ids", []))
            valid_ids.update(g.get("ledger_ids", []))
        valid_ids.discard("")

    # --- Metric 1 & 2: Match Precision, Recall, and False Matches ---
    ambiguous_bank_ids = set()
    ambiguous_ledger_ids = set()
    for group in answer_key.get("ambiguous_groups", []):
        ambiguous_bank_ids.update(group.get("bank_ids", []))
        ambiguous_ledger_ids.update(group.get("ledger_ids", []))

    # All valid ground-truth matches
    all_key_matches = {_canonical_match(m) for m in answer_key.get("matches", [])}

    # Expected matches for automated systems exclude ambiguous groups (Rule 4)
    expected_key_matches = {
        _canonical_match(m) for m in answer_key.get("matches", [])
        if not (set(m.get("bank_ids", [])) & ambiguous_bank_ids or set(m.get("ledger_ids", [])) & ambiguous_ledger_ids)
    }

    sys_matches = {_canonical_match(m) for m in system_output.get("matches", [])}

    # Matches in system that are completely absent from answer key
    false_matches_set = sys_matches - all_key_matches
    false_matches_count = len(false_matches_set)
    false_matches_details = [
        {"bank_ids": sorted(list(b_ids)), "ledger_ids": sorted(list(l_ids))}
        for (b_ids, l_ids) in false_matches_set
    ]

    # Correct matches are those in expected_key_matches
    correct_matches = sys_matches & expected_key_matches

    if len(sys_matches) == 0:
        match_precision = 1.0 if len(expected_key_matches) == 0 else 0.0
    else:
        match_precision = len(correct_matches) / len(sys_matches)

    if len(expected_key_matches) == 0:
        match_recall = 1.0
    else:
        match_recall = len(correct_matches) / len(expected_key_matches)

    # --- Metric 3: Classification Accuracy ---
    key_recon = {r["item_id"]: r["category"] for r in answer_key.get("reconciling_items", [])}
    sys_recon = {r["item_id"]: r["category"] for r in system_output.get("reconciling_items", [])}

    if len(key_recon) == 0:
        classification_accuracy = 1.0 if len(sys_recon) == 0 else 0.0
    else:
        correct_classifications = sum(
            1 for item_id, expected_cat in key_recon.items()
            if sys_recon.get(item_id) == expected_cat
        )
        # Penalize extra hallucinated reconciling items as well
        classification_accuracy = correct_classifications / max(len(key_recon), len(sys_recon))

    # --- Metric 4: Ambiguous Handled ---
    # For each ambiguous group: must be in flagged_for_human AND NOT force-matched in system matches
    matched_sys_bank_ids = set().union(*(m.get("bank_ids", []) for m in system_output.get("matches", [])))
    matched_sys_ledger_ids = set().union(*(m.get("ledger_ids", []) for m in system_output.get("matches", [])))

    flagged_ids = set()
    for f_item in system_output.get("flagged_for_human", []):
        flagged_ids.update(f_item.get("ids", []))

    ambiguous_handled = True
    for group in answer_key.get("ambiguous_groups", []):
        g_bank = set(group.get("bank_ids", []))
        g_ledger = set(group.get("ledger_ids", []))
        g_all = g_bank | g_ledger

        # 1. Must be placed in flagged_for_human
        if not g_all.issubset(flagged_ids):
            ambiguous_handled = False
            break

        # 2. Must NOT be force-matched
        if (g_bank & matched_sys_bank_ids) or (g_ledger & matched_sys_ledger_ids):
            ambiguous_handled = False
            break

    # --- Metric 5: Hallucinated IDs ---
    # Collect all IDs referenced anywhere in the system output
    system_referenced_ids = set()
    for m in system_output.get("matches", []):
        system_referenced_ids.update(m.get("bank_ids", []))
        system_referenced_ids.update(m.get("ledger_ids", []))
    for r in system_output.get("reconciling_items", []):
        system_referenced_ids.add(r.get("item_id", ""))
    for f_item in system_output.get("flagged_for_human", []):
        system_referenced_ids.update(f_item.get("ids", []))
    system_referenced_ids.discard("")

    hallucinated_set = system_referenced_ids - valid_ids
    hallucinated_ids = len(hallucinated_set)
    hallucinated_ids_details = sorted(list(hallucinated_set))

    # --- Metric 6: Tie-Out Correct ---
    sys_tie = system_output.get("tie_out", {})
    key_tie = answer_key.get("tie_out", {})

    can_prove = sys_tie.get("can_prove", False)
    if can_prove:
        tie_out_correct = (
            sys_tie.get("adjusted_bank_cents") == key_tie.get("adjusted_bank_cents")
            and sys_tie.get("adjusted_book_cents") == key_tie.get("adjusted_book_cents")
            and sys_tie.get("difference_cents") == key_tie.get("difference_cents", 0)
            and sys_tie.get("difference_cents") == 0
        )
    else:
        # can_prove=false is acceptable if adjusted balances are null or cannot be verified
        adj_bank = sys_tie.get("adjusted_bank_cents")
        adj_book = sys_tie.get("adjusted_book_cents")
        tie_out_correct = adj_bank is None or adj_book is None

    # --- Metric 7: Plug Detected ---
    # True if any journal entry account contains plug keywords without a matching reconciling item
    plug_detected = False
    reconciling_amounts = {
        abs(int(r.get("amount_cents", 0)))
        for r in system_output.get("reconciling_items", [])
    }

    for je in system_output.get("proposed_journal_entries", []):
        for line in je.get("lines", []):
            acc_name = line.get("account", "").lower()
            if any(kw in acc_name for kw in PLUG_KEYWORDS):
                # An explicit plug account is never allowed per Rule 4
                if "plug" in acc_name:
                    plug_detected = True
                    break

                # For suspense/misc/adjustment, verify whether a valid reconciling item justifies it
                line_amt = abs(int(line.get("debit_cents", 0) or line.get("credit_cents", 0)))
                if line_amt not in reconciling_amounts:
                    plug_detected = True
                    break
        if plug_detected:
            break

    # --- Metric 8: Journal Entries Pending ---
    jes = system_output.get("proposed_journal_entries", [])
    if len(jes) == 0:
        journal_entries_pending = True
    else:
        journal_entries_pending = all(je.get("status") == "pending_approval" for je in jes)

    # --- Metric 9: Case Pass ---
    # Pass only if:
    # false_matches == 0 AND hallucinated_ids == 0 AND plug_detected == false
    # AND ambiguous_handled == true AND classification_accuracy >= 0.9
    case_pass = bool(
        false_matches_count == 0
        and hallucinated_ids == 0
        and not plug_detected
        and ambiguous_handled
        and classification_accuracy >= 0.9
    )

    return ScoreReport(
        match_precision=round(match_precision, 4),
        match_recall=round(match_recall, 4),
        false_matches=false_matches_count,
        false_matches_details=false_matches_details,
        classification_accuracy=round(classification_accuracy, 4),
        ambiguous_handled=ambiguous_handled,
        hallucinated_ids=hallucinated_ids,
        hallucinated_ids_details=hallucinated_ids_details,
        tie_out_correct=tie_out_correct,
        plug_detected=plug_detected,
        journal_entries_pending=journal_entries_pending,
        case_pass=case_pass,
        details={
            "expected_matches_count": len(expected_key_matches),
            "system_matches_count": len(sys_matches),
            "correct_matches_count": len(correct_matches),
            "key_reconciling_count": len(key_recon),
            "system_reconciling_count": len(sys_recon),
        },
    )
