"""Tests for src/runners.py and src/llm.py."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.llm import LLMResponse, call_claude, get_api_key, get_model_name
from src.runners import extract_json_from_text, run_v0


BASE_DIR = Path(__file__).resolve().parent.parent


def test_missing_api_key_raises_clear_error(monkeypatch):
    """Verify get_api_key raises a descriptive error when ANTHROPIC_API_KEY is unset."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY is not set"):
        get_api_key()


def test_missing_model_raises_clear_error(monkeypatch):
    """Verify get_model_name raises a descriptive error when CLAUDE_MODEL is unset."""
    monkeypatch.delenv("CLAUDE_MODEL", raising=False)
    with pytest.raises(ValueError, match="CLAUDE_MODEL is not set"):
        get_model_name()


def test_extract_json_from_code_fences():
    """Verify extract_json_from_text handles clean JSON, markdown code fences, and extra commentary."""
    # 1. Pure JSON
    pure_json = '{"matches": [], "reconciling_items": []}'
    data, err = extract_json_from_text(pure_json)
    assert not err
    assert data == {"matches": [], "reconciling_items": []}

    # 2. Markdown fenced JSON
    fenced_json = "Here is the reconciliation:\n```json\n{\n  \"matches\": [{\"bank_ids\": [\"B1\"]}]\n}\n```\nHope this helps!"
    data, err = extract_json_from_text(fenced_json)
    assert not err
    assert data["matches"] == [{"bank_ids": ["B1"]}]

    # 3. Outer curly braces with preamble
    preamble_json = "Reconciliation result:\n{\"matches\": [], \"memo\": \"done\"}"
    data, err = extract_json_from_text(preamble_json)
    assert not err
    assert data["memo"] == "done"

    # 4. Invalid text
    bad_text = "I could not generate valid JSON."
    data, err = extract_json_from_text(bad_text)
    assert err
    assert data is None


def test_run_v0_with_mocked_llm(monkeypatch, tmp_path):
    """Verify run_v0 reads CSVs, invokes LLM, parses JSON, and saves results to results/v0/."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-api-key")
    monkeypatch.setenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")

    mock_llm_response = LLMResponse(
        content='```json\n{"matches": [], "reconciling_items": [], "flagged_for_human": [], "proposed_journal_entries": [], "tie_out": {"can_prove": true}, "memo": "clean run"}\n```',
        input_tokens=1500,
        output_tokens=300,
        elapsed_seconds=1.25,
        model="claude-3-5-sonnet-20241022",
    )

    clean_dir = BASE_DIR / "data" / "variants" / "clean"

    clean_json_path = BASE_DIR / "results" / "v0" / "clean.json"
    backup = clean_json_path.read_text(encoding="utf-8") if clean_json_path.is_file() else None

    with patch("src.runners.call_claude", return_value=mock_llm_response) as mock_call:
        try:
            parsed = run_v0(clean_dir, save_results=True)

            assert mock_call.called
            assert parsed["memo"] == "clean run"
            assert parsed["parse_error"] is False

            # Verify saved result file
            saved_file = BASE_DIR / "results" / "v0" / "clean.json"
            assert saved_file.is_file()
            with open(saved_file, "r", encoding="utf-8") as f:
                saved_data = json.load(f)
            assert saved_data["variant"] == "clean"
            assert saved_data["runner"] == "v0"
            assert saved_data["tokens"]["input_tokens"] == 1500
        finally:
            if backup is not None:
                clean_json_path.write_text(backup, encoding="utf-8")


def test_run_v0_parse_error_handling(monkeypatch):
    """Verify run_v0 records parse_error=true without crashing on unparseable output."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-api-key")
    monkeypatch.setenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")

    mock_bad_response = LLMResponse(
        content="I apologize, but I am unable to complete the reconciliation in JSON.",
        input_tokens=1000,
        output_tokens=50,
        elapsed_seconds=0.8,
        model="claude-3-5-sonnet-20241022",
    )

    clean_dir = BASE_DIR / "data" / "variants" / "clean"

    with patch("src.runners.call_claude", return_value=mock_bad_response):
        parsed = run_v0(clean_dir, save_results=False)

        assert parsed["parse_error"] is True
        assert "unable to complete" in parsed["raw_text"]
        assert parsed["tie_out"]["can_prove"] is False


def test_run_v1_with_mocked_llm(monkeypatch):
    """Verify run_v1 loads SKILL.md into the system prompt and saves results to results/v1/."""
    from src.runners import run_v1, get_system_prompt_v1

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-api-key")
    monkeypatch.setenv("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")

    sys_prompt = get_system_prompt_v1()
    assert "Bank Reconciliation Skill" in sys_prompt or "bank-reconciliation" in sys_prompt.lower()
    assert "Hard rules" in sys_prompt or "Hard Rules" in sys_prompt or "Never create a plug" in sys_prompt

    mock_llm_response = LLMResponse(
        content='```json\n{"matches": [], "reconciling_items": [], "flagged_for_human": [], "proposed_journal_entries": [], "tie_out": {"can_prove": true}, "memo": "v1 run"}\n```',
        input_tokens=2200,
        output_tokens=350,
        elapsed_seconds=1.45,
        model="claude-3-5-sonnet-20241022",
    )

    clean_dir = BASE_DIR / "data" / "variants" / "clean"
    clean_json_path = BASE_DIR / "results" / "v1" / "clean.json"
    backup = clean_json_path.read_text(encoding="utf-8") if clean_json_path.is_file() else None

    with patch("src.runners.call_claude", return_value=mock_llm_response) as mock_call:
        try:
            parsed = run_v1(clean_dir, save_results=True)

            assert mock_call.called
            # Verify system prompt passed to call_claude contains skill content
            call_kwargs = mock_call.call_args[1]
            assert "Bank Reconciliation" in call_kwargs["system"]

            assert parsed["memo"] == "v1 run"
            assert parsed["parse_error"] is False

            # Verify saved result file in results/v1/
            saved_file = BASE_DIR / "results" / "v1" / "clean.json"
            assert saved_file.is_file()
            with open(saved_file, "r", encoding="utf-8") as f:
                saved_data = json.load(f)
            assert saved_data["variant"] == "clean"
            assert saved_data["runner"] == "v1"
        finally:
            if backup is not None:
                clean_json_path.write_text(backup, encoding="utf-8")


def test_run_v2_execution_and_trace(monkeypatch):
    """Verify run_v2 executes pre-matcher, tool loop, verification, and saves trace in results/v2/."""
    from src.runners import run_v2, get_system_prompt_v2

    sys_prompt = get_system_prompt_v2()
    assert "AGENTIC RECONCILIATION INSTRUCTIONS" in sys_prompt
    assert "submit_reconciliation" in sys_prompt
    assert "get_item" in sys_prompt

    clean_dir = BASE_DIR / "data" / "variants" / "clean"
    clean_v2_path = BASE_DIR / "results" / "v2" / "clean.json"
    backup = clean_v2_path.read_text(encoding="utf-8") if clean_v2_path.is_file() else None

    try:
        parsed = run_v2(clean_dir, save_results=True, mock=True)
        assert len(parsed["matches"]) > 0
        assert parsed["tie_out"]["can_prove"] is True

        # Check saved result
        assert clean_v2_path.is_file()
        with open(clean_v2_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["runner"] == "v2"
        assert data["variant"] == "clean"
        assert "trace" in data
        assert len(data["trace"]) > 0
        assert any(t["tool"] == "submit_reconciliation" for t in data["trace"])
        assert data["pre_matches_count"] > 0
    finally:
        if backup is not None:
            clean_v2_path.write_text(backup, encoding="utf-8")


