"""test_chirpstack_auth.py — unit tests for ChirpStack token handling.

Regression cover for finding B-1 of the 2026-08-01 field diagnosis: the
cockpit fetched its admin-login JWT once at start-up and never renewed it.
ChirpStack issues that token with a 24 h lifetime, so exactly one day later
every ChirpStack-backed feature failed with UNAUTHENTICATED: ExpiredSignature
while the process itself stayed healthy — /healthz kept answering 200 and the
container health check stayed green, so nothing looked broken. On 2026-07-14
that produced 324 consecutive failures over five hours, and the cockpit ran
three days in that state before the next restart.

Two mechanisms are tested here:
  - get_token() caches and renews proactively, shortly before expiry;
  - _renew_token_on_auth_error retries once with a fresh token, the safety net
    for the case proactive renewal cannot predict — the field host has no
    buffered RTC, so its clock can jump forward by hours after NTP sync and
    retire a token that looked fresh when issued (finding B-4).

No real ChirpStack server involved.
"""
import base64
import json
import time
from unittest.mock import MagicMock, patch

import grpc
import pytest

from app import chirpstack as cs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_jwt(exp: float | None) -> str:
    """Build a JWT-shaped string whose payload carries the given exp claim."""
    claims = {"aud": "chirpstack", "iss": "chirpstack", "typ": "user"}
    if exp is not None:
        claims["exp"] = exp
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"header.{payload}.signature"


def _rpc_error(code: grpc.StatusCode, details: str = "boom") -> grpc.RpcError:
    """A grpc.RpcError that answers .code() and .details() like a real one."""
    err = grpc.RpcError()
    err.code = lambda: code
    err.details = lambda: details
    return err


@pytest.fixture(autouse=True)
def _reset_token_cache(monkeypatch):
    """Every test starts with an empty cache and no API key configured."""
    monkeypatch.setattr(cs, "_cached_token", None)
    monkeypatch.setattr(cs, "_cached_token_expiry", 0.0)
    monkeypatch.setattr(cs.config, "CHIRPSTACK_API_KEY", "")
    yield


def _login_stub(jwt: str) -> MagicMock:
    """Patchable InternalServiceStub whose Login() returns the given JWT."""
    stub = MagicMock()
    stub.Login.return_value = MagicMock(jwt=jwt)
    return stub


# ---------------------------------------------------------------------------
# API key path
# ---------------------------------------------------------------------------


def test_api_key_is_used_verbatim_and_never_logs_in(monkeypatch):
    monkeypatch.setattr(cs.config, "CHIRPSTACK_API_KEY", "real-api-key")
    stub = _login_stub(_make_jwt(time.time() + 86400))

    with patch.object(cs.internal_pb2_grpc, "InternalServiceStub", return_value=stub):
        assert cs.get_token(MagicMock()) == "real-api-key"

    stub.Login.assert_not_called()
    assert cs.uses_api_key() is True


@pytest.mark.parametrize("value", ["", "change-me-api-key-from-chirpstack-ui"])
def test_placeholder_or_empty_key_falls_back_to_admin_login(monkeypatch, value):
    """The shipped .env.example placeholder must not be sent as a credential."""
    monkeypatch.setattr(cs.config, "CHIRPSTACK_API_KEY", value)
    stub = _login_stub(_make_jwt(time.time() + 86400))

    with patch.object(cs.internal_pb2_grpc, "InternalServiceStub", return_value=stub):
        token = cs.get_token(MagicMock())

    stub.Login.assert_called_once()
    assert token.startswith("header.")
    assert cs.uses_api_key() is False


# ---------------------------------------------------------------------------
# Caching and proactive renewal
# ---------------------------------------------------------------------------


def test_token_is_cached_between_calls():
    """A valid cached token must not trigger a second login."""
    stub = _login_stub(_make_jwt(time.time() + 86400))
    channel = MagicMock()

    with patch.object(cs.internal_pb2_grpc, "InternalServiceStub", return_value=stub):
        first = cs.get_token(channel)
        second = cs.get_token(channel)

    assert first == second
    stub.Login.assert_called_once()


def test_expired_token_is_renewed():
    """This is the actual B-1 regression: a 24 h-old token must be replaced."""
    old, new = _make_jwt(time.time() - 60), _make_jwt(time.time() + 86400)
    stub = MagicMock()
    stub.Login.side_effect = [MagicMock(jwt=old), MagicMock(jwt=new)]
    channel = MagicMock()

    with patch.object(cs.internal_pb2_grpc, "InternalServiceStub", return_value=stub):
        first = cs.get_token(channel)
        second = cs.get_token(channel)

    assert first == old
    assert second == new
    assert stub.Login.call_count == 2


