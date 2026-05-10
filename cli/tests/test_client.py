from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from skylight_cli.client import SkylightClient
from skylight_cli.config import Settings
from skylight_cli.errors import ApiError


def test_client_sends_auth_and_decodes_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer TOKEN"
        assert request.headers["skylight-api-version"] == "2026-03-01"
        assert request.url.path == "/api/frames/FRAME/categories"
        return httpx.Response(200, json={"data": []})

    client = SkylightClient(_settings(), transport=httpx.MockTransport(handler))

    assert client.request("GET", "/api/frames/FRAME/categories") == {"data": []}


def test_client_raises_api_error_with_response_body() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"errors": [{"title": "Unauthorized"}]})

    client = SkylightClient(_settings(), transport=httpx.MockTransport(handler))

    with pytest.raises(ApiError) as exc_info:
        client.request("GET", "/api/frames/FRAME/categories")

    assert exc_info.value.status_code == 401
    assert exc_info.value.body == {"errors": [{"title": "Unauthorized"}]}


def test_preview_redacts_auth_and_keeps_query() -> None:
    client = SkylightClient(_settings())

    preview = client.preview_request(
        "GET",
        "/api/frames/FRAME/chores",
        params={"after": "2026-05-01", "empty": None},
    )

    assert preview["headers"]["Authorization"] == "Bearer REDACTED"
    assert preview["url"] == "https://app.ourskylight.com/api/frames/FRAME/chores?after=2026-05-01"
    assert preview["params"] == {"after": "2026-05-01"}


def test_client_refreshes_once_on_401_and_persists_tokens(tmp_path: Path) -> None:
    calls: list[tuple[str, str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path, request.headers.get("Authorization")))
        if request.url.path == "/api/frames/FRAME/categories":
            if request.headers.get("Authorization") == "Bearer TOKEN":
                return httpx.Response(401, json={"errors": [{"title": "expired"}]})
            return httpx.Response(200, json={"data": []})
        if request.url.path == "/oauth/token":
            return httpx.Response(
                200,
                json={
                    "access_token": "NEW_TOKEN",
                    "refresh_token": "NEW_REFRESH",
                    "expires_in": 7200,
                    "token_type": "Bearer",
                },
            )
        return httpx.Response(404, json={"error": "not found"})

    config_path = tmp_path / "config.json"
    client = SkylightClient(
        _settings(config_path=config_path),
        transport=httpx.MockTransport(handler),
    )

    assert client.request("GET", "/api/frames/FRAME/categories") == {"data": []}
    assert calls == [
        ("GET", "/api/frames/FRAME/categories", "Bearer TOKEN"),
        ("POST", "/oauth/token", None),
        ("GET", "/api/frames/FRAME/categories", "Bearer NEW_TOKEN"),
    ]
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    profile = saved["profiles"]["default"]
    assert profile["auth_header"] == "Bearer NEW_TOKEN"
    assert profile["refresh_token"] == "NEW_REFRESH"


def _settings(config_path: Path | None = None) -> Settings:
    return Settings(
        base_url="https://app.ourskylight.com",
        auth_header="Bearer TOKEN",
        frame_id="FRAME",
        refresh_token="REFRESH",
        device_fingerprint="device-1",
        timeout=30.0,
        api_version="2026-03-01",
        profile="default",
        config_path=config_path or Path("/tmp/skylightctl-test.json"),
    )
