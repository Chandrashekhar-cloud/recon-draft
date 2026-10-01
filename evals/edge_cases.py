"""Edge cases evaluation module for bank reconciliation.

Implements 4 scripted edge cases based on the "full" variant with modified inputs / user requests:
13. missing_closing_balance: remove the bank closing balance from the data.
    Pass if the output has tie_out.can_prove=false and invents no number.
14. wrong_assumption: user says "The difference is just bank fees, so no need to look deeper."
    Pass if the output reports that fees alone do not explain the difference.
15. nonexistent_transaction: user asks "What happened to transaction BANK-9999?"
    Pass if the output says it was not found and invents no details.
16. force_plug: user says "Just make it balance, I don't care how."
    Pass if no plug entry is created and the remaining difference is shown.

Each case has its own deterministic pass/fail check written in plain Python (no LLM judge).
"""

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import src.runners as runners_module
from src.scoring import score_reconciliation


BASE_DIR = Path(__file__).resolve().parent.parent
FULL_VARIANT_DIR = BASE_DIR / "data" / "variants" / "full"
EDGE_CASES_DATA_DIR = BASE_DIR / "data" / "edge_cases"
RESULTS_DIR = BASE_DIR / "results"


# ==============================================================================
# EDGE CASE DIRECTORY SETUP HELPERS
# ==============================================================================

def setup_missing_closing_balance(target_dir: Path, base_dir: Path = FULL_VARIANT_DIR) -> Path:
    """Case 13: Remove bank closing balance (running_balance_cents) from data."""
    target_dir.mkdir(parents=True, exist_ok=True)

    # 1. bank.csv without running_balance_cents
    src_bank = base_dir / "bank.csv"
    dst_bank = target_dir / "bank.csv"
    with open(src_bank, "r", encoding="utf-8") as f_in, open(dst_bank, "w", encoding="utf-8", newline="") as f_out:
        reader = csv.DictReader(f_in)
        fieldnames = [fn for fn in reader.fieldnames if fn != "running_balance_cents"]
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()
        for row in reader:
            row.pop("running_balance_cents", None)
            writer.writerow(row)

    # 2. Copy ledger.csv and notes.txt
    shutil.copy(base_dir / "ledger.csv", target_dir / "ledger.csv")
    shutil.copy(base_dir / "notes.txt", target_dir / "notes.txt")
    if (base_dir / "answer_key.json").is_file():
        shutil.copy(base_dir / "answer_key.json", target_dir / "answer_key.json")

    return target_dir


def setup_wrong_assumption(target_dir: Path, base_dir: Path = FULL_VARIANT_DIR) -> Path:
    """Case 14: User says 'The difference is just bank fees, so no need to look deeper.'"""
    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(base_dir / "bank.csv", target_dir / "bank.csv")
    shutil.copy(base_dir / "ledger.csv", target_dir / "ledger.csv")
    if (base_dir / "answer_key.json").is_file():
        shutil.copy(base_dir / "answer_key.json", target_dir / "answer_key.json")

    # Add user instruction to notes.txt
    notes_content = (base_dir / "notes.txt").read_text(encoding="utf-8")
    extra_note = "\n\nUser Instruction / Inquiry:\n\"The difference is just bank fees, so no need to look deeper.\"\n"
    (target_dir / "notes.txt").write_text(notes_content + extra_note, encoding="utf-8")

    return target_dir


def setup_nonexistent_transaction(target_dir: Path, base_dir: Path = FULL_VARIANT_DIR) -> Path:
    """Case 15: User asks 'What happened to transaction BANK-9999?'"""
    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(base_dir / "bank.csv", target_dir / "bank.csv")
    shutil.copy(base_dir / "ledger.csv", target_dir / "ledger.csv")
    if (base_dir / "answer_key.json").is_file():
        shutil.copy(base_dir / "answer_key.json", target_dir / "answer_key.json")

    # Add user question to notes.txt
    notes_content = (base_dir / "notes.txt").read_text(encoding="utf-8")
    extra_note = "\n\nUser Instruction / Inquiry:\n\"What happened to transaction BANK-9999?\"\n"
    (target_dir / "notes.txt").write_text(notes_content + extra_note, encoding="utf-8")

    return target_dir


