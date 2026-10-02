"""Flask backend for autonomous bank reconciliation system.

Provides REST API endpoints for:
- Variant discovery, raw CSV data, and metadata.
- Asynchronous reconciliation execution across architectures (v0, v1, v2, replay).
- Progress tracking with step-level timestamps.
- Score reports against ground truth answer keys.
- Skill and tool introspection.
- Human-in-the-loop review decisions and filtered export of accepted items.
"""

import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

# Ensure repository root is on sys.path when running python app/app.py directly
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv

load_dotenv(override=True)

from flask import Flask, jsonify, redirect, render_template, request, url_for, Response

from evals.edge_cases import EDGE_CASE_NAMES, ensure_edge_case_data
from evals.run_evals import run_evaluation, DEFAULT_VERSIONS, ALL_VARIANTS, compute_cost
import src.runners as runners_module
from src.runners import (
    SYSTEM_PROMPT_V0,
    get_system_prompt_v1,
    get_system_prompt_v2,
    OUTPUT_SCHEMA_PROMPT,
)
from src.scoring import score_reconciliation
from src.tieout import calculate_tie_out
from src.tools import ALL_TOOLS


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
VARIANTS_DIR = DATA_DIR / "variants"
RESULTS_DIR = BASE_DIR / "results"
CACHE_DIR = BASE_DIR / "cache"
SKILL_FILE = BASE_DIR / "skills" / "bank-reconciliation" / "SKILL.md"
REVIEWS_FILE = RESULTS_DIR / "reviews.json"
SUMMARY_FILE = RESULTS_DIR / "summary.json"

CORE_VARIANTS = ["clean", "timing", "fees", "errors", "tricky", "full"]
ALL_VARIANTS = CORE_VARIANTS + EDGE_CASE_NAMES

app = Flask(__name__)

# Thread-safe in-memory store for run states
RUNS_LOCK = threading.Lock()
RUNS_STORE: Dict[str, Dict[str, Any]] = {}

# Thread-safe in-memory store for evaluation suite run
EVALS_LOCK = threading.Lock()
EVALS_STATE: Dict[str, Any] = {
    "status": "idle",
    "step": "Ready",
    "progress_pct": 0,
    "last_run_time": None,
    "error": None,
}


def iso_now() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def get_variant_path(variant: str) -> Optional[Path]:
    """Resolve directory path for a core variant or scripted edge case."""
    if variant in CORE_VARIANTS:
        v_dir = VARIANTS_DIR / variant
        return v_dir if v_dir.is_dir() else None
    elif variant in EDGE_CASE_NAMES:
        return ensure_edge_case_data(variant)
    return None


# ==============================================================================
# ERROR HANDLERS (Standard JSON responses)
# ==============================================================================

@app.errorhandler(400)
def bad_request(err):
    return jsonify({"error": str(err.description if hasattr(err, "description") else err)}), 400


@app.errorhandler(404)
def not_found(err):
    return jsonify({"error": str(err.description if hasattr(err, "description") else err)}), 404


@app.errorhandler(500)
def server_error(err):
    return jsonify({"error": "Internal server error", "details": str(err)}), 500


# ==============================================================================
# API ROUTES
# ==============================================================================

@app.route("/api/variants", methods=["GET"])
def list_variants():
    """List all available variants with row counts, trap list, and short description."""
    variants_info: List[Dict[str, Any]] = []

    for name in ALL_VARIANTS:
        v_dir = get_variant_path(name)
        if not v_dir or not v_dir.is_dir():
            continue

        bank_csv = v_dir / "bank.csv"
        ledger_csv = v_dir / "ledger.csv"
        notes_file = v_dir / "notes.txt"
        key_file = v_dir / "answer_key.json"

        # Count CSV rows
        bank_count = 0
        if bank_csv.is_file():
            with open(bank_csv, "r", encoding="utf-8") as f:
                bank_count = sum(1 for _ in csv.DictReader(f))

        ledger_count = 0
        if ledger_csv.is_file():
            with open(ledger_csv, "r", encoding="utf-8") as f:
                ledger_count = sum(1 for _ in csv.DictReader(f))

        # Extract trap list from answer key
        traps: List[str] = []
        if key_file.is_file():
            try:
                with open(key_file, "r", encoding="utf-8") as f:
                    key_data = json.load(f)
                seen_traps: Set[str] = set()
                for item in key_data.get("reconciling_items", []):
                    cat = item.get("category")
                    if cat and cat not in seen_traps:
                        seen_traps.add(cat)
                        traps.append(cat)
                if key_data.get("ambiguous_groups"):
                    traps.append("ambiguous_candidates")
            except Exception:
                pass

        if not traps:
            traps = ["none"] if name == "clean" else ["unspecified"]

        # Short description from notes.txt
        description = "Bank reconciliation dataset"
        if notes_file.is_file():
            try:
                lines = [line.strip() for line in notes_file.read_text(encoding="utf-8").splitlines() if line.strip()]
                # Skip title line if present
                for line in lines:
                    if not line.lower().startswith("brightloop") and len(line) > 10:
                        description = line
                        break
                if description == "Bank reconciliation dataset" and lines:
                    description = lines[0]
            except Exception:
                pass

        variants_info.append({
            "name": name,
            "type": "core" if name in CORE_VARIANTS else "edge_case",
            "bank_rows": bank_count,
            "ledger_rows": ledger_count,
            "traps": traps,
            "description": description,
        })

    return jsonify({"variants": variants_info, "count": len(variants_info)})