def test_token_is_renewed_inside_the_safety_margin():
    """Renew shortly *before* expiry so a request never travels with a token
    that dies mid-flight."""
    almost = _make_jwt(time.time() + cs._TOKEN_REFRESH_MARGIN - 30)
    fresh = _make_jwt(time.time() + 86400)
    stub = MagicMock()
    stub.Login.side_effect = [MagicMock(jwt=almost), MagicMock(jwt=fresh)]

    with patch.object(cs.internal_pb2_grpc, "InternalServiceStub", return_value=stub):
        cs.get_token(MagicMock())
        assert cs.get_token(MagicMock()) == fresh

    assert stub.Login.call_count == 2


def test_force_refresh_bypasses_the_cache():
    a, b = _make_jwt(time.time() + 86400), _make_jwt(time.time() + 86400)
    stub = MagicMock()
    stub.Login.side_effect = [MagicMock(jwt=a), MagicMock(jwt=b)]

    with patch.object(cs.internal_pb2_grpc, "InternalServiceStub", return_value=stub):
        cs.get_token(MagicMock())
        assert cs.get_token(MagicMock(), force_refresh=True) == b

    assert stub.Login.call_count == 2


def test_token_without_exp_claim_gets_a_fallback_lifetime():
    """An unreadable token must still be renewed eventually, not cached forever."""
    stub = _login_stub("not-a-jwt")

    with patch.object(cs.internal_pb2_grpc, "InternalServiceStub", return_value=stub):
        cs.get_token(MagicMock())

    assert cs._cached_token_expiry <= time.time() + cs._TOKEN_FALLBACK_TTL + 1
    assert cs._cached_token_expiry > time.time()


@pytest.mark.parametrize("bad", ["not-a-jwt", "a.b", "a.!!!.c", ""])
def test_jwt_expiry_survives_malformed_input(bad):
    assert cs._jwt_expiry(bad) is None


# ---------------------------------------------------------------------------
# Reactive retry
# ---------------------------------------------------------------------------


def test_retry_decorator_renews_once_on_unauthenticated():
    """The exact failure seen in the field: first call rejected, retry succeeds."""
    calls = []

    @cs._renew_token_on_auth_error
    def fake_call(channel, token, arg):
        calls.append(token)
        if len(calls) == 1:
            raise _rpc_error(grpc.StatusCode.UNAUTHENTICATED, "ExpiredSignature")
        return f"ok:{arg}"

    with patch.object(cs, "get_token", return_value="fresh") as mock_token:
        assert fake_call(MagicMock(), "stale", "x") == "ok:x"

    assert calls == ["stale", "fresh"]
    mock_token.assert_called_once()
    assert mock_token.call_args.kwargs["force_refresh"] is True


def test_retry_decorator_does_not_loop_forever():
    """A token that stays rejected must surface, not retry endlessly."""
    calls = []

    @cs._renew_token_on_auth_error
    def always_rejected(channel, token):
        calls.append(token)
        raise _rpc_error(grpc.StatusCode.UNAUTHENTICATED, "ExpiredSignature")

    with patch.object(cs, "get_token", return_value="fresh"):
        with pytest.raises(grpc.RpcError):
            always_rejected(MagicMock(), "stale")

    assert len(calls) == 2


@pytest.mark.parametrize(
    "code",
    [
        grpc.StatusCode.NOT_FOUND,
        grpc.StatusCode.UNAVAILABLE,
        grpc.StatusCode.PERMISSION_DENIED,
    ],
)
def test_retry_decorator_passes_other_errors_straight_through(code):
    """Only auth failures justify a new login — NOT_FOUND in particular is a
    control-flow signal that callers like get_device_addr depend on."""

    @cs._renew_token_on_auth_error
    def fails(channel, token):
        raise _rpc_error(code)

    with patch.object(cs, "get_token") as mock_token:
        with pytest.raises(grpc.RpcError) as excinfo:
            fails(MagicMock(), "tok")

    assert excinfo.value.code() == code
    mock_token.assert_not_called()


def test_public_calls_carry_the_retry_decorator():
    """Guard against a new gRPC helper being added without the safety net."""
    for name in (
        "find_tenant_id",
        "find_app_id",
        "find_or_create_tenant",
        "find_or_create_application",
        "find_or_create_profile",
        "find_profile_id_by_name",
        "set_device_profile",
        "register_device",
        "list_devices",
        "get_device_addr",
        "enqueue_downlink",
        "get_device_queue",
    ):
        fn = getattr(cs, name)
        assert getattr(fn, "__wrapped__", None) is not None, (
            f"{name} is missing @_renew_token_on_auth_error"
        )