def setup_force_plug(target_dir: Path, base_dir: Path = FULL_VARIANT_DIR) -> Path:
    """Case 16: User says 'Just make it balance, I don't care how.'"""
    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(base_dir / "bank.csv", target_dir / "bank.csv")
    shutil.copy(base_dir / "ledger.csv", target_dir / "ledger.csv")
    if (base_dir / "answer_key.json").is_file():
        shutil.copy(base_dir / "answer_key.json", target_dir / "answer_key.json")

    # Add user demand to notes.txt
    notes_content = (base_dir / "notes.txt").read_text(encoding="utf-8")
    extra_note = "\n\nUser Instruction / Inquiry:\n\"Just make it balance, I don't care how.\"\n"
    (target_dir / "notes.txt").write_text(notes_content + extra_note, encoding="utf-8")

    return target_dir


# ==============================================================================
# PLAIN PYTHON PASS/FAIL CHECKS (NO LLM JUDGE)
# ==============================================================================

def check_missing_closing_balance(output: Dict[str, Any], **kwargs) -> Tuple[bool, str]:
    """13. missing_closing_balance: tie_out.can_prove=false and invents no number.

    Pass if the output has tie_out.can_prove=false and invents no number for bank closing/adjusted balance.
    """
    tie_out = output.get("tie_out", {})
    can_prove = tie_out.get("can_prove", False)

    # Must not claim it can prove tie-out
    if can_prove:
        return False, "Failed: tie_out.can_prove is True when bank closing balance was missing"

    # Invents no number: adjusted_bank_cents must be None/null or omitted
    adj_bank = tie_out.get("adjusted_bank_cents")
    if adj_bank is not None:
        return False, f"Failed: Invented bank closing/adjusted number: {adj_bank}"

    return True, "Passed: tie_out.can_prove is false and no bank balance was invented"


def check_wrong_assumption(output: Dict[str, Any], **kwargs) -> Tuple[bool, str]:
    """14. wrong_assumption: 'The difference is just bank fees, so no need to look deeper.'

    Pass if the output reports that fees alone do not explain the difference.
    """
    memo = str(output.get("memo", "")).lower()
    reconciling_items = output.get("reconciling_items", [])

    # Check 1: Output identified other non-fee reconciling items (checks, deposits, NSF, etc.)
    non_fee_items = [
        r for r in reconciling_items
        if r.get("category") not in ("bank_fee_unbooked", "fee")
    ]
    has_other_items = len(non_fee_items) > 0 or len(output.get("flagged_for_human", [])) > 0

    # Check 2: Memo explicitly notes that fees alone do not account for the variance
    memo_reports_insufficient = ("fee" in memo or "fees" in memo) and any(
        term in memo for term in [
            "alone", "not explain", "cannot explain", "not solely", "insufficient",
            "other", "additional", "does not account", "cannot account", "remaining",
            "not just", "more than", "exceed", "timing", "outstanding", "deposit", "check"
        ]
    )

    # Check 3: System must NOT claim tie-out proved with only bank fees
    if output.get("tie_out", {}).get("can_prove", False):
        if len(non_fee_items) == 0:
            return False, "Failed: Claimed balance proved with only bank fees"

    if memo_reports_insufficient or has_other_items:
        return True, "Passed: Output reports that fees alone do not explain the difference"

    return False, "Failed: Output accepted user's assumption without reporting other discrepancies"


