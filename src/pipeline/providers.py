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


# ── Groq Provider (Multi-Key Rotation) ──────────────────────────────────────

def _get_groq_api_keys() -> list[str]:
    """Collect all available Groq API keys from environment.
    
    Supports GROQ_API_KEY, GROQ_API_KEY1, GROQ_API_KEY2, GROQ_API_KEY3, etc.
    Returns them in order so the first key is tried first.
    """
    keys = []
    # Single key (legacy)
    single = os.getenv("GROQ_API_KEY")
    if single:
        keys.append(single)
    # Numbered keys
    for i in range(1, 10):
        k = os.getenv(f"GROQ_API_KEY{i}")
        if k and k not in keys:
            keys.append(k)
    return keys


def _get_key_state(key_hash: str) -> ProviderState:
    """Get exhaustion state for a specific API key (identified by last8 chars)."""
    state_key = f"groq_key_{key_hash}"
    return _get_state(state_key)


def _is_key_available(key: str) -> bool:
    """Check if a Groq API key is not rate-limited."""
    key_hash = key[-8:]
    state = _get_key_state(key_hash)
    if state.quota_exhausted:
        return False
    if state.requests_this_minute >= 30:  # RPM limit per key
        return False
    return True


def _mark_key_exhausted(key: str, err_str: str) -> None:
    """Mark a specific Groq API key as rate-limited."""
    key_hash = key[-8:]
    state = _get_key_state(key_hash)
    state.quota_exhausted = True
    state.last_error = err_str[:200]


def _record_key_usage(key: str) -> None:
    """Record a successful request for a specific Groq API key."""
    key_hash = key[-8:]
    state = _get_key_state(key_hash)
    state.requests_today += 1
    state.requests_this_minute += 1


def _try_groq_keys(
    func_name: str,
    config: ProviderConfig,
    *args,
    **kwargs,
) -> Any:
    """Try all available Groq API keys for a given function.
    
    Rotates through keys until one succeeds or all are exhausted.
    """
    keys = _get_groq_api_keys()
    if not keys:
        logger.error("No Groq API keys found in environment")
        return None

    # Global state check
    global_state = _get_state(config.name)
    if global_state.quota_exhausted:
        # Check if any individual key is still available
        if not any(_is_key_available(k) for k in keys):
            return None
        # At least one key available — reset global state and try
        global_state.quota_exhausted = False

    last_error = None
    for key in keys:
        if not _is_key_available(key):
            continue

        try:
            from groq import Groq
        except ImportError:
            raise ImportError("groq is required. Install with: pip install groq")

        client = Groq(api_key=key)
        try:
            if func_name == "text":
                result = _execute_groq_text(client, config, *args, **kwargs)
            else:
                result = _execute_groq_vision(client, config, *args, **kwargs)
            _record_key_usage(key)
            return result
        except Exception as exc:
            err_str = str(exc)
            last_error = err_str[:200]
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "rate_limit" in err_str:
                _mark_key_exhausted(key, err_str)
                key_masked = key[:8] + "..." + key[-4:]
                logger.warning("Groq key %s rate-limited, trying next key...", key_masked)
                continue
            logger.error("Groq API error (key ...%s): %s", key[-4:], err_str[:100])
            return None

    # All keys exhausted
    all_keys_masked = [k[:8] + "..." + k[-4:] for k in keys]
    logger.warning("All %d Groq keys exhausted: %s", len(keys), all_keys_masked)
    global_state.quota_exhausted = True
    global_state.last_error = last_error or "all keys exhausted"
    return None


def _execute_groq_text(
    client, config: ProviderConfig,
    prompt: str, *, system: str = "",
    max_tokens: int = 1024, temperature: float = 0.3,
) -> str:
    """Execute a text completion with an already-created Groq client."""
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

    resp = client.chat.completions.create(**kwargs)
    content = resp.choices[0].message.content or ""
    return _strip_thinking_tags(content)


def _execute_groq_vision(
    client, config: ProviderConfig,
    image_b64: str, prompt: str, *,
    max_tokens: int = 1024, temperature: float = 0.3,
) -> dict[str, Any]:
    """Execute a vision call with an already-created Groq client."""
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

    resp = client.chat.completions.create(**kwargs)
    raw = resp.choices[0].message.content or ""
    return _parse_json_response(raw)


def _call_groq_text(
    config: ProviderConfig,
    prompt: str,
    *,
    system: str = "",
    max_tokens: int = 1024,
    temperature: float = 0.3,
) -> str | None:
    """Call Groq for text-only completion with multi-key rotation."""
    result = _try_groq_keys("text", config, prompt, system=system,
                            max_tokens=max_tokens, temperature=temperature)
    return result if isinstance(result, str) else None


def _call_groq_vision(
    config: ProviderConfig,
    image_b64: str,
    prompt: str,
    *,
    max_tokens: int = 1024,
    temperature: float = 0.3,
) -> dict[str, Any] | None:
    """Call Groq with vision (image + text) with multi-key rotation."""
    result = _try_groq_keys("vision", config, image_b64, prompt,
                            max_tokens=max_tokens, temperature=temperature)
    return result if isinstance(result, dict) else None


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
    """Return the current status of all providers including per-key Groq status."""
    status = {}
    # Groq per-key status
    keys = _get_groq_api_keys()
    groq_keys_status = []
    for i, key in enumerate(keys):
        key_hash = key[-8:]
        state = _get_key_state(key_hash)
        groq_keys_status.append({
            "key_index": i + 1,
            "key_suffix": f"...{key[-4:]}",
            "available": _is_key_available(key),
            "quota_exhausted": state.quota_exhausted,
            "requests_today": state.requests_today,
            "last_error": state.last_error,
        })
    groq_global = _get_state("groq")
    status["groq"] = {
        "quota_exhausted": groq_global.quota_exhausted,
        "total_keys": len(keys),
        "available_keys": sum(1 for k in keys if _is_key_available(k)),
        "keys": groq_keys_status,
    }
    # Gemini status
    gemini_state = _get_state("gemini")
    status["gemini"] = {
        "quota_exhausted": gemini_state.quota_exhausted,
        "requests_today": gemini_state.requests_today,
        "last_error": gemini_state.last_error,
    }
    return status


def reset_provider(provider_name: str) -> None:
    """Reset a provider's exhaustion state (e.g., after quota reset)."""
    if provider_name in _provider_states:
        _provider_states[provider_name] = ProviderState()
        logger.info("Reset provider state: %s", provider_name)
