"""
Secret masking for a printer's ``connection_config`` JSON (SEC-403).

``connection_config`` is free-form JSON. Brand adapters and plugins keep
credentials in it, sometimes nested (``{"mqtt": {"password": ...}}``) or
inside lists. API responses must never carry those values.

- ``mask_connection_config`` returns a copy with every sensitive value
  replaced by ``MASKED_VALUE``, at any depth. A password inside a URL
  (``scheme://user:pw@host``) is masked too.
- ``restore_masked_secrets`` runs on writes. Where the client sends
  ``MASKED_VALUE`` back for a sensitive key, the value stored at the same
  path is kept. The UI can round-trip a masked config without wiping or
  overwriting the real secret. The mask string itself is never stored.

A stored secret is only kept while it still goes to the same place. If the
write changes where the printer connects (an address, host, port or URL
key next to the secret or above it, or the printer's ``ip_address``
column), keeping it would let anyone who can edit a printer send its
secret to a host they control. ``restore_masked_secrets`` raises
``SecretReuseError`` instead, and the caller asks for the secret again.
"""
import re
from copy import deepcopy
from typing import Any, Optional

MASKED_VALUE = "********"

# Key names whose values are secrets, after normalizing: camelCase is split
# ("accessCode" -> "access_code"), "-", "." and spaces read as "_", and all
# lower case. A key is also sensitive when it ends in "_" plus one of these
# names, which covers prefixed variants such as ``mqtt_access_code`` (read
# by the MQTT monitor), ``x_api_key``, ``client_secret`` and
# ``refresh_token``. A trailing "s" is ignored, so ``api_keys`` and
# ``credentials`` match too.
SENSITIVE_CONFIG_KEYS = frozenset({
    "access_code",
    "key",
    "password",
    "passwd",
    "pass",
    "passcode",
    "passphrase",
    "token",
    "secret",
    "authorization",
    "credential",
    "cookie",
})

# Keys that say where the printer connects, matched the same way (exact
# name, or "_" plus the name as a suffix: ``mqtt_host``, ``base_url``,
# ``serial_port``). Changing one of them stops stored secrets at that level
# and below from being reused.
CONNECTION_TARGET_KEYS = frozenset({
    "ip",
    "ip_address",
    "address",
    "host",
    "hostname",
    "server",
    "port",
    "url",
    "uri",
    "endpoint",
})

_MISSING = object()

_CAMEL_ACRONYM = re.compile(r"([A-Z]+)([A-Z][a-z])")
_CAMEL_WORD = re.compile(r"([a-z0-9])([A-Z])")
_SEPARATORS = re.compile(r"[\s.\-]+")
# scheme://userinfo@ ... The userinfo runs to the last "@" before the path.
_URL_USERINFO = re.compile(r"^(?P<scheme>[A-Za-z][A-Za-z0-9+.\-]*://)(?P<userinfo>[^/?#]*)@")


class SecretReuseError(ValueError):
    """A write would keep stored secrets for a printer that now connects elsewhere."""

    def __init__(self, paths: list[str]):
        self.paths = paths
        super().__init__(
            "stored secrets not reused after a connection change: " + ", ".join(paths)
        )


def _normalize_key(key: str) -> str:
    name = _CAMEL_ACRONYM.sub(r"\1_\2", key.strip())
    name = _CAMEL_WORD.sub(r"\1_\2", name)
    return _SEPARATORS.sub("_", name).lower()


def _key_matches(key: Any, names: frozenset) -> bool:
    if not isinstance(key, str):
        return False
    normalized = _normalize_key(key)
    candidates = {normalized}
    if len(normalized) > 1 and normalized.endswith("s"):
        candidates.add(normalized[:-1])
    return any(
        candidate in names or any(candidate.endswith(f"_{name}") for name in names)
        for candidate in candidates
    )


def is_sensitive_key(key: Any) -> bool:
    """Return True when a config key's value must not leave the server."""
    return _key_matches(key, SENSITIVE_CONFIG_KEYS)


def is_connection_target_key(key: Any) -> bool:
    """Return True when a config key says where the printer connects."""
    return not is_sensitive_key(key) and _key_matches(key, CONNECTION_TARGET_KEYS)


def _is_mask(value: Any) -> bool:
    return isinstance(value, str) and value == MASKED_VALUE


# ---------------------------------------------------------------------------
# Passwords inside URLs
# ---------------------------------------------------------------------------

def _split_url_password(value: str):
    """Return (scheme, user, password, rest) for a URL that carries a password."""
    match = _URL_USERINFO.match(value)
    if not match:
        return None
    user, sep, password = match.group("userinfo").partition(":")
    if not sep or not password:
        return None
    return match.group("scheme"), user, password, value[match.end():]


def _mask_url(value: str) -> str:
    parts = _split_url_password(value)
    if parts is None:
        return value
    scheme, user, _, rest = parts
    return f"{scheme}{user}:{MASKED_VALUE}@{rest}"


