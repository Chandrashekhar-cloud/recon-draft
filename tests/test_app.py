"""Unit tests for Flask API backend in app/app.py."""

import json
from pathlib import Path
import time
import pytest

from app.app import app, RUNS_STORE, REVIEWS_FILE


@pytest.fixture
def client():
    """Create Flask test client."""
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_get_variants(client):
    """GET /api/variants returns list of variants with metadata."""
    res = client.get("/api/variants")
    assert res.status_code == 200
    data = res.get_json()
    assert "variants" in data
    assert data["count"] >= 6

    clean_var = next((v for v in data["variants"] if v["name"] == "clean"), None)
    assert clean_var is not None
    assert clean_var["bank_rows"] > 0
    assert clean_var["ledger_rows"] > 0
    assert "traps" in clean_var
    assert "description" in clean_var


def test_get_variant_data_found(client):
    """GET /api/variant/<name>/data returns rows and notes."""
    res = client.get("/api/variant/clean/data")
    assert res.status_code == 200
    data = res.get_json()
    assert data["variant"] == "clean"
    assert len(data["bank_rows"]) > 0
    assert len(data["ledger_rows"]) > 0
    assert "notes" in data


def test_get_variant_data_not_found(client):
    """GET /api/variant/<name>/data returns 404 for unknown variant."""
    res = client.get("/api/variant/unknown_variant_xyz/data")
    assert res.status_code == 404
    data = res.get_json()
    assert "error" in data


def test_post_run_validation(client):
    """POST /api/run validates variant and mode."""
    # Missing variant
    res1 = client.post("/api/run", json={"mode": "replay"})
    assert res1.status_code == 400

    # Invalid mode
    res2 = client.post("/api/run", json={"variant": "clean", "mode": "invalid_mode"})
    assert res2.status_code == 400

    # Unknown variant
    res3 = client.post("/api/run", json={"variant": "bogus_variant", "mode": "replay"})
    assert res3.status_code == 404


def test_post_run_and_status_replay(client):
    """POST /api/run with mode 'replay' executes in background and returns status and result."""
    res = client.post("/api/run", json={"variant": "clean", "mode": "replay"})
    assert res.status_code == 202
    data = res.get_json()
    assert "run_id" in data
    run_id = data["run_id"]

    # Poll status until done (usually instantaneous in replay)
    max_wait = 3.0
    start = time.time()
    status_data = None
    while time.time() - start < max_wait:
        status_res = client.get(f"/api/run/{run_id}/status")
        assert status_res.status_code == 200
        status_data = status_res.get_json()
        if status_data["status"] == "done":
            break
        time.sleep(0.05)

    assert status_data is not None
    assert status_data["status"] == "done"
    steps = [s["step"] for s in status_data["steps"]]
    assert "matching" in steps
    assert "done" in steps
    for s in status_data["steps"]:
        assert "timestamp" in s

    # Get result
    res_result = client.get(f"/api/run/{run_id}/result")
    assert res_result.status_code == 200
    res_data = res_result.get_json()
    assert res_data["variant"] == "clean"
    assert "parsed_output" in res_data
    assert "score" in res_data
    assert res_data["score"]["case_pass"] is True


def test_get_evals_summary(client):
    """GET /api/evals/summary returns results/summary.json content."""
    res = client.get("/api/evals/summary")
    assert res.status_code == 200
    data = res.get_json()
    assert "versions" in data or "matrix" in data


def test_get_skill(client):
    """GET /api/skill returns SKILL.md text."""
    res = client.get("/api/skill")
    assert res.status_code == 200
    data = res.get_json()
    assert "content" in data
    assert "bank-reconciliation" in data["content"].lower() or "bank reconciliation" in data["content"].lower()


def test_get_tools(client):
    """GET /api/tools returns tool schemas."""
    res = client.get("/api/tools")
    assert res.status_code == 200
    data = res.get_json()
    assert "tools" in data
    assert data["count"] >= 4
    tool_names = [t["name"] for t in data["tools"]]
    assert "get_item" in tool_names
    assert "submit_reconciliation" in tool_names


def test_post_review_and_export(client):
    """POST /api/review saves human decision and GET /api/export/<run_id> filters accepted items."""
    # First, start a replay run to have a valid run_id
    run_res = client.post("/api/run", json={"variant": "full", "mode": "replay"})
    assert run_res.status_code == 202
    run_id = run_res.get_json()["run_id"]

    # Wait for completion
    time.sleep(0.3)

    # Post a human review decision
    rev_payload = {
        "run_id": run_id,
        "item_id": "BNK-1057",
        "decision": "accept",
        "note": "Auditor verified transaction documentation matches invoice #801.",
    }
    rev_res = client.post("/api/review", json=rev_payload)
    assert rev_res.status_code == 200
    rev_data = rev_res.get_json()
    assert rev_data["status"] == "saved"
    assert rev_data["review"]["decision"] == "accept"

    # Export accepted items
    exp_res = client.get(f"/api/export/{run_id}")
    assert exp_res.status_code == 200
    exp_data = exp_res.get_json()
    assert exp_data["run_id"] == run_id
    assert "accepted_items" in exp_data
    assert "matches" in exp_data["accepted_items"]
    assert exp_data["human_reviews_applied"] >= 1
