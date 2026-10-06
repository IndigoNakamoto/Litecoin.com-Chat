"""Shared admin bearer-token verifier: named operators (ADMIN_TOKENS) + legacy ADMIN_TOKEN."""

import pytest

from backend.utils.admin_auth import (
    LEGACY_OPERATOR,
    admin_operator,
    operator_from_request,
    parse_admin_tokens,
    verify_admin_token,
)


def test_parse_named_and_legacy_tokens():
    tokens = parse_admin_tokens(named=" alice:tok-a , bob:tok-b ,, nocolon, :empty, carol: ", legacy="shared")
    assert tokens == {"tok-a": "alice", "tok-b": "bob", "shared": LEGACY_OPERATOR}


def test_parse_same_token_twice_keeps_first_name():
    assert parse_admin_tokens(named="alice:dup,bob:dup", legacy="") == {"dup": "alice"}


def test_legacy_token_does_not_override_named_entry():
    # If the legacy value equals a named token, the name wins.
    assert parse_admin_tokens(named="alice:same", legacy="same") == {"same": "alice"}


def test_named_tokens_authenticate_and_report_operator(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKENS", "alice:tok-a,bob:tok-b")
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    assert admin_operator("Bearer tok-a") == "alice"
    assert admin_operator("Bearer tok-b") == "bob"
    assert admin_operator("bearer tok-b") == "bob"  # scheme is case-insensitive
    assert verify_admin_token("Bearer tok-a") is True
    # A token that was removed from the list no longer works.
    monkeypatch.setenv("ADMIN_TOKENS", "alice:tok-a")
    assert admin_operator("Bearer tok-b") is None
    assert verify_admin_token("Bearer tok-b") is False


def test_legacy_token_still_works(monkeypatch):
    monkeypatch.delenv("ADMIN_TOKENS", raising=False)
    monkeypatch.setenv("ADMIN_TOKEN", "shared")
    assert admin_operator("Bearer shared") == LEGACY_OPERATOR
    assert verify_admin_token("Bearer shared") is True
    assert verify_admin_token("Bearer wrong") is False


@pytest.mark.parametrize(
    "header",
    [None, "", "Bearer", "Bearer ", "Basic tok-a", "tok-a", "Bearer tok-a extra"],
)
def test_malformed_or_wrong_headers_are_rejected(monkeypatch, header):
    monkeypatch.setenv("ADMIN_TOKENS", "alice:tok-a")
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    assert admin_operator(header) is None
    assert verify_admin_token(header) is False


def test_no_tokens_configured_disables_auth(monkeypatch):
    monkeypatch.delenv("ADMIN_TOKENS", raising=False)
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    assert verify_admin_token("Bearer anything") is False


def test_operator_from_request(monkeypatch):
    monkeypatch.setenv("ADMIN_TOKENS", "alice:tok-a")
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)

    class _Req:
        def __init__(self, auth):
            self.headers = {"Authorization": auth} if auth else {}

    assert operator_from_request(_Req("Bearer tok-a")) == "alice"
    assert operator_from_request(_Req("Bearer nope")) == "unknown"
    assert operator_from_request(_Req(None)) == "unknown"


def test_every_admin_router_uses_the_shared_verifier():
    """No admin module may keep its own copy of the token check."""
    import inspect

    from backend.api.v1.admin import (
        auth,
        cache,
        incident,
        jobs,
        knowledge_candidates,
        llm_logs,
        redis,
        settings,
        usage,
        users,
    )

    for mod in (auth, cache, incident, jobs, knowledge_candidates, llm_logs, redis, settings, usage, users):
        src = inspect.getsource(mod)
        assert 'os.getenv("ADMIN_TOKEN")' not in src, mod.__name__
        assert "hmac.compare_digest" not in src, mod.__name__
