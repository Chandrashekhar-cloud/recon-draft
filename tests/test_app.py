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

    # Export accepted items as PDF via /pdf path
    pdf_res = client.get(f"/api/export/{run_id}/pdf")
    assert pdf_res.status_code == 200
    assert pdf_res.mimetype == "application/pdf"
    assert len(pdf_res.data) > 1000
    assert pdf_res.data.startswith(b"%PDF")

    # Export accepted items as PDF via ?format=pdf query param
    pdf_res2 = client.get(f"/api/export/{run_id}?format=pdf")
    assert pdf_res2.status_code == 200
    assert pdf_res2.mimetype == "application/pdf"
    assert pdf_res2.data.startswith(b"%PDF")


def test_run_page_renders(client):
    """GET / and GET /run render the Run page with hero, steps, and options."""
    for path in ("/", "/run"):
        res = client.get(path)
        assert res.status_code == 200
        html = res.get_data(as_text=True)
        assert "Bank reconciliation, drafted in minutes" in html
        assert "Choose a client month" in html
        assert "Preview the data" in html
        assert "Choose how to run" in html
        assert "Run reconciliation" in html


def test_style_guide_and_static_assets(client):
    """GET /style-guide renders the component showcase and CSS/JS are served."""
    # Style guide renders with 200 and contains core components
    sg_res = client.get("/style-guide")
    assert sg_res.status_code == 200
    html = sg_res.get_data(as_text=True)
    assert "Recon Draft" in html
    assert "Fintech Component Library" in html
    assert "Brightloop Inc" in html
    assert "Draft output. A human reviews everything." in html
    assert "Step Progress Bar" in html
    assert "Reconciliation Ledger Table" in html

    # CSS is accessible
    css_res = client.get("/static/css/app.css")
    assert css_res.status_code == 200
    css_text = css_res.get_data(as_text=True)
    assert "--color-primary: #0F766E;" in css_text
    assert "--font-mono:" in css_text
    assert "[data-theme=\"dark\"]" in css_text

    # JS is accessible
    js_res = client.get("/static/js/app.js")
    assert js_res.status_code == 200
    js_text = js_res.get_data(as_text=True)
    assert "toggleTheme" in js_text


def test_review_page_renders(client):
    """GET /review and GET /review/<run_id> render the Review page with all key components."""
    # Test default /review route
    res = client.get("/review")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Auditor Review" in html
    assert "Mathematical Tie-Out Proof" in html
    assert "Computed in Python, not by AI" in html
    assert "Flagged: two identical amounts, a human must decide" in html
    assert "Needs Your Review" in html
    assert "Matched" in html
    assert "Reconciling Items" in html
    assert "Journal Entries" in html
    assert "Reviewer Memo" in html
    assert "Show Answer Key Score" in html
    assert "Export Approved Items" in html
    assert "Export PDF Report" in html

    # Test /review/<run_id> with full variant run
    run_res = client.post("/api/run", json={"variant": "full", "mode": "replay"})
    assert run_res.status_code == 202
    run_id = run_res.get_json()["run_id"]
    time.sleep(0.3)

    res_run = client.get(f"/review/{run_id}")
    assert res_run.status_code == 200
    html_run = res_run.get_data(as_text=True)
    assert run_id in html_run
    assert "Computed in Python, not by AI" in html_run


def test_evals_page_renders(client):
    """GET /evals renders the Evals benchmark page with all showcase sections."""
    res = client.get("/evals")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Evaluation &amp; Architecture Benchmarks" in html or "Evaluation & Architecture Benchmarks" in html
    assert "v0 &bull; Raw Claude" in html or "v0 • Raw Claude" in html or "Raw Claude" in html
    assert "v1 &bull; Claude + Skill" in html or "Claude + Skill" in html
    assert "v2 &bull; Full System" in html or "Full System" in html
    assert "Pass Rate by Architecture" in html
    assert "Total False Matches" in html
    assert "Comprehensive Scenario Matrix" in html
    assert "What the Evals Caught" in html
    assert "How the Golden Set Was Made" in html
    assert "Run All Evals" in html
    assert "Scored by deterministic Python. No AI is used to grade." in html


