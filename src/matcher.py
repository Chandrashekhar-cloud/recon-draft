"""Deterministic pre-matcher for bank reconciliation using pandas.

Rules:
1. A bank row and a ledger row match "exactly" only if:
   - amounts are equal (amount_cents matches exactly)
   - AND dates are within 3 days (abs((bank_date - ledger_date).days) <= 3)
   - AND the match is UNIQUE (only one candidate on each side).
2. If more than one candidate exists for the same amount and date window,
   do NOT guess. Put all of them in an 'ambiguous_candidates' list.
3. Returns:
   - matched_pairs (with a reason string)
   - unmatched_bank rows
   - unmatched_ledger rows
   - ambiguous_candidates
4. Never modifies the input data. Never uses floats for money arithmetic.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import pandas as pd

from src.money import fmt


@dataclass
class MatchResult:
    """Structured result of deterministic pre-matching."""
    matched_pairs: List[Dict[str, Any]] = field(default_factory=list)
    unmatched_bank: List[Dict[str, Any]] = field(default_factory=list)
    unmatched_ledger: List[Dict[str, Any]] = field(default_factory=list)
    ambiguous_candidates: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to a standard dictionary."""
        return {
            "matched_pairs": self.matched_pairs,
            "unmatched_bank": self.unmatched_bank,
            "unmatched_ledger": self.unmatched_ledger,
            "ambiguous_candidates": self.ambiguous_candidates,
        }

    def __getitem__(self, item: str) -> Any:
        """Allow dict-style key access."""
        return getattr(self, item)


