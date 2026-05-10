from __future__ import annotations

from urllib.parse import parse_qs

import httpx

from skylight_cli.oauth import login_headless, refresh_oauth_token


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