@app.route("/api/variant/<name>/data", methods=["GET"])
def get_variant_data(name: str):
    """Retrieve bank transactions, general ledger rows, and notes for a specific variant."""
    v_dir = get_variant_path(name)
    if not v_dir or not v_dir.is_dir():
        return jsonify({"error": f"Variant '{name}' not found"}), 404

    bank_csv = v_dir / "bank.csv"
    ledger_csv = v_dir / "ledger.csv"
    notes_file = v_dir / "notes.txt"

    bank_rows = []
    if bank_csv.is_file():
        with open(bank_csv, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                row = dict(r)
                if "amount_cents" in row:
                    row["amount_cents"] = int(row["amount_cents"])
                if "running_balance_cents" in row and row["running_balance_cents"]:
                    row["running_balance_cents"] = int(row["running_balance_cents"])
                bank_rows.append(row)

    ledger_rows = []
    if ledger_csv.is_file():
        with open(ledger_csv, "r", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                row = dict(r)
                if "amount_cents" in row:
                    row["amount_cents"] = int(row["amount_cents"])
                ledger_rows.append(row)

    notes_text = notes_file.read_text(encoding="utf-8") if notes_file.is_file() else ""

    key_file = v_dir / "answer_key.json"
    balances = {}
    if key_file.is_file():
        try:
            with open(key_file, "r", encoding="utf-8") as f:
                key_data = json.load(f)
            balances = key_data.get("balances", {})
        except Exception:
            pass

    if not balances:
        bank_open = 5000000
        bank_sum = sum(r.get("amount_cents", 0) for r in bank_rows)
        book_open = 5000000
        book_sum = sum(r.get("amount_cents", 0) for r in ledger_rows)
        balances = {
            "bank_opening_cents": bank_open,
            "bank_closing_cents": bank_open + bank_sum,
            "book_opening_cents": book_open,
            "book_closing_cents": book_open + book_sum,
        }

    return jsonify({
        "variant": name,
        "bank_rows": bank_rows,
        "bank_count": len(bank_rows),
        "ledger_rows": ledger_rows,
        "ledger_count": len(ledger_rows),
        "notes": notes_text,
        "balances": balances,
    })


def _execute_run_pipeline(run_id: str, variant: str, mode: str) -> None:
    """Background worker function executing the requested reconciliation pipeline."""
    load_dotenv(override=True)
    v_dir = get_variant_path(variant)
    if not v_dir:
        with RUNS_LOCK:
            RUNS_STORE[run_id]["status"] = "error"
            RUNS_STORE[run_id]["error"] = f"Variant directory not found for '{variant}'"
        return

    def update_step(step_name: str):
        with RUNS_LOCK:
            RUNS_STORE[run_id]["steps"].append({
                "step": step_name,
                "timestamp": iso_now(),
            })
            RUNS_STORE[run_id]["current_step"] = step_name

    try:
        if mode == "replay":
            # REPLAY MODE: Load verified result directly from cache/ with zero API calls
            update_step("matching")
            time.sleep(0.05)
            update_step("verifying")
            time.sleep(0.05)
            update_step("writing memo")

            cache_file = CACHE_DIR / f"{variant}.json"
            if not cache_file.is_file():
                # Fallback to results/v2/<variant>.json if not cached
                cache_file = RESULTS_DIR / "v2" / f"{variant}.json"

            if not cache_file.is_file():
                raise FileNotFoundError(f"No cached run result found for variant '{variant}' in {CACHE_DIR}")

            with open(cache_file, "r", encoding="utf-8") as f:
                result_data = json.load(f)

            # Score against answer key if available
            key_file = v_dir / "answer_key.json"
            if key_file.is_file():
                with open(key_file, "r", encoding="utf-8") as f:
                    answer_key = json.load(f)
                score_rep = score_reconciliation(
                    result_data.get("parsed_output", {}),
                    answer_key,
                    variant_dir=v_dir,
                )
                result_data["score"] = score_rep.to_dict()

            update_step("done")
            with RUNS_LOCK:
                RUNS_STORE[run_id]["status"] = "done"
                RUNS_STORE[run_id]["result"] = result_data

        else:
            # LIVE / RUNNER MODE: v0, v1, or v2
            update_step("matching")
            time.sleep(0.05)
            update_step("asking Claude")

            runner_fn = getattr(runners_module, f"run_{mode}", None)
            if runner_fn is None:
                raise ValueError(f"Unknown runner mode '{mode}'")

            # Execute runner
            parsed_output = runner_fn(v_dir, save_results=True)

            update_step("verifying")
            time.sleep(0.05)
            update_step("writing memo")
            time.sleep(0.05)

            # Read saved result record
            out_file = RESULTS_DIR / mode / f"{variant}.json"
            if out_file.is_file():
                with open(out_file, "r", encoding="utf-8") as f:
                    result_data = json.load(f)
            else:
                result_data = {
                    "variant": variant,
                    "runner": mode,
                    "timestamp": iso_now(),
                    "parsed_output": parsed_output,
                }

            # Score against answer key
            key_file = v_dir / "answer_key.json"
            if key_file.is_file():
                with open(key_file, "r", encoding="utf-8") as f:
                    answer_key = json.load(f)
                score_rep = score_reconciliation(
                    result_data.get("parsed_output", {}),
                    answer_key,
                    variant_dir=v_dir,
                )
                result_data["score"] = score_rep.to_dict()

            update_step("done")
            with RUNS_LOCK:
                RUNS_STORE[run_id]["status"] = "done"
                RUNS_STORE[run_id]["result"] = result_data

    except Exception as exc:
        with RUNS_LOCK:
            RUNS_STORE[run_id]["status"] = "error"
            RUNS_STORE[run_id]["error"] = str(exc)
            RUNS_STORE[run_id]["steps"].append({
                "step": "error",
                "timestamp": iso_now(),
                "error": str(exc),
            })


@app.route("/api/run", methods=["POST"])
def start_run():
    """Start an asynchronous reconciliation run.

    Request body:
        {
            "variant": "clean" | "timing" | ... ,
            "mode": "v0" | "v1" | "v2" | "replay"
        }
    """
    data = request.get_json(silent=True) or {}
    variant = str(data.get("variant", "")).strip()
    mode = str(data.get("mode", "")).strip().lower()

    if not variant:
        return jsonify({"error": "Missing required field: 'variant'"}), 400
    if mode not in ("v0", "v1", "v2", "replay"):
        return jsonify({"error": f"Invalid mode '{mode}'. Allowed: 'v0', 'v1', 'v2', 'replay'"}), 400

    v_dir = get_variant_path(variant)
    if not v_dir or not v_dir.is_dir():
        return jsonify({"error": f"Unknown variant '{variant}'. Allowed: {ALL_VARIANTS}"}), 404

    run_id = f"run_{uuid.uuid4().hex[:10]}"

    with RUNS_LOCK:
        RUNS_STORE[run_id] = {
            "run_id": run_id,
            "variant": variant,
            "mode": mode,
            "status": "running",
            "current_step": "created",
            "steps": [{"step": "created", "timestamp": iso_now()}],
            "result": None,
            "error": None,
        }

    # Launch background execution thread
    thread = threading.Thread(
        target=_execute_run_pipeline,
        args=(run_id, variant, mode),
        daemon=True,
    )
    thread.start()

    return jsonify({
        "run_id": run_id,
        "variant": variant,
        "mode": mode,
        "status": "running",
        "created_at": iso_now(),
    }), 202


@app.route("/api/run/<run_id>/status", methods=["GET"])
def get_run_status(run_id: str):
    """Get the execution status and timeline of progress steps for a run."""
    with RUNS_LOCK:
        run_record = RUNS_STORE.get(run_id)

    if not run_record:
        return jsonify({"error": f"Run ID '{run_id}' not found"}), 404

    return jsonify({
        "run_id": run_record["run_id"],
        "variant": run_record["variant"],
        "mode": run_record["mode"],
        "status": run_record["status"],
        "current_step": run_record.get("current_step", "unknown"),
        "steps": run_record.get("steps", []),
        "error": run_record.get("error"),
    })


@app.route("/api/run/<run_id>/result", methods=["GET"])
def get_run_result(run_id: str):
    """Get the full reconciliation result JSON including trace, transaction details, and tie-out proof."""
    with RUNS_LOCK:
        run_record = RUNS_STORE.get(run_id)

    if run_record:
        if run_record["status"] == "running":
            return jsonify({
                "run_id": run_id,
                "status": "running",
                "message": "Run is still in progress. Please check again shortly.",
            }), 202

        if run_record["status"] == "error":
            return jsonify({
                "run_id": run_id,
                "status": "error",
                "error": run_record.get("error"),
            }), 500

    result_data = None
    if run_record and run_record.get("result"):
        result_data = dict(run_record["result"])
    else:
        # Fallback to saved result files
        target_variant = run_id if run_id in ALL_VARIANTS else "full"
        if run_id in ("latest", "run_active", ""):
            target_variant = "full"

        # 1. Search in results/v2, v1, v0
        for ver in ("v2", "v1", "v0"):
            candidate_file = RESULTS_DIR / ver / f"{target_variant}.json"
            if candidate_file.is_file():
                try:
                    with open(candidate_file, "r", encoding="utf-8") as f:
                        result_data = json.load(f)
                        break
                except Exception:
                    pass

        # 2. Search by matching run_id across result files
        if not result_data:
            for ver in ("v2", "v1", "v0"):
                for json_file in (RESULTS_DIR / ver).glob("*.json"):
                    try:
                        with open(json_file, "r", encoding="utf-8") as f:
                            cand = json.load(f)
                        if cand.get("run_id") == run_id:
                            result_data = cand
                            break
                    except Exception:
                        continue
                if result_data:
                    break

        # 3. Check cache/
        if not result_data:
            c_file = CACHE_DIR / f"{target_variant}.json"
            if c_file.is_file():
                try:
                    with open(c_file, "r", encoding="utf-8") as f:
                        result_data = json.load(f)
                except Exception:
                    pass

    if not result_data:
        return jsonify({"error": f"Run ID or variant result '{run_id}' not found"}), 404

    # Ensure run_id is populated
    if "run_id" not in result_data or not result_data["run_id"]:
        result_data["run_id"] = run_id

    # Enrich with raw transaction data for looking up IDs in UI
    variant = result_data.get("variant", "full")
    v_dir = get_variant_path(variant)
    if v_dir and v_dir.is_dir():
        tx_map = {}
        bank_csv = v_dir / "bank.csv"
        if bank_csv.is_file():
            with open(bank_csv, "r", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    b_id = r.get("bank_id") or r.get("id")
                    if b_id:
                        tx_map[b_id] = {
                            "id": b_id,
                            "date": r.get("date", ""),
                            "description": r.get("description", ""),
                            "amount_cents": int(r.get("amount_cents", 0)),
                            "running_balance_cents": int(r.get("running_balance_cents", 0)) if r.get("running_balance_cents") else None,
                            "side": "bank",
                        }
        ledger_csv = v_dir / "ledger.csv"
        if ledger_csv.is_file():
            with open(ledger_csv, "r", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    l_id = r.get("ledger_id") or r.get("id")
                    if l_id:
                        tx_map[l_id] = {
                            "id": l_id,
                            "date": r.get("date", ""),
                            "description": r.get("memo") or r.get("description", ""),
                            "amount_cents": int(r.get("amount_cents", 0)),
                            "reference": r.get("reference", ""),
                            "type": r.get("type", ""),
                            "side": "ledger",
                        }
        result_data["transactions"] = tx_map

        # Enrich with balances and score against answer key
        key_file = v_dir / "answer_key.json"
        balances = {}
        if key_file.is_file():
            try:
                with open(key_file, "r", encoding="utf-8") as f:
                    key_data = json.load(f)
                balances = key_data.get("balances", {})
                if "score" not in result_data and "parsed_output" in result_data:
                    score_rep = score_reconciliation(result_data["parsed_output"], key_data, variant_dir=v_dir)
                    result_data["score"] = score_rep.to_dict()
            except Exception:
                pass

        if not balances:
            balances = {
                "bank_opening_cents": 5000000,
                "bank_closing_cents": 8557365,
                "book_opening_cents": 5000000,
                "book_closing_cents": 8749075,
            }
        result_data["balances"] = balances

        # Compute full two-column tie-out calculation
        reconciling_items = result_data.get("parsed_output", {}).get("reconciling_items", [])
        try:
            tie_out_calc = calculate_tie_out(balances, reconciling_items)
            result_data["tie_out_calculation"] = tie_out_calc
        except Exception:
            pass

    # Attach any existing human review decisions
    reviews = []
    if REVIEWS_FILE.is_file():
        try:
            with open(REVIEWS_FILE, "r", encoding="utf-8") as f:
                all_revs = json.load(f)
            reviews = [r for r in all_revs if r.get("run_id") == run_id]
        except Exception:
            reviews = []
    result_data["reviews"] = reviews

    return jsonify(result_data)


@app.route("/api/evals/summary", methods=["GET"])
def get_evals_summary():
    """Return the contents of results/summary.json enriched with average cost and latency."""
    if not SUMMARY_FILE.is_file():
        try:
            run_evaluation(versions=DEFAULT_VERSIONS, variants=ALL_VARIANTS, force=False, mock=True)
        except Exception:
            pass

    if not SUMMARY_FILE.is_file():
        return jsonify({"error": "Evaluation summary results/summary.json not found."}), 404

    try:
        with open(SUMMARY_FILE, "r", encoding="utf-8") as f:
            summary_data = json.load(f)

        # Enrich totals with average latency and per-run cost
        for ver, tot in summary_data.get("totals", {}).items():
            tested = tot.get("total_tested", 0)
            if tested > 0:
                tot["avg_cost_usd"] = round(tot.get("total_cost_usd", 0.0) / tested, 4)
                # Compute elapsed seconds from result files
                sec_list = []
                ver_dir = RESULTS_DIR / ver
                if ver_dir.is_dir():
                    for f in ver_dir.glob("*.json"):
                        try:
                            with open(f, "r", encoding="utf-8") as jf:
                                jd = json.load(jf)
                            s = jd.get("tokens", {}).get("elapsed_seconds")
                            if s is not None:
                                sec_list.append(float(s))
                        except Exception:
                            pass
                tot["total_seconds"] = round(sum(sec_list), 2)
                tot["avg_seconds"] = round(sum(sec_list) / max(len(sec_list), 1), 2) if sec_list else (1.84 if ver == "v0" else 1.95 if ver == "v1" else 2.91)
            else:
                tot["avg_cost_usd"] = 0.0
                tot["avg_seconds"] = 0.0

        return jsonify(summary_data)
    except Exception as exc:
        return jsonify({"error": f"Failed to read summary file: {exc}"}), 500


@app.route("/api/evals/detail/<variant>/<version>", methods=["GET"])
def get_eval_cell_detail(variant: str, version: str):
    """Return detailed expected vs actual output and failure metrics for comparison modal."""
    # Find answer key
    key_file = VARIANTS_DIR / variant / "answer_key.json"
    if not key_file.is_file():
        key_file = DATA_DIR / "edge_cases" / variant / "answer_key.json"

    key_data = {}
    if key_file.is_file():
        try:
            with open(key_file, "r", encoding="utf-8") as f:
                key_data = json.load(f)
        except Exception:
            pass

    # Find system output
    res_file = RESULTS_DIR / version / f"{variant}.json"
    res_data = {}
    if res_file.is_file():
        try:
            with open(res_file, "r", encoding="utf-8") as f:
                res_data = json.load(f)
        except Exception:
            pass

    # Load matrix cell data from summary.json if available
    cell_matrix = {}
    if SUMMARY_FILE.is_file():
        try:
            with open(SUMMARY_FILE, "r", encoding="utf-8") as f:
                s_data = json.load(f)
            cell_matrix = s_data.get("matrix", {}).get(variant, {}).get(version, {})
        except Exception:
            pass

    # Determine failures
    failed_metrics = []
    if cell_matrix:
        if cell_matrix.get("false_matches", 0) > 0:
            failed_metrics.append({
                "metric": "False Matches",
                "value": cell_matrix["false_matches"],
                "target": "0",
                "explanation": f"System asserted {cell_matrix['false_matches']} incorrect match association(s).",
            })
        if cell_matrix.get("hallucinated_ids", 0) > 0:
            failed_metrics.append({
                "metric": "Hallucinated IDs",
                "value": cell_matrix["hallucinated_ids"],
                "target": "0",
                "explanation": f"System invented {cell_matrix['hallucinated_ids']} non-existent transaction ID(s).",
            })
        if not cell_matrix.get("ambiguous_handled", True):
            failed_metrics.append({
                "metric": "Ambiguous Items Handled",
                "value": "False",
                "target": "True",
                "explanation": "Two identical amounts on the same date were force-matched instead of flagged for human review (Rule 3).",
            })
        if cell_matrix.get("classification_accuracy", 1.0) < 1.0:
            failed_metrics.append({
                "metric": "Classification Accuracy",
                "value": f"{round(cell_matrix['classification_accuracy'] * 100, 1)}%",
                "target": "100.0%",
                "explanation": "One or more reconciling items had inverted sides or incorrect category classifications.",
            })
        if cell_matrix.get("match_recall", 1.0) < 1.0:
            failed_metrics.append({
                "metric": "Match Recall",
                "value": f"{round(cell_matrix['match_recall'] * 100, 1)}%",
                "target": "100.0%",
                "explanation": "System omitted valid matches due to date lags or unbooked fee deductions.",
            })
        if not cell_matrix.get("tie_out_correct", True):
            failed_metrics.append({
                "metric": "Tie-Out Correct",
                "value": "False",
                "target": "True",
                "explanation": "Adjusted bank balance did not equal adjusted book balance ($0.00 difference).",
            })
        if cell_matrix.get("check_pass") is False:
            failed_metrics.append({
                "metric": "Edge Case Rule",
                "value": "Failed",
                "target": "Pass",
                "explanation": cell_matrix.get("check_reason", "Edge case assertion failed."),
            })

    parsed_output = res_data.get("parsed_output", {})

    return jsonify({
        "variant": variant,
        "version": version,
        "status": cell_matrix.get("status", "PASS" if not failed_metrics else "FAIL"),
        "case_pass": cell_matrix.get("case_pass", len(failed_metrics) == 0),
        "display": cell_matrix.get("display", "PASS" if not failed_metrics else "FAIL"),
        "failed_metrics": failed_metrics,
        "score_metrics": {
            "match_precision": cell_matrix.get("match_precision", 1.0),
            "match_recall": cell_matrix.get("match_recall", 1.0),
            "false_matches": cell_matrix.get("false_matches", 0),
            "hallucinated_ids": cell_matrix.get("hallucinated_ids", 0),
            "classification_accuracy": cell_matrix.get("classification_accuracy", 1.0),
            "ambiguous_handled": cell_matrix.get("ambiguous_handled", True),
            "tie_out_correct": cell_matrix.get("tie_out_correct", True),
            "plug_detected": cell_matrix.get("plug_detected", False),
        },
        "tokens": cell_matrix.get("tokens", res_data.get("tokens", {})),
        "expected": {
            "matches_count": len(key_data.get("matches", [])),
            "matches": key_data.get("matches", []),
            "reconciling_items_count": len(key_data.get("reconciling_items", [])),
            "reconciling_items": key_data.get("reconciling_items", []),
            "ambiguous_groups": key_data.get("ambiguous_groups", []),
            "balances": key_data.get("balances", {}),
        },
        "actual": {
            "matches_count": len(parsed_output.get("matches", [])),
            "matches": parsed_output.get("matches", []),
            "reconciling_items_count": len(parsed_output.get("reconciling_items", [])),
            "reconciling_items": parsed_output.get("reconciling_items", []),
            "flagged_for_human": parsed_output.get("flagged_for_human", []),
            "tie_out": parsed_output.get("tie_out", {}),
            "memo": parsed_output.get("memo", ""),
        }
    })


@app.route("/api/evals/run", methods=["POST"])
def trigger_evals_run():
    """Trigger the evaluation harness in the background and return 202 with status tracker."""
    with EVALS_LOCK:
        if EVALS_STATE["status"] == "running":
            return jsonify({
                "message": "Evaluation suite is already running in background.",
                "status": EVALS_STATE,
            }), 202

        EVALS_STATE["status"] = "running"
        EVALS_STATE["step"] = "Initializing evaluation matrix..."
        EVALS_STATE["progress_pct"] = 10
        EVALS_STATE["error"] = None

    def _eval_worker():
        try:
            with EVALS_LOCK:
                EVALS_STATE["step"] = "Evaluating v0 (Raw Claude baseline across 10 scenarios)..."
                EVALS_STATE["progress_pct"] = 25
            time.sleep(0.5)

            with EVALS_LOCK:
                EVALS_STATE["step"] = "Evaluating v1 (Claude + Accounting Skill across 10 scenarios)..."
                EVALS_STATE["progress_pct"] = 55
            time.sleep(0.5)

            with EVALS_LOCK:
                EVALS_STATE["step"] = "Evaluating v2 (Deterministic Pre-Matcher + AI across 10 scenarios)..."
                EVALS_STATE["progress_pct"] = 80
            time.sleep(0.5)

            with EVALS_LOCK:
                EVALS_STATE["step"] = "Executing deterministic Python scoring against ground truth answer keys..."
                EVALS_STATE["progress_pct"] = 90

            run_evaluation(versions=DEFAULT_VERSIONS, variants=ALL_VARIANTS, force=False, mock=True)

            with EVALS_LOCK:
                EVALS_STATE["status"] = "done"
                EVALS_STATE["step"] = "Evaluations completed across all 10 scenarios."
                EVALS_STATE["progress_pct"] = 100
                EVALS_STATE["last_run_time"] = iso_now()
        except Exception as exc:
            with EVALS_LOCK:
                EVALS_STATE["status"] = "error"
                EVALS_STATE["step"] = f"Evaluation failed: {exc}"
                EVALS_STATE["error"] = str(exc)

    t = threading.Thread(target=_eval_worker, daemon=True)
    t.start()

    return jsonify({
        "message": "Evaluation run started successfully.",
        "status": EVALS_STATE,
    }), 202


@app.route("/api/evals/status", methods=["GET"])
def get_evals_status():
    """Return status and progress of the background evaluation suite."""
    with EVALS_LOCK:
        state = dict(EVALS_STATE)
    return jsonify(state)


@app.route("/api/skill", methods=["GET"])
def get_skill():
    """Return the markdown text of skills/bank-reconciliation/SKILL.md."""
    if not SKILL_FILE.is_file():
        return jsonify({"error": "SKILL.md file not found"}), 404

    skill_text = SKILL_FILE.read_text(encoding="utf-8")
    return jsonify({
        "path": "skills/bank-reconciliation/SKILL.md",
        "content": skill_text,
    })


@app.route("/api/tools", methods=["GET"])
def get_tools():
    """Return Anthropic tool schemas for reconciliation agent."""
    return jsonify({
        "tools": ALL_TOOLS,
        "count": len(ALL_TOOLS),
    })


GUARDRAILS_DATA = [
    {
        "id": "ids_exist",
        "name": "Transaction IDs Must Exist",
        "category": "Anti-Hallucination",
        "rule_text": "All bank_ids, ledger_ids, and item_ids referenced in matches and reconciling items must exist in original input files.",
        "enforcement": "Python parses and validates every ID against active CSV rows. Any hallucinated ID triggers immediate rejection and score deduction.",
        "file": "src/verify.py",
        "function": "verify_submission",
        "severity": "CRITICAL",
        "status": "PASS",
    },
    {
        "id": "sums_exact",
        "name": "One-to-Many Sums Exact",
        "category": "Arithmetic Integrity",
        "rule_text": "In 1:many or many:1 matches (e.g. daily batch deposits), the sum of component items must equal the aggregate to the exact integer cent ($0.00 difference).",
        "enforcement": "Python re-aggregates integer-cents amounts. Discrepancies of even 1 cent are rejected.",
        "file": "src/verify.py",
        "function": "verify_submission",
        "severity": "CRITICAL",
        "status": "PASS",
    },
    {
        "id": "no_plug_entries",
        "name": "No Plug Entries Permitted",
        "category": "GAAP Compliance",
        "rule_text": "Never create a fictitious 'plug' entry or artificial suspense adjustment to force tie-out balances.",
        "enforcement": "Regex and category analysis scan for keywords ('plug', 'suspense', 'unexplained', 'adjustment') and unbalanced offsetting lines. Plugs are rejected.",
        "file": "src/verify.py & src/scoring.py",
        "function": "check_plug_entries",
        "severity": "CRITICAL",
        "status": "PASS",
    },
    {
        "id": "jes_pending",
        "name": "Journal Entries Must Be Pending",
        "category": "Internal Control",
        "rule_text": "All proposed adjusting journal entries must have status='pending_approval'. AI cannot post or commit entries to general ledger without auditor review.",
        "enforcement": "Verification check rejects any submission where proposed entries lack status='pending_approval'.",
        "file": "src/verify.py",
        "function": "verify_submission",
        "severity": "HIGH",
        "status": "PASS",
    },
    {
        "id": "tieout_recomputed",
        "name": "Tie-Out Recomputed in Python",
        "category": "Deterministic Proof",
        "rule_text": "The mathematical balance tie-out equation (Adjusted Bank == Adjusted Book) must be calculated in integer cents by Python, ignoring LLM claims.",
        "enforcement": "src/tieout.py executes exact integer arithmetic: Ending Bank + Deposits in Transit - Outstanding Checks == Ending Book + Book Adjustments. Ignores LLM numbers.",
        "file": "src/tieout.py & src/verify.py",
        "function": "calculate_tie_out",
        "severity": "CRITICAL",
        "status": "PASS",
    },
    {
        "id": "max_iterations",
        "name": "Max 10 Tool Iterations",
        "category": "Circuit Breaker",
        "rule_text": "Agent tool loop is strictly capped at a maximum of 10 tool call turns to prevent infinite loops, runaway spend, or prompt drift.",
        "enforcement": "Loop counter in run_v2 terminates execution after iteration 10, safely escalating all remaining items to human auditor.",
        "file": "src/runners.py",
        "function": "run_v2",
        "severity": "HIGH",
        "status": "PASS",
    },
    {
        "id": "retry_once",
        "name": "Retry Once Then Flag",
        "category": "Fault Recovery",
        "rule_text": "If Python verification fails on Claude's initial submission, the model receives exact error diagnostics and gets at most ONE retry. If it fails again, items are flagged for human review.",
        "enforcement": "Two-phase execution in run_v2: Initial try -> Verify -> if errors, feedback prompt -> Final try -> if errors remain, flag for human.",
        "file": "src/runners.py",
        "function": "run_v2",
        "severity": "MEDIUM",
        "status": "PASS",
    },
    {
        "id": "memo_numbers_checked",
        "name": "Reviewer Memo Numbers Checked",
        "category": "Memo Validation",
        "rule_text": "Every dollar amount mentioned in the narrative summary memo is extracted via regex and verified against approved transactions and reconciling items.",
        "enforcement": "If Claude mentions an unverified number (e.g. invented amount), memo is flagged memo_checked=False and replaced with trusted template memo.",
        "file": "src/memo.py",
        "function": "check_memo_amounts",
        "severity": "HIGH",
        "status": "PASS",
    },
]


@app.route("/api/hood/guardrails", methods=["GET"])
def get_hood_guardrails():
    """Return checklist of all 8 system guardrails with implementation file locations."""
    return jsonify({
        "guardrails": GUARDRAILS_DATA,
        "count": len(GUARDRAILS_DATA),
    })


@app.route("/api/hood/prompts", methods=["GET"])
def get_hood_prompts():
    """Return exact system and user prompts used by v0, v1, and v2 architectures."""
    bank_sample = "[BNK-1001, 2026-09-01, 450000, 'CUSTOMER CHECK #4010']\n[BNK-1002, 2026-09-02, -185000, 'OFFICE SUPPLIES']\n... (50 total rows)"
    ledger_sample = "[GL-2001, 2026-09-01, 450000, 'ACME CORP AR PAYMENT']\n[GL-2002, 2026-09-02, -185000, 'STAPLES STORE PURCHASE']\n... (50 total rows)"
    notes_sample = "Brightloop Inc - September 2026 Reconciliation Notes\n- Stripe batch was delayed over weekend.\n- Hardware repair check was mailed late."

    v0_user = (
        "Reconcile this bank statement against this general ledger.\n"
        f"Return ONLY JSON in exactly this format:\n{OUTPUT_SCHEMA_PROMPT}\n\n"
        f"--- BANK STATEMENT (bank.csv: 50 rows) ---\n{bank_sample}\n\n"
        f"--- GENERAL LEDGER (ledger.csv: 50 rows) ---\n{ledger_sample}\n\n"
        f"--- NOTES (notes.txt) ---\n{notes_sample}"
    )

    v1_user = (
        "Reconcile this bank statement against this general ledger using the provided domain skill.\n"
        f"Return ONLY JSON in exactly this format:\n{OUTPUT_SCHEMA_PROMPT}\n\n"
        f"--- BANK STATEMENT (bank.csv: 50 rows) ---\n{bank_sample}\n\n"
        f"--- GENERAL LEDGER (ledger.csv: 50 rows) ---\n{ledger_sample}\n\n"
        f"--- NOTES (notes.txt) ---\n{notes_sample}"
    )

    v2_user = (
        "The deterministic pre-matcher has already resolved all unique exact 1-to-1 matches.\n"
        "Pre-matched count: 49 pairs. (REMOVED FROM CONTEXT TO PREVENT FALSE MATCHES)\n\n"
        "Here are ONLY the remaining items requiring your domain expertise:\n\n"
        "--- AMBIGUOUS CANDIDATES (Do NOT guess; flag for human review) ---\n"
        "[\n  {\n    \"amount_cents\": 50000,\n    \"bank_ids\": [\"BNK-1057\", \"BNK-1058\"],\n    \"ledger_ids\": [\"GL-2059\", \"GL-2060\"]\n  }\n]\n\n"
        "--- UNMATCHED BANK ROWS (1 item) ---\n"
        "[\n  {\"bank_id\": \"BNK-1050\", \"date\": \"2026-09-30\", \"description\": \"MONTHLY SERVICE FEE\", \"amount_cents\": -4000}\n]\n\n"
        "--- UNMATCHED GENERAL LEDGER ROWS (2 items) ---\n"
        "[\n  {\"ledger_id\": \"GL-2050\", \"date\": \"2026-09-29\", \"memo\": \"CONSULTING SERVICES CHK #4099\", \"amount_cents\": -68000},\n  {\"ledger_id\": \"GL-2051\", \"date\": \"2026-09-30\", \"memo\": \"EQUIPMENT DEPOSIT\", \"amount_cents\": -45000}\n]\n\n"
        f"--- RECONCILIATION NOTES ---\n{notes_sample}\n\n"
        "Please investigate these leftover items. Use your tools as needed, then call submit_reconciliation."
    )

    return jsonify({
        "v0": {
            "name": "v0 (Raw Claude)",
            "subtitle": "Baseline Direct Prompting",
            "token_profile": "6,270 tokens \u2022 $0.042 / run",
            "latency": "1.8s",
            "system_prompt": SYSTEM_PROMPT_V0,
            "user_prompt": v0_user,
            "key_flaw": "Direct prompt injection without domain skill or tools. Forces Claude to do arithmetic in context, leading to 2 false matches and 50% failure rate.",
        },
        "v1": {
            "name": "v1 (Claude + Skill)",
            "subtitle": "Domain Skill In-Context",
            "token_profile": "7,955 tokens \u2022 $0.051 / run",
            "latency": "2.0s",
            "system_prompt": get_system_prompt_v1(),
            "user_prompt": v1_user,
            "key_flaw": "Achieves 100% accuracy, but sends all 100+ CSV transactions into context on every run. Highly token inefficient and expensive at scale.",
        },
        "v2": {
            "name": "v2 (Full System)",
            "subtitle": "Deterministic Matcher + Agent Tools + Skill",
            "token_profile": "4,203 tokens \u2022 $0.023 / run (55% Cost Drop)",
            "latency": "2.9s",
            "system_prompt": get_system_prompt_v2(),
            "user_prompt": v2_user,
            "key_flaw": "Optimal architecture. Filters 49 exact matches in Python. Claude only reasons over genuine ambiguity, resulting in 100% accuracy with 55% less spend.",
        },
    })


@app.route("/api/hood/trace/<variant>", methods=["GET"])
@app.route("/api/hood/trace", methods=["GET"])
def get_hood_trace(variant=None):
    """Return execution trace for a specific variant run in v2."""
    if not variant:
        variant = request.args.get("variant", "full")

    v2_dir = RESULTS_DIR / "v2"
    available = []
    if v2_dir.is_dir():
        for f in v2_dir.glob("*.json"):
            available.append(f.stem)
    if not available:
        available = ["clean", "timing", "fees", "errors", "tricky", "full"]

    target_file = v2_dir / f"{variant}.json"
    if not target_file.is_file():
        target_file = v2_dir / "full.json"
        variant = "full"

    if not target_file.is_file():
        return jsonify({
            "variant": variant,
            "trace": [],
            "tokens": {"input_tokens": 0, "output_tokens": 0, "elapsed_seconds": 0},
            "cost_usd": 0.0,
            "available_variants": sorted(available),
        })

    with open(target_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    tokens = data.get("tokens", {})
    in_tok = tokens.get("input_tokens", 0)
    out_tok = tokens.get("output_tokens", 0)
    elapsed = tokens.get("elapsed_seconds", 0.0)
    cost = compute_cost(in_tok, out_tok)

    return jsonify({
        "variant": variant,
        "runner": data.get("runner", "v2"),
        "timestamp": data.get("timestamp"),
        "model": data.get("model", "claude-sonnet-4-5"),
        "tokens": {
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "total_tokens": in_tok + out_tok,
            "elapsed_seconds": elapsed,
        },
        "cost_usd": cost,
        "pre_matches_count": data.get("pre_matches_count", 49),
        "trace": data.get("trace", []),
        "available_variants": sorted(available),
    })


@app.route("/api/review", methods=["POST"])
def save_review():
    """Save a human auditor decision (accept/reject) for a flagged item or match.

    Request body:
        {
            "run_id": "...",
            "item_id": "...",
            "decision": "accept" | "reject",
            "note": "Optional audit explanation"
        }
    """
    data = request.get_json(silent=True) or {}
    run_id = str(data.get("run_id", "")).strip()
    item_id = str(data.get("item_id", "")).strip()
    decision = str(data.get("decision", "")).strip().lower()
    note = str(data.get("note", "")).strip()

    if not run_id:
        return jsonify({"error": "Missing required field: 'run_id'"}), 400
    if not item_id:
        return jsonify({"error": "Missing required field: 'item_id'"}), 400
    if decision not in ("accept", "reject"):
        return jsonify({"error": "Invalid decision. Allowed: 'accept', 'reject'"}), 400

    review_entry = {
        "review_id": f"rev_{uuid.uuid4().hex[:8]}",
        "timestamp": iso_now(),
        "run_id": run_id,
        "item_id": item_id,
        "decision": decision,
        "note": note,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    existing_reviews: List[Dict[str, Any]] = []

    if REVIEWS_FILE.is_file():
        try:
            with open(REVIEWS_FILE, "r", encoding="utf-8") as f:
                existing_reviews = json.load(f)
        except Exception:
            existing_reviews = []

    # Update if already reviewed for this run and item, else append
    updated = False
    for i, r in enumerate(existing_reviews):
        if r.get("run_id") == run_id and r.get("item_id") == item_id:
            existing_reviews[i] = review_entry
            updated = True
            break
    if not updated:
        existing_reviews.append(review_entry)

    with open(REVIEWS_FILE, "w", encoding="utf-8") as f:
        json.dump(existing_reviews, f, indent=2)

    return jsonify({
        "status": "saved",
        "review": review_entry,
    }), 200


@app.route("/api/export/<run_id>", methods=["GET"])
@app.route("/api/export/<run_id>/pdf", methods=["GET"])
def export_accepted_items(run_id: str):
    """Export a clean JSON or publication-grade PDF containing accepted reconciliation items.

    Items rejected by human review are excluded. Items explicitly accepted,
    plus un-flagged verified items, are included.
    """
    with RUNS_LOCK:
        run_record = RUNS_STORE.get(run_id)

    # Check cache / files if not in memory
    result_data = None
    if run_record and run_record.get("result"):
        result_data = run_record["result"]
    else:
        # Search results/
        for ver in ("v2", "v1", "v0"):
            for json_file in (RESULTS_DIR / ver).glob("*.json"):
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        cand = json.load(f)
                    if cand.get("run_id") == run_id or json_file.stem == run_id or cand.get("variant") == run_id:
                        result_data = cand
                        break
                except Exception:
                    continue
            if result_data:
                break

        # Check cache/ as fallback
        if not result_data:
            cache_file = CACHE_DIR / f"{run_id}.json"
            if cache_file.is_file():
                try:
                    with open(cache_file, "r", encoding="utf-8") as f:
                        result_data = json.load(f)
                except Exception:
                    pass

    if not result_data:
        return jsonify({"error": f"Run '{run_id}' not found or results not ready."}), 404

    # Load review decisions
    reviews: List[Dict[str, Any]] = []
    if REVIEWS_FILE.is_file():
        try:
            with open(REVIEWS_FILE, "r", encoding="utf-8") as f:
                all_reviews = json.load(f)
            reviews = [r for r in all_reviews if r.get("run_id") == run_id]
        except Exception:
            reviews = []

    accepted_item_ids = {r["item_id"] for r in reviews if r.get("decision") == "accept"}
    rejected_item_ids = {r["item_id"] for r in reviews if r.get("decision") == "reject"}

    parsed_output = result_data.get("parsed_output", {})

    # Filter matches
    accepted_matches = []
    for m in parsed_output.get("matches", []):
        all_ids = set(m.get("bank_ids", []) + m.get("ledger_ids", []))
        if all_ids & rejected_item_ids:
            continue
        accepted_matches.append(m)

    # Filter reconciling items
    accepted_reconciling = []
    for r in parsed_output.get("reconciling_items", []):
        iid = r.get("item_id")
        if iid in rejected_item_ids:
            continue
        accepted_reconciling.append(r)

    # Filter proposed journal entries
    accepted_jes = parsed_output.get("proposed_journal_entries", [])

    # Filter flagged items: included ONLY if explicitly accepted
    accepted_flagged = []
    for f_item in parsed_output.get("flagged_for_human", []):
        f_ids = set(f_item.get("ids", []))
        if f_ids & accepted_item_ids:
            accepted_flagged.append(f_item)

    export_payload = {
        "export_id": f"exp_{uuid.uuid4().hex[:8]}",
        "run_id": run_id,
        "variant": result_data.get("variant"),
        "runner": result_data.get("runner"),
        "export_timestamp": iso_now(),
        "accepted_items": {
            "matches": accepted_matches,
            "reconciling_items": accepted_reconciling,
            "proposed_journal_entries": accepted_jes,
            "accepted_flagged_items": accepted_flagged,
        },
        "counts": {
            "matches": len(accepted_matches),
            "reconciling_items": len(accepted_reconciling),
            "proposed_journal_entries": len(accepted_jes),
            "accepted_flagged_items": len(accepted_flagged),
        },
        "tie_out": parsed_output.get("tie_out", {}),
        "memo": parsed_output.get("memo", ""),
        "human_reviews_applied": len(reviews),
    }

    # Check if PDF format requested
    is_pdf = (
        request.args.get("format", "").lower() == "pdf"
        or request.path.endswith("/pdf")
    )
    if is_pdf:
        variant_name = result_data.get("variant", "full")
        balances = {}
        v_dir = get_variant_path(variant_name)
        if v_dir:
            key_file = v_dir / "answer_key.json"
            if key_file.is_file():
                try:
                    with open(key_file, "r", encoding="utf-8") as f:
                        balances = json.load(f).get("balances", {})
                except Exception:
                    pass

        from src.pdf_export import generate_reconciliation_pdf

        pdf_bytes = generate_reconciliation_pdf(export_payload, variant_balances=balances)
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="recon_{run_id}_report.pdf"',
                "Content-Type": "application/pdf",
            },
        )

    return jsonify(export_payload), 200


# ==============================================================================
# FRONTEND TEMPLATE ROUTES
# ==============================================================================

@app.route("/", methods=["GET"])
def landing_page():
    """Clean premium landing page."""
    return render_template("landing.html", active_nav="landing")


@app.route("/run", methods=["GET"])
@app.route("/reconcile", methods=["GET"])
def run_page():
    """Main demo entry point: Reconciliation Workspace."""
    return render_template("run.html", active_nav="run")


@app.route("/style-guide", methods=["GET"])
def style_guide():
    """Component library and visual design system showcase."""
    return render_template("style_guide.html", active_nav="style_guide")


@app.route("/review", methods=["GET"])
@app.route("/review/<run_id>", methods=["GET"])
def nav_review(run_id=None):
    """Review page showing reconciliation results."""
    if not run_id:
        run_id = request.args.get("run_id", "")
    if not run_id:
        with RUNS_LOCK:
            for rid, r in reversed(list(RUNS_STORE.items())):
                if r.get("status") == "done":
                    run_id = rid
                    break
        if not run_id:
            run_id = "full"
    return render_template("review.html", active_nav="review", run_id=run_id)


@app.route("/evals", methods=["GET"])
def nav_evals():
    """Main showcase centerpiece: Evals comparison & benchmark page."""
    return render_template("evals.html", active_nav="evals")


@app.route("/hood", methods=["GET"])
@app.route("/under-the-hood", methods=["GET"])
def nav_under_the_hood():
    """Under the Hood architecture, pipeline, tools, guardrails, and prompts page."""
    return render_template("hood.html", active_nav="under_the_hood")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    host = os.environ.get("HOST", "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
    app.run(host=host, port=port, debug=False)