def match_transactions(
    bank_data: Union[pd.DataFrame, List[Dict[str, Any]], str, Path],
    ledger_data: Union[pd.DataFrame, List[Dict[str, Any]], str, Path],
) -> MatchResult:
    """Perform deterministic pre-matching between bank and ledger transactions.

    Args:
        bank_data: DataFrame, list of row dicts, or CSV path of bank transactions.
        ledger_data: DataFrame, list of row dicts, or CSV path of ledger transactions.

    Returns:
        MatchResult containing matched_pairs, unmatched_bank, unmatched_ledger,
        and ambiguous_candidates.
    """
    # 1. Load data without modifying the caller's objects
    if isinstance(bank_data, (str, Path)):
        bank_df = pd.read_csv(bank_data)
    elif isinstance(bank_data, pd.DataFrame):
        bank_df = bank_data.copy(deep=True)
    elif isinstance(bank_data, list):
        bank_df = pd.DataFrame(bank_data)
    else:
        raise TypeError(f"Unsupported bank_data type: {type(bank_data)}")

    if isinstance(ledger_data, (str, Path)):
        ledger_df = pd.read_csv(ledger_data)
    elif isinstance(ledger_data, pd.DataFrame):
        ledger_df = ledger_data.copy(deep=True)
    elif isinstance(ledger_data, list):
        ledger_df = pd.DataFrame(ledger_data)
    else:
        raise TypeError(f"Unsupported ledger_data type: {type(ledger_data)}")

    # Enforce integer cents and date types on deep copies
    b_df = bank_df.copy(deep=True)
    l_df = ledger_df.copy(deep=True)

    b_df["amount_cents"] = b_df["amount_cents"].astype(int)
    l_df["amount_cents"] = l_df["amount_cents"].astype(int)

    b_df["parsed_date"] = pd.to_datetime(b_df["date"]).dt.date
    l_df["parsed_date"] = pd.to_datetime(l_df["date"]).dt.date

    # Prepare raw dict representations for output
    bank_records = {row["bank_id"]: row.to_dict() for _, row in bank_df.iterrows()}
    ledger_records = {row["ledger_id"]: row.to_dict() for _, row in ledger_df.iterrows()}

    # 2. Find all candidate pairs where amount_cents match exactly
    # Merge candidates on exact amount_cents
    candidate_pairs = pd.merge(
        b_df[["bank_id", "date", "parsed_date", "amount_cents"]],
        l_df[["ledger_id", "date", "parsed_date", "amount_cents"]],
        on="amount_cents",
        suffixes=("_bank", "_ledger"),
    )

    if not candidate_pairs.empty:
        # Calculate date difference in days (absolute difference <= 3 days)
        candidate_pairs["day_diff"] = (
            candidate_pairs["parsed_date_bank"] - candidate_pairs["parsed_date_ledger"]
        ).apply(lambda delta: abs(delta.days))

        valid_candidates = candidate_pairs[candidate_pairs["day_diff"] <= 3]
    else:
        valid_candidates = pd.DataFrame(columns=["bank_id", "ledger_id", "amount_cents", "day_diff"])

    # 3. Analyze candidate multiplicity on each side
    bank_cand_counts = (
        valid_candidates.groupby("bank_id")["ledger_id"].nunique().to_dict()
        if not valid_candidates.empty
        else {}
    )
    ledger_cand_counts = (
        valid_candidates.groupby("ledger_id")["bank_id"].nunique().to_dict()
        if not valid_candidates.empty
        else {}
    )

    # A pair (b, l) is unique if b has exactly 1 candidate and l has exactly 1 candidate
    matched_pairs: List[Dict[str, Any]] = []
    matched_bank_ids = set()
    matched_ledger_ids = set()

    for _, row in valid_candidates.iterrows():
        b_id = row["bank_id"]
        l_id = row["ledger_id"]
        amt = int(row["amount_cents"])
        day_diff = int(row["day_diff"])

        if bank_cand_counts.get(b_id, 0) == 1 and ledger_cand_counts.get(l_id, 0) == 1:
            if b_id not in matched_bank_ids and l_id not in matched_ledger_ids:
                matched_bank_ids.add(b_id)
                matched_ledger_ids.add(l_id)
                reason = (
                    f"Exact unique match: amount {fmt(amt)} with {day_diff}-day date difference"
                )
                matched_pairs.append({
                    "bank_row": bank_records[b_id],
                    "ledger_row": ledger_records[l_id],
                    "bank_id": b_id,
                    "ledger_id": l_id,
                    "amount_cents": amt,
                    "date_diff_days": day_diff,
                    "reason": reason,
                })

    # 4. Identify ambiguous candidates
    # Any candidate where a bank row has >1 candidate or ledger row has >1 candidate
    ambiguous_bank_ids = set()
    ambiguous_ledger_ids = set()

    for _, row in valid_candidates.iterrows():
        b_id = row["bank_id"]
        l_id = row["ledger_id"]

        if b_id not in matched_bank_ids or l_id not in matched_ledger_ids:
            ambiguous_bank_ids.add(b_id)
            ambiguous_ledger_ids.add(l_id)

    ambiguous_candidates: List[Dict[str, Any]] = []
    if ambiguous_bank_ids or ambiguous_ledger_ids:
        # Group ambiguous rows by amount_cents for structured inspection
        ambig_subset = valid_candidates[
            valid_candidates["bank_id"].isin(ambiguous_bank_ids)
            | valid_candidates["ledger_id"].isin(ambiguous_ledger_ids)
        ]

        grouped = ambig_subset.groupby("amount_cents")
        for amt_val, group in grouped:
            amt = int(amt_val)
            g_b_ids = sorted(list(set(group["bank_id"])))
            g_l_ids = sorted(list(set(group["ledger_id"])))
            g_b_rows = [bank_records[bid] for bid in g_b_ids if bid in bank_records]
            g_l_rows = [ledger_records[lid] for lid in g_l_ids if lid in ledger_records]

            reason = (
                f"Ambiguous candidates: {len(g_b_ids)} bank row(s) and {len(g_l_ids)} ledger row(s) "
                f"share amount {fmt(amt)} within the 3-day date window without unique 1-to-1 match."
            )
            ambiguous_candidates.append({
                "amount_cents": amt,
                "bank_ids": g_b_ids,
                "ledger_ids": g_l_ids,
                "bank_rows": g_b_rows,
                "ledger_rows": g_l_rows,
                "reason": reason,
            })

    # 5. Identify completely unmatched rows (0 candidates within 3-day window)
    unmatched_bank: List[Dict[str, Any]] = []
    for bid, row_dict in bank_records.items():
        if bid not in matched_bank_ids and bid not in ambiguous_bank_ids:
            unmatched_bank.append(row_dict)

    unmatched_ledger: List[Dict[str, Any]] = []
    for lid, row_dict in ledger_records.items():
        if lid not in matched_ledger_ids and lid not in ambiguous_ledger_ids:
            unmatched_ledger.append(row_dict)

    return MatchResult(
        matched_pairs=matched_pairs,
        unmatched_bank=unmatched_bank,
        unmatched_ledger=unmatched_ledger,
        ambiguous_candidates=ambiguous_candidates,
    )


