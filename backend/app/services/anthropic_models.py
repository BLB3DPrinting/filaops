"""Anthropic model discovery and model checks for the AI settings page.

The settings page used to hard-code three Claude model IDs. Anthropic retires
models on a schedule, so a hard-coded list goes stale (one of the old IDs was
never valid at all). Instead the page asks Anthropic which models the saved
key can use (GET /v1/models), and "Test connection" sends a one-token request
with the selected model so a retired or mistyped ID shows up at setup time,
not when the first invoice is parsed.

Raw HTTP through requests (already a Core dependency) rather than the
anthropic SDK: the SDK is an optional, installed-on-demand package, and these
two calls need nothing from it.

SEC: the API key is sent only to the fixed Anthropic host below, never echoed
back to the caller and never logged. Error messages are built here from the
status code and Anthropic's error type, not from the raw response body.
"""
from __future__ import annotations

import hmac
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import requests

from app.logging_config import get_logger

logger = get_logger(__name__)

ANTHROPIC_API_BASE = "https://api.anthropic.com"
ANTHROPIC_VERSION = "2023-06-01"
PRICING_URL = "https://platform.claude.com/docs/en/about-claude/pricing"

# The default for new installs and for a cleared setting. The frontend reads
# it from the API (GET /settings/ai and /settings/ai/anthropic-models), so
# this is the single source of the default.
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5-5"

# Shown when Anthropic can't be asked (no key, network down, bad key). Keep
# this short and current; it is a fallback, not the source of truth.
FALLBACK_MODELS: tuple[dict, ...] = (
    {"id": "claude-fable-5-1", "display_name": "Claude Fable 5.1"},
    {"id": "claude-opus-5-5", "display_name": "Claude Opus 5.5"},
    {"id": "claude-sonnet-5-5", "display_name": "Claude Sonnet 5.5"},
    {"id": "claude-haiku-5-5", "display_name": "Claude Haiku 5.5"},
)

CACHE_TTL_SECONDS = 600
_TIMEOUT = (5, 15)  # (connect, read) seconds
_MAX_PAGES = 5  # 1000 models per page; more than enough
_MAX_ERROR_DETAIL = 300


class AnthropicModelsError(Exception):
    """A model listing or model check failed. str(exc) is safe to show."""


@dataclass
class _CacheEntry:
    # An install has one saved key, so one entry is enough. The entry keeps
    # the key it was fetched with (already held decrypted in memory by the
    # caller) so a changed key never sees the old key's list.
    api_key: str
    expires_at: float
    models: list[dict] = field(default_factory=list)


class _ModelCache:
    """One cached model list, guarded by a lock."""

    def __init__(self) -> None:
        self._entry: Optional[_CacheEntry] = None
        self._lock = threading.Lock()

    def get(self, api_key: str, now: float) -> Optional[list[dict]]:
        with self._lock:
            entry = self._entry
        if (
            entry
            and entry.expires_at > now
            and hmac.compare_digest(entry.api_key, api_key)
        ):
            return [dict(m) for m in entry.models]
        return None

    def put(self, api_key: str, models: list[dict], now: float) -> None:
        with self._lock:
            self._entry = _CacheEntry(
                api_key=api_key, expires_at=now + CACHE_TTL_SECONDS, models=models
            )

    def clear(self) -> None:
        with self._lock:
            self._entry = None


_cache = _ModelCache()


def clear_model_cache() -> None:
    _cache.clear()


def _headers(api_key: str) -> dict[str, str]:
    return {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }


def _error_type_and_message(response: requests.Response) -> tuple[Optional[str], Optional[str]]:
    """Anthropic's {"error": {"type", "message"}} body, if it has one."""
    try:
        error = response.json().get("error") or {}
    except (ValueError, AttributeError):
        return None, None
    if not isinstance(error, dict):
        return None, None
    err_type = error.get("type") if isinstance(error.get("type"), str) else None
    message = error.get("message") if isinstance(error.get("message"), str) else None
    if message:
        message = message[:_MAX_ERROR_DETAIL]
    return err_type, message


