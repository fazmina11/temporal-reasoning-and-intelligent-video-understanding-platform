"""
src/pipeline/providers.py — Multi-Provider LLM/VLM Client
==========================================================

Unified interface for calling Vision Language Models and Text LLMs across
multiple free-tier providers with automatic fallback:

  1. Groq  (qwen/qwen3.6-27b)     — 14,400 req/day, ultra-fast
  2. Gemini (gemini-2.5-flash)      — 1,500 req/day
  3. OpenRouter (free models)       — 200 req/hr

Supports:
  - Vision (image + text → structured JSON)
  - Text-only (summarization, cleanup)
  - Reasoning model handling (strips <think> tags)
  - Automatic provider fallback on quota exhaustion
  - Resume support (tracks per-provider exhaustion)
"""

from __future__ import annotations

import json
import os
import re
import time
import base64
import logging
from pathlib import Path
from typing import Any
from dataclasses import dataclass, field

from dotenv import load_dotenv

_REPO_ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_REPO_ROOT_ENV)

logger = logging.getLogger("providers")


# ── Provider Configuration ──────────────────────────────────────────────────

@dataclass
class ProviderConfig:
    name: str
    model: str
    supports_vision: bool = True
    supports_text: bool = True
    rpm_limit: int = 30
    rpd_limit: int = 14400
    timeout: int = 60
    reasoning_effort: str | None = None  # e.g. "none" for Qwen


# Default provider chain (ordered by priority)
DEFAULT_PROVIDERS = [
    ProviderConfig(
        name="groq",
        model=os.getenv("GROQ_VLM_MODEL", "qwen/qwen3.6-27b"),
        rpm_limit=30,
        rpd_limit=14400,
        timeout=60,
        reasoning_effort="none",
    ),
    ProviderConfig(
        name="gemini",
        model=os.getenv("GEMINI_MODEL_VLM", "gemini-2.5-flash"),
        rpm_limit=15,
        rpd_limit=1500,
        timeout=120,
    ),
]


# ── Provider State (tracks per-session exhaustion) ─────────────────────────

@dataclass
class ProviderState:
    quota_exhausted: bool = False
    requests_today: int = 0
    last_error: str = ""
    requests_this_minute: int = 0
    minute_start: float = field(default_factory=time.time)


_provider_states: dict[str, ProviderState] = {}


def _get_state(name: str) -> ProviderState:
    if name not in _provider_states:
        _provider_states[name] = ProviderState()
    state = _provider_states[name]
    # Reset per-minute counter
    if time.time() - state.minute_start > 60:
        state.requests_this_minute = 0
        state.minute_start = time.time()
    return state


# ── Stripping Reasoning Tags ────────────────────────────────────────────────

def _strip_thinking_tags(text: str) -> str:
    """Remove <think>...</think> blocks and markdown fences."""
    # Remove thinking tags
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    text = re.sub(r'<think>.*', '', text, flags=re.DOTALL)
    # Strip markdown code fences
    text = text.strip()
    if text.startswith("```"):
        # Remove opening fence (```json or ```)
        text = re.sub(r'^```\w*\s*\n?', '', text)
        # Remove closing fence
        text = re.sub(r'\n?```\s*$', '', text)
    return text.strip()


