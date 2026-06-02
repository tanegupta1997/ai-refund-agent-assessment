from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass

import openai

from app.agent.tools import get_tool_definitions
from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Client initialisation — fail fast if key is missing
# ---------------------------------------------------------------------------

if not settings.OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set. Add it to your .env file.")

_client = openai.OpenAI(
    api_key=settings.OPENAI_API_KEY,
    base_url=settings.LLM_BASE_URL or None,
)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class LLMMessage:
    role: str    # "system" / "user" / "assistant"
    content: str


@dataclass
class LLMToolCall:
    tool_call_id: str
    tool_name: str
    tool_args: dict


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[LLMToolCall]
    finish_reason: str           # "stop" / "tool_calls" / "error"
    raw_usage: dict
    error: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _error_response(error: str) -> LLMResponse:
    return LLMResponse(
        content=None,
        tool_calls=[],
        finish_reason="error",
        raw_usage={},
        error=error,
    )


def _is_transient(exc: Exception) -> bool:
    return isinstance(exc, (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError))


def _safe_error_message(exc: Exception) -> str:
    """Return a safe error string with no API key material."""
    return f"{type(exc).__name__}: {str(exc)[:200]}"


# ---------------------------------------------------------------------------
# Function 1 — call_llm
# ---------------------------------------------------------------------------


def call_llm(
    messages: list[LLMMessage],
    use_tools: bool = True,
    system_prompt: str | None = None,
) -> LLMResponse:
    api_messages: list[dict] = []

    if system_prompt:
        api_messages.append({"role": "system", "content": system_prompt})

    for m in messages:
        api_messages.append({"role": m.role, "content": m.content})

    kwargs: dict = {
        "model": settings.MODEL_NAME,
        "messages": api_messages,
        "temperature": settings.LLM_TEMPERATURE,
        "max_tokens": settings.LLM_MAX_TOKENS,
    }

    if use_tools:
        kwargs["tools"] = get_tool_definitions()
        kwargs["tool_choice"] = "auto"

    attempts = 0
    max_attempts = 1 + settings.LLM_MAX_RETRIES

    while attempts < max_attempts:
        attempts += 1
        try:
            response = _client.chat.completions.create(**kwargs)
            choice = response.choices[0]
            finish_reason = choice.finish_reason
            usage = response.usage
            raw_usage = {
                "prompt_tokens": usage.prompt_tokens if usage else 0,
                "completion_tokens": usage.completion_tokens if usage else 0,
            }

            logger.info(
                "LLM call — model=%s finish_reason=%s prompt_tokens=%d completion_tokens=%d",
                settings.MODEL_NAME,
                finish_reason,
                raw_usage["prompt_tokens"],
                raw_usage["completion_tokens"],
            )

            if finish_reason == "tool_calls":
                tool_calls: list[LLMToolCall] = []
                for tc in choice.message.tool_calls or []:
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        logger.warning("Failed to parse tool args for %s: %s", tc.function.name, tc.function.arguments)
                        args = {}
                    tool_calls.append(LLMToolCall(
                        tool_call_id=tc.id,
                        tool_name=tc.function.name,
                        tool_args=args,
                    ))
                return LLMResponse(
                    content=None,
                    tool_calls=tool_calls,
                    finish_reason="tool_calls",
                    raw_usage=raw_usage,
                )

            # finish_reason == "stop" (or anything else)
            content = choice.message.content or ""
            return LLMResponse(
                content=content,
                tool_calls=[],
                finish_reason="stop",
                raw_usage=raw_usage,
            )

        except openai.AuthenticationError as exc:
            # Auth errors are permanent — do not retry
            logger.error("LLM authentication error: %s", type(exc).__name__)
            return _error_response("Authentication failed. Check your API key.")

        except Exception as exc:
            if _is_transient(exc) and attempts < max_attempts:
                logger.warning(
                    "Transient LLM error (attempt %d/%d): %s — retrying in 1s",
                    attempts, max_attempts, type(exc).__name__,
                )
                time.sleep(1)
                continue
            logger.error("LLM call failed: %s", _safe_error_message(exc))
            return _error_response(_safe_error_message(exc))

    return _error_response("LLM call failed after retries.")


# ---------------------------------------------------------------------------
# Function 2 — call_llm_for_json
# ---------------------------------------------------------------------------


def call_llm_for_json(
    prompt: str,
    system_prompt: str | None = None,
) -> dict | None:
    try:
        response = call_llm(
            messages=[LLMMessage(role="user", content=prompt)],
            use_tools=False,
            system_prompt=system_prompt,
        )
        if not response.content:
            return None

        cleaned = response.content.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        return json.loads(cleaned)
    except Exception as exc:
        logger.error("call_llm_for_json failed: %s", _safe_error_message(exc))
        return None


# ---------------------------------------------------------------------------
# Function 3 — call_llm_for_text
# ---------------------------------------------------------------------------


def call_llm_for_text(
    prompt: str,
    system_prompt: str | None = None,
) -> str | None:
    try:
        response = call_llm(
            messages=[LLMMessage(role="user", content=prompt)],
            use_tools=False,
            system_prompt=system_prompt,
        )
        return response.content or None
    except Exception as exc:
        logger.error("call_llm_for_text failed: %s", _safe_error_message(exc))
        return None


# ---------------------------------------------------------------------------
# Function 4 — format_tool_result_for_llm
# ---------------------------------------------------------------------------


def format_tool_result_for_llm(
    tool_call_id: str,
    tool_name: str,
    result: dict | list | str,
) -> dict:
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": tool_name,
        "content": json.dumps(result),
    }


# ---------------------------------------------------------------------------
# Function 5 — estimate_token_count
# ---------------------------------------------------------------------------


def estimate_token_count(text: str) -> int:
    return int(len(text.split()) * 1.3)


__all__ = [
    "LLMMessage",
    "LLMToolCall",
    "LLMResponse",
    "call_llm",
    "call_llm_for_json",
    "call_llm_for_text",
    "format_tool_result_for_llm",
    "estimate_token_count",
]