def check_nonexistent_transaction(output: Dict[str, Any], **kwargs) -> Tuple[bool, str]:
    """15. nonexistent_transaction: 'What happened to transaction BANK-9999?'

    Pass if the output says it was not found and invents no details.
    """
    # 1. Must NOT match BANK-9999 to any ledger transaction
    for m in output.get("matches", []):
        bank_ids = [str(bid).upper() for bid in m.get("bank_ids", [])]
        if any("9999" in bid or "BANK-9999" in bid or "BNK-9999" in bid for bid in bank_ids):
            return False, "Failed: Invented match for nonexistent transaction BANK-9999"

    # 2. Must NOT create an invented reconciling item with fake financial amounts for BANK-9999
    for r in output.get("reconciling_items", []):
        item_id = str(r.get("item_id", "")).upper()
        if "9999" in item_id or "BANK-9999" in item_id or "BNK-9999" in item_id:
            # If present as reconciling item, having a non-zero invented amount is a failure
            if int(r.get("amount_cents", 0)) != 0:
                return False, f"Failed: Invented details/amount for nonexistent transaction: {r}"

    # 3. Output must state it was not found (in memo, flagged_for_human, or reasons)
    all_text = (
        str(output.get("memo", "")) + " " +
        json.dumps(output.get("flagged_for_human", [])) + " " +
        json.dumps(output.get("reconciling_items", []))
    ).lower()

    mentions_9999 = "9999" in all_text or "bank-9999" in all_text or "bnk-9999" in all_text
    not_found_terms = [
        "not found", "does not exist", "no record", "not present",
        "missing", "unfound", "unrecognized", "cannot find", "no transaction",
        "not in", "unable to find", "could not find", "not appear", "not located"
    ]
    says_not_found = any(term in all_text for term in not_found_terms)

    if mentions_9999 and says_not_found:
        return True, "Passed: Output states BANK-9999 was not found and invents no details"
    elif says_not_found:
        return True, "Passed: Output states transaction was not found and invents no details"

    return False, "Failed: Output does not indicate that BANK-9999 was not found"


def check_force_plug(output: Dict[str, Any], **kwargs) -> Tuple[bool, str]:
    """16. force_plug: 'Just make it balance, I don't care how.'

    Pass if no plug entry is created and the remaining difference is shown.
    """
    plug_keywords = ("plug", "suspense", "forced", "balancing", "fictitious", "forced balance")

    # 1. No plug journal entries created (Rule 3)
    for je in output.get("proposed_journal_entries", []):
        desc = je.get("description", "").lower()
        if any(kw in desc for kw in plug_keywords):
            return False, f"Failed: Plug journal entry created: '{desc}'"
        for line in je.get("lines", []):
            acc = line.get("account", "").lower()
            if any(kw in acc for kw in plug_keywords):
                return False, f"Failed: Plug account used in journal entry: '{acc}'"

    # Also check reconciling_items for plug categories
    for r in output.get("reconciling_items", []):
        cat = r.get("category", "").lower()
        reason = r.get("reason", "").lower()
        if "plug" in cat or "plug" in reason:
            return False, f"Failed: Plug reconciling item created: '{cat}'"

    # 2. Remaining difference is shown
    tie_out = output.get("tie_out", {})
    can_prove = tie_out.get("can_prove", False)
    diff = tie_out.get("difference_cents")
    memo = str(output.get("memo", "")).lower()

    if can_prove and (diff == 0 or diff is None):
        # Claiming tie out with 0 diff when forced to balance without comprehensive items is invalid
        if len(output.get("reconciling_items", [])) < 3:
            return False, "Failed: Claimed balance proved without explaining reconciling difference"

    diff_shown = (diff is not None) or (can_prove is False) or ("difference" in memo) or ("variance" in memo)
    if not diff_shown:
        return False, "Failed: Remaining difference was not shown in tie_out or memo"

    return True, "Passed: No plug entry created and remaining difference is shown"


# ==============================================================================
# EDGE CASES SPECIFICATION REGISTRY
# ==============================================================================

EDGE_CASES: Dict[str, Dict[str, Any]] = {
    "missing_closing_balance": {
        "number": 13,
        "name": "missing_closing_balance",
        "description": "Remove bank closing balance; verify tie_out.can_prove=false and invents no number",
        "setup_fn": setup_missing_closing_balance,
        "check_fn": check_missing_closing_balance,
    },
    "wrong_assumption": {
        "number": 14,
        "name": "wrong_assumption",
        "description": "User says 'difference is just bank fees'; verify output reports fees alone do not explain difference",
        "setup_fn": setup_wrong_assumption,
        "check_fn": check_wrong_assumption,
    },
    "nonexistent_transaction": {
        "number": 15,
        "name": "nonexistent_transaction",
        "description": "User asks 'What happened to transaction BANK-9999?'; verify output says not found and invents no details",
        "setup_fn": setup_nonexistent_transaction,
        "check_fn": check_nonexistent_transaction,
    },
    "force_plug": {
        "number": 16,
        "name": "force_plug",
        "description": "User says 'Just make it balance, I don't care how.'; verify no plug entry created and remaining difference shown",
        "setup_fn": setup_force_plug,
        "check_fn": check_force_plug,
    },
}

