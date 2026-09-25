"""Unit tests for app/services/printer_config_masking.py (SEC-403)."""
import copy

import pytest

from app.services.printer_config_masking import (
    MASKED_VALUE,
    SecretReuseError,
    is_connection_target_key,
    is_sensitive_key,
    mask_connection_config,
    restore_masked_secrets,
)


@pytest.mark.parametrize("key", [
    "access_code", "api_key", "password", "token", "secret", "auth_token",
    "private_key", "mqtt_access_code", "mqtt_password", "octoprint_api_key",
    "refresh_token", "client_secret", "API-Key", "Password",
    # camelCase and acronyms (CodeRabbit review on PR #973)
    "apiKey", "accessCode", "accessToken", "mqttAccessCode", "APIKey", "X-Api-Key",
    # other names and plurals (security review on PR #973)
    "key", "client_key", "passwd", "mqtt_pass", "passcode", "passphrase",
    "api_keys", "tokens", "credentials", "Authorization", "cookie",
])
def test_sensitive_keys(key):
    assert is_sensitive_key(key)


@pytest.mark.parametrize("key", [
    "host", "username", "mqtt_topic", "serial", "token_expires_at",
    "password_hint_shown", "last_telemetry", "ip_address", "address", "status",
    "bypass", "hotkey", "key_id", 3, None,
])
def test_non_sensitive_keys(key):
    assert not is_sensitive_key(key)


@pytest.mark.parametrize("key", [
    "ip", "ip_address", "ipAddress", "host", "mqtt_host", "hostname", "port",
    "mqtt_port", "serial_port", "url", "base_url", "baseUrl", "uri", "endpoint", "server",
])
def test_connection_target_keys(key):
    assert is_connection_target_key(key)


@pytest.mark.parametrize("key", ["serial", "mqtt_topic", "name", "zip", "access_code", "api_url_key"])
def test_non_target_keys(key):
    assert not is_connection_target_key(key)


def test_mask_covers_camel_case_headers_and_plurals():
    config = {
        "apiKey": "s1",
        "accessCode": "s2",
        "headers": {"Authorization": "Bearer t1", "Accept": "application/json"},
        "api_keys": ["k1", "k2"],
        "client_key": "s3",
        "passwd": "s4",
        "host": "printer.local",
    }

    masked = mask_connection_config(config)

    assert masked == {
        "apiKey": MASKED_VALUE,
        "accessCode": MASKED_VALUE,
        "headers": {"Authorization": MASKED_VALUE, "Accept": "application/json"},
        "api_keys": MASKED_VALUE,
        "client_key": MASKED_VALUE,
        "passwd": MASKED_VALUE,
        "host": "printer.local",
    }


def test_mask_hides_passwords_inside_urls():
    config = {
        "url": "mqtts://bblp:SECRET12@192.168.1.5:8883/device",
        "mirrors": ["https://user:p@ss@example.com/a", "https://example.com/b"],
        "plain": "https://example.com/c?x=1",
        "user_only": "ssh://git@example.com/repo",
    }

    masked = mask_connection_config(config)

    assert masked == {
        "url": f"mqtts://bblp:{MASKED_VALUE}@192.168.1.5:8883/device",
        "mirrors": [f"https://user:{MASKED_VALUE}@example.com/a", "https://example.com/b"],
        "plain": "https://example.com/c?x=1",
        "user_only": "ssh://git@example.com/repo",
    }
    assert "SECRET12" not in repr(masked) and "p@ss" not in repr(masked)


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
        "label": MASKED_VALUE,  # not a secret key: kept as sent
    }

    result = restore_masked_secrets(incoming, stored)

    # The two account items can't be told apart, so neither gets "t1".
    assert result == {
        "mqtt": {"password": "new"},
        "accounts": [{}, {}],
        "label": MASKED_VALUE,
    }


def test_restore_does_not_share_objects_with_stored_config():
    stored = {"token": {"value": "abc"}}
    result = restore_masked_secrets({"token": MASKED_VALUE}, stored)
    assert result == stored
    assert result["token"] is not stored["token"]


def test_restore_with_nothing_stored_drops_masks():
    assert restore_masked_secrets({"password": MASKED_VALUE, "host": "h"}, None) == {"host": "h"}


# ---------------------------------------------------------------------------
# List items are matched by their non-secret content, not only by index
# (CodeRabbit review on PR #973)
# ---------------------------------------------------------------------------

def test_restore_list_item_after_an_earlier_item_is_removed():
    stored = {"accounts": [{"name": "a", "token": "tokA"}, {"name": "b", "token": "tokB"}]}
    incoming = {"accounts": [{"name": "b", "token": MASKED_VALUE}]}

    assert restore_masked_secrets(incoming, stored) == {
        "accounts": [{"name": "b", "token": "tokB"}],
    }


def test_restore_list_items_after_reordering():
    stored = {"accounts": [{"name": "a", "token": "tokA"}, {"name": "b", "token": "tokB"}]}
    incoming = {"accounts": [
        {"name": "b", "token": MASKED_VALUE},
        {"name": "a", "token": MASKED_VALUE},
    ]}

    assert restore_masked_secrets(incoming, stored) == {
        "accounts": [{"name": "b", "token": "tokB"}, {"name": "a", "token": "tokA"}],
    }


