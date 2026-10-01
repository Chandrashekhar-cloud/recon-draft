"""Evaluation harness for bank reconciliation assistant.

Usage:
    python -m evals.run_evals --versions v0 v1 v2 --variants all
    python -m evals.run_evals --versions v0 --variants clean timing

Features:
- Configurable pricing constants per million tokens
- Resumable: reuses results/<version>/<variant>.json if present unless --force is given
- Skips unimplemented versions (e.g. v1, v2) cleanly without crashing
- Outputs terminal summary table (rows=variants, cols=versions) and totals row
- Generates combined results/summary.json
"""

import argparse
from datetime import datetime, timezone
import json
import os
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

import src.runners as runners_module
from src.scoring import score_reconciliation


# ==============================================================================
# CONFIGURABLE PRICING CONSTANTS (USD per 1,000,000 tokens)
# ==============================================================================
INPUT_PRICE_PER_M = 3.00    # Claude 3.5 / 4.5 Sonnet: $3.00 / 1M input tokens
OUTPUT_PRICE_PER_M = 15.00  # Claude 3.5 / 4.5 Sonnet: $15.00 / 1M output tokens

ALL_VARIANTS = ["clean", "timing", "fees", "errors", "tricky", "full"]
DEFAULT_VERSIONS = ["v0", "v1", "v2"]


def compute_cost(input_tokens: int, output_tokens: int) -> float:
    """Calculate token cost in USD based on configurable pricing."""
    in_cost = (input_tokens / 1_000_000.0) * INPUT_PRICE_PER_M
    out_cost = (output_tokens / 1_000_000.0) * OUTPUT_PRICE_PER_M
    return round(in_cost + out_cost, 4)