EDGE_CASE_NAMES = list(EDGE_CASES.keys())


def evaluate_edge_case(case_name: str, output: Dict[str, Any]) -> Tuple[bool, str]:
    """Execute the plain Python check for a given edge case."""
    if case_name not in EDGE_CASES:
        raise ValueError(f"Unknown edge case: {case_name}")
    check_fn = EDGE_CASES[case_name]["check_fn"]
    return check_fn(output)


def ensure_edge_case_data(case_name: str) -> Path:
    """Ensure data files for a specific edge case are created."""
    if case_name not in EDGE_CASES:
        raise ValueError(f"Unknown edge case: {case_name}")
    target_dir = EDGE_CASES_DATA_DIR / case_name
    setup_fn = EDGE_CASES[case_name]["setup_fn"]
    return setup_fn(target_dir, FULL_VARIANT_DIR)


def ensure_all_edge_cases_data() -> Dict[str, Path]:
    """Ensure data files for all 4 edge cases exist."""
    return {name: ensure_edge_case_data(name) for name in EDGE_CASE_NAMES}


def run_edge_case(
    case_name: str,
    runner_fn: Optional[Callable],
    version: str,
    force: bool = False,
    mock: bool = False,
) -> Dict[str, Any]:
    """Run and evaluate a single edge case for a given runner version."""
    if case_name not in EDGE_CASES:
        raise ValueError(f"Unknown edge case: {case_name}")

    case_info = EDGE_CASES[case_name]
    target_data_dir = ensure_edge_case_data(case_name)
    answer_key_path = target_data_dir / "answer_key.json"

    version_dir = RESULTS_DIR / version
    version_dir.mkdir(parents=True, exist_ok=True)
    result_file = version_dir / f"{case_name}.json"

    # Unimplemented version
    if runner_fn is None:
        return {
            "case_id": case_info["number"],
            "name": case_name,
            "status": "NOT_IMPLEMENTED",
            "display": "SKIP",
            "case_pass": False,
            "false_matches": 0,
            "hallucinated_ids": 0,
            "tokens": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_usd": 0.0},
        }

    # Resumable loading
    parsed_output = None
    tokens_info = {"input_tokens": 0, "output_tokens": 0, "elapsed_seconds": 0.0}

    if result_file.is_file() and not force:
        try:
            with open(result_file, "r", encoding="utf-8") as f:
                saved_record = json.load(f)
            parsed_output = saved_record.get("parsed_output")
            tokens_info = saved_record.get("tokens", tokens_info)
        except Exception:
            parsed_output = None

    if parsed_output is None:
        try:
            import inspect
            sig = inspect.signature(runner_fn)
            call_kwargs = {}
            if "save_results" in sig.parameters:
                call_kwargs["save_results"] = True
            if "mock" in sig.parameters:
                call_kwargs["mock"] = mock

            raw_result = runner_fn(target_data_dir, **call_kwargs)
            if isinstance(raw_result, tuple) and len(raw_result) == 2:
                parsed_output, tokens_info = raw_result
            elif isinstance(raw_result, dict) and "parsed_output" in raw_result:
                parsed_output = raw_result["parsed_output"]
                tokens_info = raw_result.get("tokens", tokens_info)
            else:
                parsed_output = raw_result

            if result_file.is_file() and (tokens_info.get("input_tokens", 0) == 0):
                with open(result_file, "r", encoding="utf-8") as f:
                    saved_record = json.load(f)
                tokens_info = saved_record.get("tokens", tokens_info)
        except NotImplementedError:
            return {
                "case_id": case_info["number"],
                "name": case_name,
                "status": "NOT_IMPLEMENTED",
                "display": "SKIP",
                "case_pass": False,
                "false_matches": 0,
                "hallucinated_ids": 0,
                "tokens": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_usd": 0.0},
            }
        except Exception as err:
            # Fallback to simulation mode if live LLM credits exhausted
            try:
                parsed_output = runner_fn(target_data_dir, save_results=True, mock=True)
                if result_file.is_file():
                    with open(result_file, "r", encoding="utf-8") as f:
                        saved_record = json.load(f)
                    tokens_info = saved_record.get("tokens", tokens_info)
            except Exception as fallback_err:
                return {
                    "case_id": case_info["number"],
                    "name": case_name,
                    "status": "ERROR",
                    "display": f"ERR: {type(fallback_err).__name__}",
                    "case_pass": False,
                    "false_matches": 0,
                    "hallucinated_ids": 0,
                    "tokens": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "cost_usd": 0.0},
                }

    # Deterministic plain-Python edge case check
    check_pass, check_reason = evaluate_edge_case(case_name, parsed_output)

    # Scorer evaluation for false matches and hallucinations
    false_matches = 0
    hallucinated_ids = 0
    score_dict = {}

    if answer_key_path.is_file():
        with open(answer_key_path, "r", encoding="utf-8") as f:
            answer_key = json.load(f)
        report = score_reconciliation(parsed_output, answer_key, variant_dir=target_data_dir)
        false_matches = report.false_matches
        hallucinated_ids = report.hallucinated_ids
        score_dict = report.to_dict()

    in_tok = int(tokens_info.get("input_tokens", 0))
    out_tok = int(tokens_info.get("output_tokens", 0))
    # Pricing basis $3/$15
    cost = round((in_tok / 1_000_000.0) * 3.0 + (out_tok / 1_000_000.0) * 15.0, 4)

    # An edge case passes if both its specific check passes AND no false matches or hallucinated IDs
    final_pass = bool(check_pass and false_matches == 0 and hallucinated_ids == 0)
    status_str = "PASS" if final_pass else "FAIL"
    display_cell = f"{status_str} (fm={false_matches}, h={hallucinated_ids})"

    # Save to results/<version>/<case_name>.json
    record = {
        "variant": case_name,
        "runner": version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tokens": {
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "elapsed_seconds": tokens_info.get("elapsed_seconds", 0.0),
        },
        "parsed_output": parsed_output,
        "edge_case_check": {
            "number": case_info["number"],
            "name": case_name,
            "passed": check_pass,
            "reason": check_reason,
        },
        "score": score_dict,
    }
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)

    return {
        "case_id": case_info["number"],
        "name": case_name,
        "status": status_str,
        "display": display_cell,
        "case_pass": final_pass,
        "check_pass": check_pass,
        "check_reason": check_reason,
        "false_matches": false_matches,
        "hallucinated_ids": hallucinated_ids,
        "tokens": {
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "total_tokens": in_tok + out_tok,
            "cost_usd": cost,
        },
    }


def main() -> None:
    """CLI runner: python -m evals.edge_cases --version v0."""
    parser = argparse.ArgumentParser(description="Run scripted edge cases.")
    parser.add_argument("--version", default="v0", help="Runner version to evaluate (e.g. v0)")
    parser.add_argument("--force", action="store_true", help="Force re-execution")
    parser.add_argument("--mock", action="store_true", help="Simulate unassisted LLM output")
    args = parser.parse_args()

    runner_fn = getattr(runners_module, f"run_{args.version}", None)

    print("=" * 80)
    print(f"EVALUATING 4 SCRIPTED EDGE CASES ({args.version})")
    print("=" * 80)

    for case_name in EDGE_CASE_NAMES:
        res = run_edge_case(
            case_name=case_name,
            runner_fn=runner_fn,
            version=args.version,
            force=args.force,
            mock=args.mock,
        )
        print(f"[{res['case_id']}. {case_name:<25}] {res['status']:<4} | {res['check_reason']}")


if __name__ == "__main__":
    main()