def summarize_variant_matching(variant_dir: Path) -> Dict[str, Any]:
    """Run matcher on a variant directory and return count metrics."""
    bank_csv = variant_dir / "bank.csv"
    ledger_csv = variant_dir / "ledger.csv"

    res = match_transactions(bank_csv, ledger_csv)

    bank_df = pd.read_csv(bank_csv)
    ledger_df = pd.read_csv(ledger_csv)

    total_bank_rows = len(bank_df)
    total_ledger_rows = len(ledger_df)
    total_rows = total_bank_rows + total_ledger_rows

    # Each matched pair resolves 1 bank row and 1 ledger row
    resolved_rows = 2 * len(res.matched_pairs)
    left_for_llm = total_rows - resolved_rows

    ambiguous_rows_count = sum(len(g["bank_ids"]) + len(g["ledger_ids"]) for g in res.ambiguous_candidates)
    unmatched_rows_count = len(res.unmatched_bank) + len(res.unmatched_ledger)

    return {
        "variant": variant_dir.name,
        "total_rows": total_rows,
        "bank_rows": total_bank_rows,
        "ledger_rows": total_ledger_rows,
        "matched_pairs": len(res.matched_pairs),
        "resolved_rows": resolved_rows,
        "left_for_llm": left_for_llm,
        "unmatched_rows": unmatched_rows_count,
        "ambiguous_rows": ambiguous_rows_count,
    }


def main() -> None:
    """CLI runner to print matching metrics across all 6 variants."""
    base_dir = Path(__file__).resolve().parent.parent
    variants_dir = base_dir / "data" / "variants"
    variant_names = ["clean", "timing", "fees", "errors", "tricky", "full"]

    print("Deterministic Pre-Matcher Summary Across Variants")
    print("=" * 95)
    header = (
        f"{'Variant':<10} | {'Total':<6} | {'Bank/GL':<10} | {'Resolved (Pairs)':<18} | "
        f"{'Resolved Rows':<14} | {'Left for LLM':<14} | {'Resolution %':<12}"
    )
    print(header)
    print("-" * 95)

    for v_name in variant_names:
        v_path = variants_dir / v_name
        if not v_path.is_dir():
            continue
        stats = summarize_variant_matching(v_path)
        pct = (stats["resolved_rows"] / stats["total_rows"]) * 100.0 if stats["total_rows"] else 0.0
        print(
            f"{stats['variant']:<10} | {stats['total_rows']:<6} | "
            f"{stats['bank_rows']}/{stats['ledger_rows']:<7} | "
            f"{stats['matched_pairs']:<18} | "
            f"{stats['resolved_rows']:<14} | "
            f"{stats['left_for_llm']:<14} | "
            f"{pct:>10.1f}%"
        )

    print("=" * 95)


if __name__ == "__main__":
    main()