# ---------------------------------------------------------------------------
# Masking (responses)
# ---------------------------------------------------------------------------

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
    if isinstance(value, str):
        return _mask_url(value)
    return value


def _non_secret_view(value: Any) -> Any:
    """*value* with its secrets left out, used to match list items."""
    if isinstance(value, dict):
        return {
            key: _non_secret_view(item)
            for key, item in value.items()
            if not is_sensitive_key(key)
        }
    if isinstance(value, list):
        return [_non_secret_view(item) for item in value]
    if isinstance(value, str):
        return _mask_url(value)
    return value


def _target_values(config: dict) -> dict:
    """The connection-target keys of one dict level, normalized for comparing."""
    values = {}
    for key, value in config.items():
        if not is_connection_target_key(key):
            continue
        if isinstance(value, str):
            value = value.strip() or None
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            value = str(value)
        if value is not None:
            values[_normalize_key(key)] = value
    return values


# ---------------------------------------------------------------------------
# Restoring (writes)
# ---------------------------------------------------------------------------

def restore_masked_secrets(
    incoming: dict,
    stored: Optional[dict],
    *,
    retargeted: bool = False,
) -> dict:
    """Merge a client-sent config with the stored one before saving.

    Returns *incoming* with each masked sensitive value swapped for the value
    stored at the same path. Dict keys match by name. List items match by
    index when the list is unchanged apart from its secrets. Otherwise an
    item matches the stored item with the same non-secret content, if that
    content is unique in both lists.

    A mask with nothing to restore is dropped, so the mask string is never
    saved as a secret. That includes a list item that was edited, or that
    can't be told apart from another one: the client has to send that
    item's secrets again.

    Pass ``retargeted=True`` when the printer's address changed outside this
    JSON (the ``ip_address`` column). Raises ``SecretReuseError`` when a
    masked value would keep a stored secret although the connection target
    changed at its level or above.

    Everything else in *incoming* is kept as sent, so this is still a full
    replacement of the config, as before.
    """
    blocked: list[str] = []
    result = _restore(
        incoming,
        stored if stored is not None else _MISSING,
        retargeted=retargeted,
        path="",
        blocked=blocked,
    )
    if blocked:
        raise SecretReuseError(blocked)
    return result


def _join(path: str, key: Any) -> str:
    return f"{path}.{key}" if path else str(key)


def _restore(incoming: Any, stored: Any, *, retargeted: bool, path: str, blocked: list) -> Any:
    if isinstance(incoming, dict):
        stored_map = stored if isinstance(stored, dict) else {}
        if stored_map and _target_values(incoming) != _target_values(stored_map):
            retargeted = True
        result = {}
        for key, value in incoming.items():
            if _is_mask(value) and is_sensitive_key(key):
                if key in stored_map:
                    if retargeted:
                        blocked.append(_join(path, key))
                    else:
                        result[key] = deepcopy(stored_map[key])
                continue
            result[key] = _restore(
                value,
                stored_map.get(key, _MISSING),
                retargeted=retargeted,
                path=_join(path, key),
                blocked=blocked,
            )
        return result

    if isinstance(incoming, list):
        stored_list = stored if isinstance(stored, list) else []
        matches = _match_list_items(incoming, stored_list)
        return [
            _restore(
                item,
                stored_list[matches[index]] if index in matches else _MISSING,
                retargeted=retargeted,
                path=f"{path}[{index}]",
                blocked=blocked,
            )
            for index, item in enumerate(incoming)
        ]

    if isinstance(incoming, str):
        parts = _split_url_password(incoming)
        if parts is None or parts[2] != MASKED_VALUE:
            return incoming
        # A URL names its own host, so it matches only a stored URL with the
        # same scheme, user, host and path. The stored password is kept then.
        if isinstance(stored, str) and _mask_url(stored) == incoming:
            return stored
        if isinstance(stored, str) and _split_url_password(stored) is not None:
            blocked.append(path)
        scheme, user, _, rest = parts
        return f"{scheme}{user}@{rest}" if user else f"{scheme}{rest}"

    return incoming


def _match_list_items(incoming: list, stored_list: list) -> dict:
    """Map incoming list indexes to stored indexes (see restore_masked_secrets)."""
    incoming_views = [_non_secret_view(item) for item in incoming]
    stored_views = [_non_secret_view(item) for item in stored_list]

    # Unchanged apart from secrets: a plain round trip, match by index.
    if incoming_views == stored_views:
        return {index: index for index in range(len(incoming))}

    # Otherwise an item's non-secret content is its identity. It must be
    # unique on both sides, or we can't tell which stored secret is its own.
    matches: dict[int, int] = {}
    for index, view in enumerate(incoming_views):
        if incoming_views.count(view) != 1:
            continue
        stored_indexes = [i for i, stored_view in enumerate(stored_views) if stored_view == view]
        if len(stored_indexes) == 1:
            matches[index] = stored_indexes[0]
    return matches
