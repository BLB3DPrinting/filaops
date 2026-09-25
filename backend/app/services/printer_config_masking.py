"""
Secret masking for a printer's ``connection_config`` JSON (SEC-403).

``connection_config`` is free-form JSON. Brand adapters and plugins keep
credentials in it, sometimes nested (``{"mqtt": {"password": ...}}``) or
inside lists. API responses must never carry those values.

- ``mask_connection_config`` returns a copy with every sensitive value
  replaced by ``MASKED_VALUE``, at any depth.
- ``restore_masked_secrets`` runs on writes. Where the client sends
  ``MASKED_VALUE`` back for a sensitive key, the value stored at the same
  path is kept. The UI can round-trip a masked config without wiping or
  overwriting the real secret. The mask string itself is never stored.
"""
from copy import deepcopy
from typing import Any, Optional

MASKED_VALUE = "********"

# Key names (lower case, "-" read as "_") whose values are secrets. A key is
# also sensitive when it ends in "_" plus one of these names. That covers
# prefixed variants such as ``mqtt_access_code`` (read by the MQTT monitor),
# ``mqtt_password``, ``octoprint_api_key`` and ``refresh_token``.
SENSITIVE_CONFIG_KEYS = frozenset({
    "access_code",
    "api_key",
    "password",
    "token",
    "secret",
    "auth_token",
    "private_key",
})

_MISSING = object()


def is_sensitive_key(key: Any) -> bool:
    """Return True when a config key's value must not leave the server."""
    if not isinstance(key, str):
        return False
    normalized = key.strip().lower().replace("-", "_")
    if normalized in SENSITIVE_CONFIG_KEYS:
        return True
    return any(normalized.endswith(f"_{name}") for name in SENSITIVE_CONFIG_KEYS)


def _is_mask(value: Any) -> bool:
    return isinstance(value, str) and value == MASKED_VALUE


def mask_connection_config(config: Optional[dict]) -> dict:
    """Return a copy of *config* with every sensitive value masked.

    Walks nested dicts and lists. A sensitive key with a truthy value is
    replaced by ``MASKED_VALUE`` whatever its type, so a secret stored as an
    object is hidden too. Empty values are left as they are, so the UI can
    still tell "not set" from "set".
    """
    if not isinstance(config, dict):
        return {}
    return _mask(config)


def _mask(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: MASKED_VALUE if is_sensitive_key(key) and item else _mask(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_mask(item) for item in value]
    return value


def restore_masked_secrets(incoming: dict, stored: Optional[dict]) -> dict:
    """Merge a client-sent config with the stored one before saving.

    Returns *incoming* with each masked sensitive value swapped for the value
    stored at the same path (dict keys by name, list items by index). If
    nothing is stored at that path, the key is dropped instead of saving the
    mask string as a secret. Everything else in *incoming* is kept as sent,
    so this is still a full replacement of the config, as before.
    """
    return _restore(incoming, stored if stored is not None else _MISSING)


def _restore(incoming: Any, stored: Any) -> Any:
    if isinstance(incoming, dict):
        stored_map = stored if isinstance(stored, dict) else {}
        result = {}
        for key, value in incoming.items():
            if _is_mask(value) and is_sensitive_key(key):
                if key in stored_map:
                    result[key] = deepcopy(stored_map[key])
                continue
            result[key] = _restore(value, stored_map.get(key, _MISSING))
        return result
    if isinstance(incoming, list):
        stored_list = stored if isinstance(stored, list) else []
        return [
            _restore(item, stored_list[index] if index < len(stored_list) else _MISSING)
            for index, item in enumerate(incoming)
        ]
    return incoming