def test_restore_drops_mask_of_a_changed_list_item():
    """An item whose other fields changed can't be matched; its secret is not reused."""
    stored = {"accounts": [{"name": "a", "token": "tokA"}, {"name": "b", "token": "tokB"}]}
    incoming = {"accounts": [{"name": "c", "token": MASKED_VALUE}]}

    assert restore_masked_secrets(incoming, stored) == {"accounts": [{"name": "c"}]}


def test_restore_drops_ambiguous_list_masks():
    stored = {"accounts": [{"token": "tok1"}, {"token": "tok2"}]}
    incoming = {"accounts": [{"note": "x"}, {"token": MASKED_VALUE}, {"token": MASKED_VALUE}]}

    # Index 0 no longer matches, and items 1 and 2 could each be either
    # stored item, so neither gets a stored token.
    result = restore_masked_secrets(incoming, stored)

    assert result == {"accounts": [{"note": "x"}, {}, {}]}


# ---------------------------------------------------------------------------
# Passwords inside URLs
# ---------------------------------------------------------------------------

def test_restore_url_password_when_the_url_is_unchanged():
    stored = {"url": "mqtts://bblp:SECRET12@192.168.1.5:8883/device"}

    assert restore_masked_secrets(mask_connection_config(stored), stored) == stored


def test_url_password_is_not_reused_for_another_host():
    stored = {"url": "mqtts://bblp:SECRET12@192.168.1.5:8883/device"}
    incoming = {"url": f"mqtts://bblp:{MASKED_VALUE}@203.0.113.66:8883/device"}

    with pytest.raises(SecretReuseError) as exc:
        restore_masked_secrets(incoming, stored)
    assert exc.value.paths == ["url"]


def test_masked_url_password_with_nothing_stored_is_stripped():
    incoming = {"url": f"mqtts://bblp:{MASKED_VALUE}@192.168.1.5:8883/device"}

    assert restore_masked_secrets(incoming, None) == {"url": "mqtts://bblp@192.168.1.5:8883/device"}


# ---------------------------------------------------------------------------
# A stored secret is not reused once the connection target changes
# (security review on PR #973)
# ---------------------------------------------------------------------------

def test_masked_secret_rejected_when_a_host_next_to_it_changes():
    stored = {"access_code": "SECRET12", "mqtt_host": "192.168.1.5"}
    incoming = {"access_code": MASKED_VALUE, "mqtt_host": "203.0.113.66"}

    with pytest.raises(SecretReuseError) as exc:
        restore_masked_secrets(incoming, stored)
    assert exc.value.paths == ["access_code"]
    assert "SECRET12" not in str(exc.value)


def test_masked_secret_rejected_when_the_host_is_removed():
    """Dropping mqtt_host makes the monitor fall back to another address."""
    stored = {"access_code": "SECRET12", "mqtt_host": "192.168.1.5"}

    with pytest.raises(SecretReuseError):
        restore_masked_secrets({"access_code": MASKED_VALUE}, stored)


def test_masked_secret_rejected_when_the_ip_column_changed():
    stored = {"access_code": "SECRET12", "serial": "S1"}

    with pytest.raises(SecretReuseError):
        restore_masked_secrets({"access_code": MASKED_VALUE, "serial": "S1"}, stored, retargeted=True)


def test_nested_secret_rejected_when_a_parent_host_changes():
    stored = {"host": "printer.local", "mqtt": {"password": "pw"}}
    incoming = {"host": "evil.example", "mqtt": {"password": MASKED_VALUE}}

    with pytest.raises(SecretReuseError) as exc:
        restore_masked_secrets(incoming, stored)
    assert exc.value.paths == ["mqtt.password"]


def test_nested_host_change_only_affects_that_level():
    stored = {"access_code": "SECRET12", "cloud": {"url": "https://a.example", "token": "t"}}
    incoming = {"access_code": MASKED_VALUE, "cloud": {"url": "https://b.example", "token": MASKED_VALUE}}

    with pytest.raises(SecretReuseError) as exc:
        restore_masked_secrets(incoming, stored)
    assert exc.value.paths == ["cloud.token"]


def test_new_secret_with_new_host_is_accepted():
    stored = {"access_code": "SECRET12", "mqtt_host": "192.168.1.5"}
    incoming = {"access_code": "NEWCODE9", "mqtt_host": "192.168.1.6"}

    assert restore_masked_secrets(incoming, stored) == incoming


def test_same_target_written_differently_is_not_a_change():
    stored = {"access_code": "SECRET12", "port": 8883, "host": "printer.local"}
    incoming = {"access_code": MASKED_VALUE, "port": "8883", "host": " printer.local "}

    assert restore_masked_secrets(incoming, stored)["access_code"] == "SECRET12"


def test_retarget_with_no_stored_secret_is_fine():
    stored = {"mqtt_host": "192.168.1.5"}
    incoming = {"access_code": MASKED_VALUE, "mqtt_host": "192.168.1.6"}

    assert restore_masked_secrets(incoming, stored, retargeted=True) == {"mqtt_host": "192.168.1.6"}
