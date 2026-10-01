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
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

from flask import Flask, jsonify, request

from evals.edge_cases import EDGE_CASE_NAMES, ensure_edge_case_data
import src.runners as runners_module
from src.scoring import score_reconciliation
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

    return jsonify({
        "variant": name,
        "bank_rows": bank_rows,
        "bank_count": len(bank_rows),
        "ledger_rows": ledger_rows,
        "ledger_count": len(ledger_rows),
        "notes": notes_text,
    })


def _execute_run_pipeline(run_id: str, variant: str, mode: str) -> None:
    """Background worker function executing the requested reconciliation pipeline."""
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
    """Get the full reconciliation result JSON including trace and objective score."""
    with RUNS_LOCK:
        run_record = RUNS_STORE.get(run_id)

    if not run_record:
        return jsonify({"error": f"Run ID '{run_id}' not found"}), 404

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

    return jsonify(run_record["result"])


@app.route("/api/evals/summary", methods=["GET"])
def get_evals_summary():
    """Return the contents of results/summary.json."""
    if not SUMMARY_FILE.is_file():
        return jsonify({"error": "Evaluation summary results/summary.json not found."}), 404

    try:
        with open(SUMMARY_FILE, "r", encoding="utf-8") as f:
            summary_data = json.load(f)
        return jsonify(summary_data)
    except Exception as exc:
        return jsonify({"error": f"Failed to read summary file: {exc}"}), 500


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
def export_accepted_items(run_id: str):
    """Export a clean JSON containing only accepted reconciliation items.

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
                    if cand.get("run_id") == run_id:
                        result_data = cand
                        break
                except Exception:
                    continue
            if result_data:
                break

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

    return jsonify(export_payload), 200


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
