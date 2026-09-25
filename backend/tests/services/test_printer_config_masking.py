"""Unit tests for app/services/printer_config_masking.py (SEC-403)."""
import copy

import pytest

from app.services.printer_config_masking import (
    MASKED_VALUE,
    is_sensitive_key,
    mask_connection_config,
    restore_masked_secrets,
)


@pytest.mark.parametrize("key", [
    "access_code", "api_key", "password", "token", "secret", "auth_token",
    "private_key", "mqtt_access_code", "mqtt_password", "octoprint_api_key",
    "refresh_token", "client_secret", "API-Key", "Password",
])
def test_sensitive_keys(key):
    assert is_sensitive_key(key)


@pytest.mark.parametrize("key", [
    "host", "username", "mqtt_topic", "serial", "token_expires_at",
    "password_hint_shown", "last_telemetry", 3, None,
])
def test_non_sensitive_keys(key):
    assert not is_sensitive_key(key)


def test_mask_walks_nested_dicts_and_lists():
    config = {
        "host": "printer.local",
        "password": "top",
        "mqtt": {"user": "bblp", "password": "nested", "tls": {"private_key": "pem"}},
        "accounts": [{"token": "t1"}, {"token": ""}, ["x", {"secret": "deep"}]],
        "token": {"value": "abc", "expires": 1},
    }
    original = copy.deepcopy(config)

    masked = mask_connection_config(config)

    assert masked == {
        "host": "printer.local",
        "password": MASKED_VALUE,
        "mqtt": {"user": "bblp", "password": MASKED_VALUE, "tls": {"private_key": MASKED_VALUE}},
        "accounts": [{"token": MASKED_VALUE}, {"token": ""}, ["x", {"secret": MASKED_VALUE}]],
        "token": MASKED_VALUE,
    }
    assert config == original, "masking must not mutate the stored config"


@pytest.mark.parametrize("config", [None, {}, [], "not-a-dict"])
def test_mask_non_dict_or_empty_returns_empty_dict(config):
    assert mask_connection_config(config) == {}


def test_restore_round_trip_returns_stored_config():
    stored = {
        "host": "printer.local",
        "mqtt": {"user": "bblp", "password": "nested"},
        "accounts": [{"name": "a", "token": "t1"}, {"name": "b", "token": "t2"}],
    }
    assert restore_masked_secrets(mask_connection_config(stored), stored) == stored


def test_restore_keeps_new_values_and_drops_unknown_masks():
    stored = {"mqtt": {"password": "old"}, "accounts": [{"token": "t1"}]}
    incoming = {
        "mqtt": {"password": "new", "api_key": MASKED_VALUE},
        "accounts": [{"token": MASKED_VALUE}, {"token": MASKED_VALUE}],
        "host": MASKED_VALUE,  # not a secret key: kept as sent
    }

    result = restore_masked_secrets(incoming, stored)

    assert result == {
        "mqtt": {"password": "new"},
        "accounts": [{"token": "t1"}, {}],
        "host": MASKED_VALUE,
    }


def test_restore_does_not_share_objects_with_stored_config():
    stored = {"token": {"value": "abc"}}
    result = restore_masked_secrets({"token": MASKED_VALUE}, stored)
    assert result == stored
    assert result["token"] is not stored["token"]


def test_restore_with_nothing_stored_drops_masks():
    assert restore_masked_secrets({"password": MASKED_VALUE, "host": "h"}, None) == {"host": "h"}
