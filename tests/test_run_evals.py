"""Unit tests for evals/run_evals.py evaluation harness."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from evals.run_evals import (
    ALL_VARIANTS,
    DEFAULT_VERSIONS,
    INPUT_PRICE_PER_M,
    OUTPUT_PRICE_PER_M,
    compute_cost,
    print_summary_table,
    run_evaluation,
)


BASE_DIR = Path(__file__).resolve().parent.parent


def test_pricing_and_compute_cost():
    """Verify configurable constants and cost calculation."""
    assert INPUT_PRICE_PER_M > 0
    assert OUTPUT_PRICE_PER_M > 0

    # 1,000,000 in, 1,000,000 out
    cost = compute_cost(1_000_000, 1_000_000)
    expected = round(INPUT_PRICE_PER_M + OUTPUT_PRICE_PER_M, 4)
    assert cost == expected

    # 0 tokens
    assert compute_cost(0, 0) == 0.0


def test_unimplemented_versions_skip_cleanly(tmp_path):
    """Verify unimplemented runner versions skip without crashing."""
    summary = run_evaluation(
        versions=["v99_nonexistent"],
        variants=["clean"],
        force=False,
    )

    assert "v99_nonexistent" in summary["versions"]
    assert "clean" in summary["matrix"]
    cell = summary["matrix"]["clean"]["v99_nonexistent"]
    assert cell["status"] == "NOT_IMPLEMENTED"
    assert cell["display"] == "SKIP"

    totals = summary["totals"]["v99_nonexistent"]
    assert totals["implemented"] is False
    assert totals["total_tested"] == 0
    assert totals["passed"] == 0
    assert totals["total_cost_usd"] == 0.0


def test_not_implemented_error_runner_skips_cleanly():
    """Verify that a runner raising NotImplementedError is treated as skipped."""
    def dummy_stub(variant_dir, **kwargs):
        raise NotImplementedError("Feature not ready")

    with patch("evals.run_evals.runners_module.run_v_stub", dummy_stub, create=True):
        summary = run_evaluation(
            versions=["v_stub"],
            variants=["clean"],
            force=True,
        )
        cell = summary["matrix"]["clean"]["v_stub"]
        assert cell["status"] == "NOT_IMPLEMENTED"
        assert cell["display"] == "SKIP"


def test_resumable_execution(tmp_path):
    """Verify run_evals reuses existing result files when --force is False."""
    call_counter = {"count": 0}

    def mock_runner(variant_dir, **kwargs):
        call_counter["count"] += 1
        return {
            "parsed_output": {
                "matches": [],
                "reconciling_items": [],
                "flagged_for_human": [],
                "proposed_journal_entries": [],
                "tie_out": {"can_prove": True},
                "memo": "mock run",
            },
            "tokens": {"input_tokens": 100, "output_tokens": 50, "elapsed_seconds": 0.5},
        }

    mock_dir = BASE_DIR / "results" / "v_mock"
    try:
        with patch("evals.run_evals.runners_module.run_v_mock", mock_runner, create=True):
            # First run (executes runner)
            summary1 = run_evaluation(
                versions=["v_mock"],
                variants=["clean"],
                force=True,
            )
            assert call_counter["count"] == 1

            # Second run without force (should reuse results file)
            summary2 = run_evaluation(
                versions=["v_mock"],
                variants=["clean"],
                force=False,
            )
            # Runner should not have been called again
            assert call_counter["count"] == 1

            # Third run with force=True (should re-execute runner)
            summary3 = run_evaluation(
                versions=["v_mock"],
                variants=["clean"],
                force=True,
            )
            assert call_counter["count"] == 2
    finally:
        import shutil
        if mock_dir.is_dir():
            shutil.rmtree(mock_dir, ignore_errors=True)


def test_summary_json_file_created():
    """Verify that results/summary.json contains valid matrix and totals."""
    summary_path = BASE_DIR / "results" / "summary.json"
    assert summary_path.is_file()

    with open(summary_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "timestamp" in data
    assert "versions" in data
    assert "variants" in data
    assert "pricing" in data
    assert "matrix" in data
    assert "totals" in data
    assert data["pricing"]["input_price_per_million"] == INPUT_PRICE_PER_M
    assert data["pricing"]["output_price_per_million"] == OUTPUT_PRICE_PER_M


def test_print_summary_table_output(capsys):
    """Verify table printing renders variants, version columns, cells, and totals rows."""
    dummy_summary = {
        "versions": ["v0", "v1"],
        "variants": ["clean", "timing"],
        "pricing": {
            "input_price_per_million": INPUT_PRICE_PER_M,
            "output_price_per_million": OUTPUT_PRICE_PER_M,
        },
        "matrix": {
            "clean": {
                "v0": {"display": "PASS (fm=0, h=0)"},
                "v1": {"display": "SKIP"},
            },
            "timing": {
                "v0": {"display": "FAIL (fm=1, h=0)"},
                "v1": {"display": "SKIP"},
            },
        },
        "totals": {
            "v0": {
                "implemented": True,
                "total_tested": 2,
                "passed": 1,
                "pass_rate": 0.5,
                "false_matches": 1,
                "hallucinated_ids": 0,
                "total_tokens": 10000,
                "total_cost_usd": 0.05,
            },
            "v1": {
                "implemented": False,
                "total_tested": 0,
                "passed": 0,
                "pass_rate": 0.0,
                "false_matches": 0,
                "hallucinated_ids": 0,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
            },
        },
    }

    print_summary_table(dummy_summary)
    captured = capsys.readouterr().out

    # Check header and variants
    assert "Variant" in captured
    assert "v0" in captured
    assert "v1" in captured
    assert "clean" in captured
    assert "timing" in captured

    # Check cells
    assert "PASS (fm=0, h=0)" in captured
    assert "FAIL (fm=1, h=0)" in captured
    assert "SKIP" in captured

    # Check totals rows
    assert "Pass Rate" in captured
    assert "1/2 (50.0%)" in captured
    assert "False Matches" in captured
    assert "Hallucinated" in captured
    assert "Total Tokens" in captured
    assert "10,000" in captured
    assert "Est. Cost" in captured
    assert "$0.0500" in captured


def test_cli_main_execution(monkeypatch, capsys):
    """Verify python -m evals.run_evals execution with CLI arguments."""
    from evals.run_evals import main
    test_args = ["run_evals.py", "--versions", "v0", "v1", "--variants", "clean", "--force", "--mock"]
    monkeypatch.setattr("sys.argv", test_args)

    main()
    captured = capsys.readouterr().out
    assert "clean" in captured
    assert "v0" in captured
    assert "v1" in captured
    assert "Pass Rate" in captured