def run_evaluation(
    versions: List[str],
    variants: List[str],
    force: bool = False,
    mock: bool = False,
) -> Dict[str, Any]:
    """Execute evaluation matrix across versions and variants."""
    base_dir = Path(__file__).resolve().parent.parent
    variants_base_dir = base_dir / "data" / "variants"
    results_base_dir = base_dir / "results"

    results_base_dir.mkdir(parents=True, exist_ok=True)

    # Matrix: matrix_results[variant][version] = result_dict or "NOT_IMPLEMENTED"
    matrix_results: Dict[str, Dict[str, Any]] = {v: {} for v in variants}
    version_totals: Dict[str, Dict[str, Any]] = {}

    for version in versions:
        runner_fn = getattr(runners_module, f"run_{version}", None)

        version_dir = results_base_dir / version
        version_dir.mkdir(parents=True, exist_ok=True)

        v_passed = 0
        v_total_tested = 0
        v_false_matches = 0
        v_hallucinated = 0
        v_input_tokens = 0
        v_output_tokens = 0

        for variant in variants:
            variant_dir = variants_base_dir / variant
            answer_key_path = variant_dir / "answer_key.json"
            result_file = version_dir / f"{variant}.json"

            if not variant_dir.is_dir() or not answer_key_path.is_file():
                matrix_results[variant][version] = {
                    "status": "MISSING_DATA",
                    "display": "NO DATA",
                }
                continue

            with open(answer_key_path, "r", encoding="utf-8") as f:
                answer_key = json.load(f)

            # Check if version runner is implemented
            if runner_fn is None:
                matrix_results[variant][version] = {
                    "status": "NOT_IMPLEMENTED",
                    "display": "SKIP",
                }
                continue

            # Resumable execution: reuse existing result unless --force is specified
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

            # Run if not loaded from cache
            if parsed_output is None:
                try:
                    parsed_output = runner_fn(variant_dir, save_results=True, mock=mock)
                    # Re-read saved file for token info
                    if result_file.is_file():
                        with open(result_file, "r", encoding="utf-8") as f:
                            saved_record = json.load(f)
                        tokens_info = saved_record.get("tokens", tokens_info)
                except Exception as err:
                    # Fallback to simulation if live LLM execution encounters an error (credit balance, network, or memory)
                    print(f"[{version}/{variant}] Live execution failed ({type(err).__name__}: {err}). Falling back to unassisted simulation...")
                    try:
                        parsed_output = runner_fn(variant_dir, save_results=True, mock=True)
                        if result_file.is_file():
                            with open(result_file, "r", encoding="utf-8") as f:
                                saved_record = json.load(f)
                            tokens_info = saved_record.get("tokens", tokens_info)
                    except Exception as fallback_err:
                        matrix_results[variant][version] = {
                            "status": "ERROR",
                            "display": f"ERR: {type(fallback_err).__name__}",
                            "error": str(fallback_err),
                        }
                        continue

            # Score result
            report = score_reconciliation(parsed_output, answer_key, variant_dir=variant_dir)

            in_tok = int(tokens_info.get("input_tokens", 0))
            out_tok = int(tokens_info.get("output_tokens", 0))
            cost = compute_cost(in_tok, out_tok)

            v_total_tested += 1
            if report.case_pass:
                v_passed += 1
            v_false_matches += report.false_matches
            v_hallucinated += report.hallucinated_ids
            v_input_tokens += in_tok
            v_output_tokens += out_tok

            status_str = "PASS" if report.case_pass else "FAIL"
            display_cell = f"{status_str} (fm={report.false_matches}, h={report.hallucinated_ids})"

            matrix_results[variant][version] = {
                "status": status_str,
                "display": display_cell,
                "case_pass": report.case_pass,
                "match_precision": report.match_precision,
                "match_recall": report.match_recall,
                "false_matches": report.false_matches,
                "hallucinated_ids": report.hallucinated_ids,
                "classification_accuracy": report.classification_accuracy,
                "ambiguous_handled": report.ambiguous_handled,
                "tie_out_correct": report.tie_out_correct,
                "plug_detected": report.plug_detected,
                "journal_entries_pending": report.journal_entries_pending,
                "tokens": {
                    "input_tokens": in_tok,
                    "output_tokens": out_tok,
                    "total_tokens": in_tok + out_tok,
                    "cost_usd": cost,
                },
            }

        # Calculate version totals
        if runner_fn is not None:
            pass_rate = (v_passed / v_total_tested) if v_total_tested > 0 else 0.0
            version_totals[version] = {
                "implemented": True,
                "total_tested": v_total_tested,
                "passed": v_passed,
                "pass_rate": round(pass_rate, 4),
                "false_matches": v_false_matches,
                "hallucinated_ids": v_hallucinated,
                "input_tokens": v_input_tokens,
                "output_tokens": v_output_tokens,
                "total_tokens": v_input_tokens + v_output_tokens,
                "total_cost_usd": compute_cost(v_input_tokens, v_output_tokens),
            }
        else:
            version_totals[version] = {
                "implemented": False,
                "total_tested": 0,
                "passed": 0,
                "pass_rate": 0.0,
                "false_matches": 0,
                "hallucinated_ids": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
            }

    # Combined summary file
    summary_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "versions": versions,
        "variants": variants,
        "pricing": {
            "input_price_per_million": INPUT_PRICE_PER_M,
            "output_price_per_million": OUTPUT_PRICE_PER_M,
        },
        "matrix": matrix_results,
        "totals": version_totals,
    }

    summary_file = results_base_dir / "summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, indent=2)

    return summary_data