def test_evals_summary_enriched(client):
    """GET /api/evals/summary returns enriched matrix with average cost and latency."""
    res = client.get("/api/evals/summary")
    assert res.status_code == 200
    data = res.get_json()
    assert "totals" in data
    assert "matrix" in data
    for ver in ("v0", "v1", "v2"):
        if ver in data["totals"]:
            tot = data["totals"][ver]
            assert "pass_rate" in tot
            assert "avg_cost_usd" in tot
            assert "avg_seconds" in tot


def test_evals_cell_detail(client):
    """GET /api/evals/detail/<variant>/<version> returns diff and metric details."""
    res = client.get("/api/evals/detail/tricky/v0")
    assert res.status_code == 200
    data = res.get_json()
    assert data["variant"] == "tricky"
    assert data["version"] == "v0"
    assert "expected" in data
    assert "actual" in data
    assert "score_metrics" in data


def test_evals_run_and_status(client):
    """POST /api/evals/run triggers background runner and GET /api/evals/status returns progress."""
    res = client.post("/api/evals/run")
    assert res.status_code == 202
    data = res.get_json()
    assert "status" in data

    # Check status endpoint
    status_res = client.get("/api/evals/status")
    assert status_res.status_code == 200
    status_data = status_res.get_json()
    assert "status" in status_data
    assert "progress_pct" in status_data


def test_hood_page_renders(client):
    """GET /hood and GET /under-the-hood render the Under the Hood page with pipeline and tabs."""
    for path in ("/hood", "/under-the-hood"):
        res = client.get(path)
        assert res.status_code == 200
        html = res.get_data(as_text=True)
        assert "Under the Hood" in html
        assert "AI does judgment. Python does math and checking." in html
        assert "Deterministic Python Engine" in html
        assert "Claude 3.5 Sonnet" in html
        assert "Pre-Matcher" in html
        assert "Verification" in html
        assert "Tie-Out Proof" in html
        assert "Reviewer Memo" in html
        assert "Auditor Signoff" in html
        assert "Skill (SKILL.md)" in html
        assert "Tools (4 Schemas)" in html
        assert "Guardrails (8 Checks)" in html
        assert "Last Run Trace" in html
        assert "Prompts (v0 vs v1 vs v2)" in html


def test_hood_guardrails_api(client):
    """GET /api/hood/guardrails returns 8 deterministic guardrails with file locations."""
    res = client.get("/api/hood/guardrails")
    assert res.status_code == 200
    data = res.get_json()
    assert "guardrails" in data
    assert data["count"] == 8
    names = [g["name"] for g in data["guardrails"]]
    assert "Transaction IDs Must Exist" in names
    assert "One-to-Many Sums Exact" in names
    assert "No Plug Entries Permitted" in names
    assert "Journal Entries Must Be Pending" in names
    assert "Tie-Out Recomputed in Python" in names
    assert "Max 10 Tool Iterations" in names
    assert "Retry Once Then Flag" in names
    assert "Reviewer Memo Numbers Checked" in names

    # Verify implementation file paths exist
    for g in data["guardrails"]:
        assert "file" in g
        assert "function" in g
        assert "status" in g


def test_hood_prompts_api(client):
    """GET /api/hood/prompts returns side-by-side prompt definitions for v0, v1, and v2."""
    res = client.get("/api/hood/prompts")
    assert res.status_code == 200
    data = res.get_json()
    for ver in ("v0", "v1", "v2"):
        assert ver in data
        assert "system_prompt" in data[ver]
        assert "user_prompt" in data[ver]
        assert "token_profile" in data[ver]
    assert "DOMAINS" in data["v1"]["system_prompt"] or "SKILL" in data["v1"]["system_prompt"]
    assert "get_item" in data["v2"]["system_prompt"] or "tools" in data["v2"]["system_prompt"].lower()


def test_hood_trace_api(client):
    """GET /api/hood/trace/<variant> returns execution steps and tool invocations."""
    res = client.get("/api/hood/trace/full")
    assert res.status_code == 200
    data = res.get_json()
    assert data["variant"] == "full"
    assert "tokens" in data
    assert "cost_usd" in data
    assert "trace" in data
    assert len(data["trace"]) > 0
    first_step = data["trace"][0]
    assert "step" in first_step
    assert "tool" in first_step
    assert "input" in first_step


