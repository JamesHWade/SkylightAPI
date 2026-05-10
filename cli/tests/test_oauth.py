from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs

import httpx
import pytest

from skylight_cli.errors import ConfigError
from skylight_cli.oauth import OAuthToken, login_headless, refresh_oauth_token


def test_login_headless_exchanges_code_for_tokens() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(f"{request.method} {request.url.path}")
        if request.method == "GET" and request.url.path == "/auth/session/new":
            return httpx.Response(
                200,
                text='<input type="hidden" name="authenticity_token" value="csrf123" />',
            )
        if request.method == "POST" and request.url.path == "/auth/session":
            body = parse_qs(request.content.decode())
            assert body["authenticity_token"] == ["csrf123"]
            assert body["email"] == ["person@example.com"]
            assert body["password"] == ["secret"]
            return httpx.Response(302, headers={"location": "/home"})
        if request.method == "GET" and request.url.path == "/oauth/authorize":
            assert request.url.params["client_id"] == "skylight-mobile"
            assert request.url.params["skylight_api_client_device_fingerprint"] == "device-1"
            return httpx.Response(
                302,
                headers={"location": "https://ourskylight.com/welcome?code=AUTH_CODE"},
            )
        if request.method == "POST" and request.url.path == "/oauth/token":
            body = parse_qs(request.content.decode())
            assert body["grant_type"] == ["authorization_code"]
            assert body["code"] == ["AUTH_CODE"]
            return httpx.Response(
                200,
                json={
                    "access_token": "ACCESS",
                    "refresh_token": "REFRESH",
                    "expires_in": 3600,
                    "token_type": "Bearer",
                },
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    token = login_headless(
        base_url="https://app.ourskylight.com",
        email="person@example.com",
        password="secret",
        fingerprint="device-1",
        timeout=30,
        transport=httpx.MockTransport(handler),
    )

    assert token.authorization_header == "Bearer ACCESS"
    assert token.refresh_token == "REFRESH"
    assert seen == [
        "GET /auth/session/new",
        "POST /auth/session",
        "GET /oauth/authorize",
        "POST /oauth/token",
    ]


def test_refresh_oauth_token_returns_rotated_tokens() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/oauth/token"
        body = parse_qs(request.content.decode())
        assert body["grant_type"] == ["refresh_token"]
        assert body["refresh_token"] == ["OLD_REFRESH"]
        assert body["skylight_api_client_device_fingerprint"] == ["device-1"]
        return httpx.Response(
            200,
            json={
                "access_token": "NEW_ACCESS",
                "refresh_token": "NEW_REFRESH",
                "expires_in": 3600,
                "token_type": "Bearer",
            },
        )

    token = refresh_oauth_token(
        base_url="https://app.ourskylight.com",
        refresh_token="OLD_REFRESH",
        fingerprint="device-1",
        timeout=30,
        transport=httpx.MockTransport(handler),
    )

    assert token.authorization_header == "Bearer NEW_ACCESS"
    assert token.refresh_token == "NEW_REFRESH"


def test_login_headless_treats_form_rerender_200_as_bad_credentials() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/auth/session/new":
            return httpx.Response(
                200,
                text='<input type="hidden" name="authenticity_token" value="csrf123" />',
            )
        if request.url.path == "/auth/session":
            # Rails re-renders the login form with a 200 on bad credentials.
            return httpx.Response(200, text="<html>bad credentials</html>")
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    with pytest.raises(ConfigError, match="login was rejected"):
        login_headless(
            base_url="https://app.ourskylight.com",
            email="person@example.com",
            password="wrong",
            fingerprint="device-1",
            timeout=30,
            transport=httpx.MockTransport(handler),
        )


def test_oauth_token_is_expired_uses_issued_at_and_expires_in() -> None:
    issued = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    token = OAuthToken(
        access_token="A",
        refresh_token=None,
        expires_in=3600,
        token_type="Bearer",
        issued_at=issued,
    )

    assert token.expires_at == issued + timedelta(seconds=3600)
    assert token.is_expired(now=issued + timedelta(seconds=3500), leeway=timedelta(0)) is False
    assert token.is_expired(now=issued + timedelta(seconds=3600)) is True


def test_oauth_token_is_expired_returns_false_when_unknown() -> None:
    token = OAuthToken(
        access_token="A",
        refresh_token=None,
        expires_in=None,
        token_type="Bearer",
    )

    assert token.expires_at is None
    assert token.is_expired() is False


def test_post_oauth_token_accepts_string_int_expires_in() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "access_token": "ACCESS",
                "refresh_token": "REFRESH",
                "expires_in": "3600",
                "token_type": "Bearer",
            },
        )

    token = refresh_oauth_token(
        base_url="https://app.ourskylight.com",
        refresh_token="OLD",
        fingerprint="device-1",
        timeout=30,
        transport=httpx.MockTransport(handler),
    )
    assert token.expires_in == 3600


def test_post_oauth_token_rejects_unparseable_expires_in() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "access_token": "ACCESS",
                "refresh_token": "REFRESH",
                "expires_in": "soon",
                "token_type": "Bearer",
            },
        )

    with pytest.raises(ConfigError, match="expires_in"):
        refresh_oauth_token(
            base_url="https://app.ourskylight.com",
            refresh_token="OLD",
            fingerprint="device-1",
            timeout=30,
            transport=httpx.MockTransport(handler),
        )