def _describe_http_error(response: requests.Response, action: str) -> str:
    status_code = response.status_code
    _, message = _error_type_and_message(response)
    if status_code == 401:
        return "Anthropic rejected the API key (401). Check the key and save it again."
    if status_code == 403:
        return "This API key is not allowed to " + action + " (403)."
    if status_code == 429:
        return "Anthropic rate limit reached (429). Try again in a minute."
    if status_code >= 500:
        return f"Anthropic is having trouble right now ({status_code}). Try again later."
    suffix = f": {message}" if message else ""
    return f"Anthropic returned {status_code} while trying to {action}{suffix}"


def _model_summary(item: dict) -> Optional[dict]:
    model_id = item.get("id")
    if not isinstance(model_id, str) or not model_id:
        return None
    display_name = item.get("display_name")
    lifecycle = item.get("lifecycle")
    created_at = item.get("created_at")
    return {
        "id": model_id,
        "display_name": display_name if isinstance(display_name, str) else model_id,
        "lifecycle": lifecycle if isinstance(lifecycle, str) else None,
        "created_at": created_at if isinstance(created_at, str) else None,
    }


def _fetch_models(api_key: str) -> list[dict]:
    models: list[dict] = []
    params: dict[str, object] = {"limit": 1000}
    for _ in range(_MAX_PAGES):
        try:
            response = requests.get(
                f"{ANTHROPIC_API_BASE}/v1/models",
                headers=_headers(api_key),
                params=params,
                timeout=_TIMEOUT,
                allow_redirects=False,
            )
        except requests.exceptions.Timeout:
            raise AnthropicModelsError("Timed out talking to Anthropic.") from None
        except requests.exceptions.RequestException:
            raise AnthropicModelsError(
                "Could not reach api.anthropic.com. Check the server's internet connection."
            ) from None

        if response.status_code != 200:
            raise AnthropicModelsError(_describe_http_error(response, "list models"))
        try:
            body = response.json()
        except ValueError:
            raise AnthropicModelsError("Anthropic sent a response that was not JSON.") from None

        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list):
            raise AnthropicModelsError("Anthropic sent an unexpected model list.")
        models.extend(m for m in (_model_summary(i) for i in data if isinstance(i, dict)) if m)

        last_id = body.get("last_id")
        if not body.get("has_more") or not isinstance(last_id, str):
            break
        params = {"limit": 1000, "after_id": last_id}
    return models


def list_models(api_key: str, *, refresh: bool = False) -> tuple[list[dict], bool]:
    """Models the key can use, newest first. Returns (models, served_from_cache).

    Successful answers are cached for the current key for CACHE_TTL_SECONDS
    (a different key misses the cache). Failures are
    not cached, so fixing the key or the network shows up on the next try.
    Raises AnthropicModelsError with a message that is safe to show.
    """
    now = time.monotonic()
    if not refresh:
        cached = _cache.get(api_key, now)
        if cached is not None:
            return cached, True

    models = _fetch_models(api_key)
    _cache.put(api_key, models, now)
    return [dict(m) for m in models], False


def fallback_models() -> list[dict]:
    return [
        {**m, "lifecycle": None, "created_at": None}
        for m in FALLBACK_MODELS
    ]


def check_model(api_key: str, model: str) -> tuple[bool, str]:
    """Send the smallest possible request (max_tokens=1) with this model.

    Costs a handful of input tokens. Returns (ok, message safe to show).
    """
    try:
        response = requests.post(
            f"{ANTHROPIC_API_BASE}/v1/messages",
            headers=_headers(api_key),
            json={
                "model": model,
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "ping"}],
            },
            timeout=_TIMEOUT,
            allow_redirects=False,
        )
    except requests.exceptions.Timeout:
        return False, "Timed out talking to Anthropic."
    except requests.exceptions.RequestException:
        return False, "Could not reach api.anthropic.com. Check the server's internet connection."

    if response.status_code == 200:
        return True, f"Connected to Anthropic. Model '{model}' answered."

    err_type, message = _error_type_and_message(response)
    if response.status_code == 404 or err_type == "not_found_error":
        return False, (
            f"Model '{model}' was not found. It may be retired, mistyped, or not "
            "available to this API key. Pick another model from the list."
        )
    if response.status_code == 400 and message and "model" in message.lower():
        return False, f"Anthropic did not accept model '{model}': {message}"
    return False, _describe_http_error(response, f"use model '{model}'")