def _parse_json_response(raw: str) -> dict[str, Any]:
    """Parse a JSON response, handling markdown fences and thinking tags."""
    cleaned = _strip_thinking_tags(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find JSON object in the response
        match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return {}


# ── Groq Provider ───────────────────────────────────────────────────────────

def _call_groq_text(
    config: ProviderConfig,
    prompt: str,
    *,
    system: str = "",
    max_tokens: int = 1024,
    temperature: float = 0.3,
) -> str | None:
    """Call Groq for text-only completion."""
    try:
        from groq import Groq
    except ImportError:
        raise ImportError("groq is required. Install with: pip install groq")

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise EnvironmentError("GROQ_API_KEY not set in .env")

    state = _get_state(config.name)
    if state.quota_exhausted:
        return None
    if state.requests_this_minute >= config.rpm_limit:
        logger.warning("Groq: RPM limit reached (%d), skipping", config.rpm_limit)
        return None

    client = Groq(api_key=api_key)
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    kwargs = {
        "model": config.model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if config.reasoning_effort:
        kwargs["reasoning_effort"] = config.reasoning_effort

    try:
        resp = client.chat.completions.create(**kwargs)
        state.requests_today += 1
        state.requests_this_minute += 1
        content = resp.choices[0].message.content or ""
        return _strip_thinking_tags(content)
    except Exception as exc:
        err_str = str(exc)
        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "rate_limit" in err_str:
            state.quota_exhausted = True
            state.last_error = err_str[:200]
            logger.warning("Groq quota exhausted: %s", err_str[:100])
            return None
        logger.error("Groq API error: %s", err_str[:200])
        state.last_error = err_str[:200]
        return None


def _call_groq_vision(
    config: ProviderConfig,
    image_b64: str,
    prompt: str,
    *,
    max_tokens: int = 1024,
    temperature: float = 0.3,
) -> dict[str, Any] | None:
    """Call Groq with vision (image + text)."""
    try:
        from groq import Groq
    except ImportError:
        raise ImportError("groq is required. Install with: pip install groq")

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise EnvironmentError("GROQ_API_KEY not set in .env")

    state = _get_state(config.name)
    if state.quota_exhausted:
        return None
    if state.requests_this_minute >= config.rpm_limit:
        logger.warning("Groq: RPM limit reached, skipping vision call")
        return None

    client = Groq(api_key=api_key)

    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
        ],
    }]

    kwargs = {
        "model": config.model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if config.reasoning_effort:
        kwargs["reasoning_effort"] = config.reasoning_effort

    try:
        resp = client.chat.completions.create(**kwargs)
        state.requests_today += 1
        state.requests_this_minute += 1
        raw = resp.choices[0].message.content or ""
        return _parse_json_response(raw)
    except Exception as exc:
        err_str = str(exc)
        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "rate_limit" in err_str:
            state.quota_exhausted = True
            state.last_error = err_str[:200]
            logger.warning("Groq quota exhausted: %s", err_str[:100])
            return None
        logger.error("Groq vision error: %s", err_str[:200])
        state.last_error = err_str[:200]
        return None


# ── Gemini Provider ─────────────────────────────────────────────────────────

def _call_gemini_text(
    config: ProviderConfig,
    prompt: str,
    *,
    system: str = "",
    max_tokens: int = 1024,
    temperature: float = 0.3,
) -> str | None:
    """Call Gemini for text-only completion."""
    try:
        from google import genai
    except ImportError:
        raise ImportError("google-genai required. Install with: pip install google-genai")

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY not set — skipping Gemini provider")
        return None

    state = _get_state(config.name)
    if state.quota_exhausted:
        return None

    client = genai.Client(api_key=api_key)
    contents = []
    if system:
        contents.append(f"System: {system}\n\n{prompt}")
    else:
        contents.append(prompt)

    try:
        resp = client.models.generate_content(
            model=config.model,
            contents=contents,
            config={"max_output_tokens": max_tokens, "temperature": temperature},
        )
        state.requests_today += 1
        return (resp.text or "").strip()
    except Exception as exc:
        err_str = str(exc)
        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
            state.quota_exhausted = True
            state.last_error = err_str[:200]
            logger.warning("Gemini quota exhausted: %s", err_str[:100])
            return None
        logger.error("Gemini API error: %s", err_str[:200])
        state.last_error = err_str[:200]
        return None


def _call_gemini_vision(
    config: ProviderConfig,
    image_b64: str,
    prompt: str,
    *,
    max_tokens: int = 1024,
    temperature: float = 0.3,
) -> dict[str, Any] | None:
    """Call Gemini with vision (image + text)."""
    try:
        from google import genai
        from PIL import Image
        import io
    except ImportError:
        raise ImportError("google-genai and Pillow required")

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None

    state = _get_state(config.name)
    if state.quota_exhausted:
        return None

    client = genai.Client(api_key=api_key)

    # Decode base64 to PIL Image
    img_bytes = base64.b64decode(image_b64)
    image = Image.open(io.BytesIO(img_bytes)).convert("RGB")

    try:
        resp = client.models.generate_content(
            model=config.model,
            contents=[prompt, image],
            config={"max_output_tokens": max_tokens, "temperature": temperature},
        )
        state.requests_today += 1
        raw = (resp.text or "").strip()
        return _parse_json_response(raw)
    except Exception as exc:
        err_str = str(exc)
        if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
            state.quota_exhausted = True
            state.last_error = err_str[:200]
            logger.warning("Gemini quota exhausted: %s", err_str[:100])
            return None
        logger.error("Gemini vision error: %s", err_str[:200])
        state.last_error = err_str[:200]
        return None


# ── Unified Interface ───────────────────────────────────────────────────────

# Dispatch tables
_VLM_CALLERS = {
    "groq": _call_groq_vision,
    "gemini": _call_gemini_vision,
}
_TEXT_CALLERS = {
    "groq": _call_groq_text,
    "gemini": _call_gemini_text,
}


def call_vlm(
    image_b64: str,
    prompt: str,
    *,
    providers: list[ProviderConfig] | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.3,
) -> dict[str, Any] | None:
    """
    Call a Vision Language Model with automatic provider fallback.

    Tries each provider in order until one succeeds. Returns parsed JSON
    dict or None if all providers fail.
    """
    if providers is None:
        providers = DEFAULT_PROVIDERS

    for config in providers:
        if not config.supports_vision:
            continue
        caller = _VLM_CALLERS.get(config.name)
        if not caller:
            continue

        logger.debug("Trying provider: %s (model: %s)", config.name, config.model)
        result = caller(
            config, image_b64, prompt,
            max_tokens=max_tokens, temperature=temperature,
        )
        if result is not None:
            logger.info("Provider %s succeeded", config.name)
            return result
        logger.warning("Provider %s failed, trying next...", config.name)

    logger.error("All providers failed for VLM call")
    return None


def call_llm(
    prompt: str,
    *,
    system: str = "",
    providers: list[ProviderConfig] | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.3,
) -> str | None:
    """
    Call a text LLM with automatic provider fallback.

    Returns the text response or None if all providers fail.
    """
    if providers is None:
        providers = DEFAULT_PROVIDERS

    for config in providers:
        if not config.supports_text:
            continue
        caller = _TEXT_CALLERS.get(config.name)
        if not caller:
            continue

        logger.debug("Trying provider: %s (model: %s)", config.name, config.model)
        result = caller(
            config, prompt,
            system=system, max_tokens=max_tokens, temperature=temperature,
        )
        if result is not None:
            logger.info("Provider %s succeeded for text call", config.name)
            return result
        logger.warning("Provider %s failed for text, trying next...", config.name)

    logger.error("All providers failed for text call")
    return None


def get_provider_status() -> dict[str, Any]:
    """Return the current status of all providers."""
    status = {}
    for name in ["groq", "gemini"]:
        state = _get_state(name)
        status[name] = {
            "quota_exhausted": state.quota_exhausted,
            "requests_today": state.requests_today,
            "last_error": state.last_error,
        }
    return status


def reset_provider(provider_name: str) -> None:
    """Reset a provider's exhaustion state (e.g., after quota reset)."""
    if provider_name in _provider_states:
        _provider_states[provider_name] = ProviderState()
        logger.info("Reset provider state: %s", provider_name)
