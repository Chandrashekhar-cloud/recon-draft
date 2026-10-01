"""Anthropic LLM integration module for reconciliation agents.

Provides a thin wrapper around the Anthropic Python SDK:
- Loads ANTHROPIC_API_KEY and CLAUDE_MODEL from .env
- Model name must come from environment, never hardcoded (Rule 6 / Project spec)
- Retries once on transient errors
- Logs every call (timestamp, tokens, seconds) to results/call_log.jsonl
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Union

from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()


@dataclass
class LLMResponse:
    """Standardized response from Claude invocation."""
    content: str
    input_tokens: int
    output_tokens: int
    elapsed_seconds: float
    model: str
    raw_response: Any = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "content": self.content,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "elapsed_seconds": self.elapsed_seconds,
            "model": self.model,
        }


def get_api_key() -> str:
    """Retrieve and validate the Anthropic API key from the environment."""
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY is not set. Please add it to your .env file or environment."
        )
    return api_key


def get_model_name() -> str:
    """Retrieve and validate the Claude model name from the environment."""
    model = os.getenv("CLAUDE_MODEL", "").strip()
    if not model:
        raise ValueError(
            "CLAUDE_MODEL is not set. Please specify the model name in your .env file."
        )
    return model


def log_llm_call(
    model: str,
    input_tokens: int,
    output_tokens: int,
    elapsed_seconds: float,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """Log LLM invocation metadata to results/call_log.jsonl."""
    base_dir = Path(__file__).resolve().parent.parent
    log_dir = base_dir / "results"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "call_log.jsonl"

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "elapsed_seconds": round(elapsed_seconds, 3),
    }
    if metadata:
        entry["metadata"] = metadata

    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def call_claude(
    system: str,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    max_tokens: int = 4000,
    metadata: Optional[Dict[str, Any]] = None,
) -> LLMResponse:
    """Invoke Claude using the Anthropic Python SDK with automatic retry on transient error.

    Args:
        system: System prompt string.
        messages: List of message dicts (e.g. [{"role": "user", "content": "..."}]).
        tools: Optional tool schemas.
        max_tokens: Maximum tokens in response.
        metadata: Optional metadata to append to the log.

    Returns:
        LLMResponse containing content, token usage, elapsed time, and model.

    Raises:
        ValueError: If API key or model is missing.
        Exception: If call fails after retry.
    """
    import anthropic

    api_key = get_api_key()
    model = get_model_name()

    client = anthropic.Anthropic(api_key=api_key)

    kwargs: Dict[str, Any] = {
        "model": model,
        "system": system,
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if tools:
        kwargs["tools"] = tools

    # Transient error retry loop (retry once)
    start_time = time.perf_counter()
    attempts = 0
    max_attempts = 2
    last_error: Optional[Exception] = None

    while attempts < max_attempts:
        attempts += 1
        try:
            response = client.messages.create(**kwargs)
            elapsed = time.perf_counter() - start_time

            # Extract text content
            content_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    content_text += block.text

            in_tokens = response.usage.input_tokens
            out_tokens = response.usage.output_tokens

            # Log call
            log_llm_call(model, in_tokens, out_tokens, elapsed, metadata)

            return LLMResponse(
                content=content_text,
                input_tokens=in_tokens,
                output_tokens=out_tokens,
                elapsed_seconds=elapsed,
                model=model,
                raw_response=response,
            )

        except (
            anthropic.APIConnectionError,
            anthropic.RateLimitError,
            anthropic.InternalServerError,
        ) as err:
            last_error = err
            if attempts < max_attempts:
                time.sleep(2.0)
            else:
                raise err
        except Exception as err:
            # Non-transient errors (e.g. AuthenticationError, BadRequestError) fail immediately
            raise err

    raise last_error or RuntimeError("Unknown error during Claude invocation")