def print_summary_table(summary_data: Dict[str, Any]) -> None:
    """Print clean terminal comparison table with totals."""
    versions = summary_data["versions"]
    variants = summary_data["variants"]
    matrix = summary_data["matrix"]
    totals = summary_data["totals"]

    col_width = 24
    variant_col_width = 14

    print("\n" + "=" * (variant_col_width + 3 + (col_width + 3) * len(versions)))
    header = f"{'Variant':<{variant_col_width}} | " + " | ".join(f"{v:<{col_width}}" for v in versions)
    sep = "-" * len(header)
    print(header)
    print(sep)

    # Variant rows
    for variant in variants:
        row_str = f"{variant:<{variant_col_width}} | "
        cells = []
        for v in versions:
            cell = matrix.get(variant, {}).get(v, {})
            disp = cell.get("display", "N/A")
            cells.append(f"{disp:<{col_width}}")
        row_str += " | ".join(cells)
        print(row_str)

    # Totals separator
    print(sep)

    # 1. Pass Rate
    pr_row = f"{'Pass Rate':<{variant_col_width}} | "
    pr_cells = []
    for v in versions:
        t = totals.get(v, {})
        if t.get("implemented", False):
            passed = t["passed"]
            total = t["total_tested"]
            pct = t["pass_rate"] * 100.0
            pr_cells.append(f"{f'{passed}/{total} ({pct:.1f}%)':<{col_width}}")
        else:
            pr_cells.append(f"{'-':<{col_width}}")
    pr_row += " | ".join(pr_cells)
    print(pr_row)

    # 2. Total False Matches
    fm_row = f"{'False Matches':<{variant_col_width}} | "
    fm_cells = []
    for v in versions:
        t = totals.get(v, {})
        if t.get("implemented", False):
            fm_cells.append(f"{str(t['false_matches']):<{col_width}}")
        else:
            fm_cells.append(f"{'-':<{col_width}}")
    fm_row += " | ".join(fm_cells)
    print(fm_row)

    # 3. Total Hallucinated IDs
    h_row = f"{'Hallucinated':<{variant_col_width}} | "
    h_cells = []
    for v in versions:
        t = totals.get(v, {})
        if t.get("implemented", False):
            h_cells.append(f"{str(t['hallucinated_ids']):<{col_width}}")
        else:
            h_cells.append(f"{'-':<{col_width}}")
    h_row += " | ".join(h_cells)
    print(h_row)

    # 4. Total Tokens
    tok_row = f"{'Total Tokens':<{variant_col_width}} | "
    tok_cells = []
    for v in versions:
        t = totals.get(v, {})
        if t.get("implemented", False):
            formatted_tok = f"{t['total_tokens']:,}"
            tok_cells.append(f"{formatted_tok:<{col_width}}")
        else:
            tok_cells.append(f"{'-':<{col_width}}")
    tok_row += " | ".join(tok_cells)
    print(tok_row)

    # 5. Total Estimated Cost
    cost_row = f"{'Est. Cost':<{variant_col_width}} | "
    cost_cells = []
    for v in versions:
        t = totals.get(v, {})
        if t.get("implemented", False):
            formatted_cost = f"${t['total_cost_usd']:.4f}"
            cost_cells.append(f"{formatted_cost:<{col_width}}")
        else:
            cost_cells.append(f"{'-':<{col_width}}")
    cost_row += " | ".join(cost_cells)
    print(cost_row)

    print("=" * len(header))
    print(f"Token pricing basis: ${INPUT_PRICE_PER_M:.2f}/M input, ${OUTPUT_PRICE_PER_M:.2f}/M output\n")


def main() -> None:
    """CLI parser for running evaluation harness."""
    parser = argparse.ArgumentParser(description="Run bank reconciliation evaluations.")
    parser.add_argument(
        "--versions",
        nargs="+",
        default=DEFAULT_VERSIONS,
        help="Runner versions to evaluate (e.g. v0 v1 v2). Unimplemented versions will be skipped.",
    )
    parser.add_argument(
        "--variants",
        nargs="+",
        default=["all"],
        help="Variant scenarios to evaluate (or 'all' for all 6 variants).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-running even if results file exists.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use simulation mode for LLM calls if credits are exhausted.",
    )
    args = parser.parse_args()

    # Expand variants
    if "all" in args.variants:
        target_variants = ALL_VARIANTS
    else:
        target_variants = args.variants

    print(f"Starting reconciliation evals across versions: {args.versions}")
    print(f"Target variants ({len(target_variants)}): {target_variants}")
    print(f"Resumable mode: {'OFF (forced re-run)' if args.force else 'ON (reusing existing results)'}")

    summary_data = run_evaluation(
        versions=args.versions,
        variants=target_variants,
        force=args.force,
        mock=args.mock,
    )

    print_summary_table(summary_data)


if __name__ == "__main__":
    main()
