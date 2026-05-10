from __future__ import annotations

import json
from typing import Any

import pytest
from typer.testing import CliRunner

from skylight_cli import main
from skylight_cli.oauth import OAuthToken

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolate_cli_config(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("SKYLIGHT_CONFIG", str(tmp_path / "config.json"))
    for name in [
        "SKYLIGHT_AUTH_HEADER",
        "SKYLIGHT_BASE_URL",
        "SKYLIGHT_DEVICE_FINGERPRINT",
        "SKYLIGHT_EMAIL",
        "SKYLIGHT_FRAME_ID",
        "SKYLIGHT_PASSWORD",
        "SKYLIGHT_PROFILE",
        "SKYLIGHT_REFRESH_TOKEN",
    ]:
        monkeypatch.delenv(name, raising=False)


def test_capabilities_outputs_json() -> None:
    result = runner.invoke(main.app, ["capabilities"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["defaults"]["json"] is True
    assert {"name": "chores list", "method": "GET", "operationId": "listChores"} in payload[
        "commands"
    ]
    assert {"name": "auth login", "method": "OAuth", "operationId": None} in payload[
        "commands"
    ]


def test_auth_login_redacts_secret_by_default(monkeypatch: Any) -> None:
    def fake_login_headless(**kwargs: Any) -> OAuthToken:
        assert kwargs["email"] == "person@example.com"
        assert kwargs["password"] == "secret"
        assert kwargs["fingerprint"] == "device-1"
        return OAuthToken(
            access_token="ACCESS",
            refresh_token="REFRESH",
            expires_in=3600,
            token_type="Bearer",
        )

    monkeypatch.setattr(main, "login_headless", fake_login_headless)
    result = runner.invoke(
        main.app,
        [
            "auth",
            "login",
            "--email",
            "person@example.com",
            "--password",
            "secret",
            "--fingerprint",
            "device-1",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["authorization_header_redacted"] == "Bearer REDACTED"
    assert "authorization_header" not in payload
    assert "access_token" not in payload
    assert payload["refresh_token_redacted"] == "REDACTED"


def test_auth_login_can_show_secret(monkeypatch: Any) -> None:
    def fake_login_headless(**_kwargs: Any) -> OAuthToken:
        return OAuthToken(
            access_token="ACCESS",
            refresh_token="REFRESH",
            expires_in=3600,
            token_type="Bearer",
        )

    monkeypatch.setattr(main, "login_headless", fake_login_headless)
    result = runner.invoke(
        main.app,
        [
            "auth",
            "login",
            "--email",
            "person@example.com",
            "--password",
            "secret",
            "--fingerprint",
            "device-1",
            "--show-secret",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["authorization_header"] == "Bearer ACCESS"
    assert payload["refresh_token"] == "REFRESH"


def test_auth_login_can_save_tokens(monkeypatch: Any, tmp_path) -> None:
    def fake_login_headless(**_kwargs: Any) -> OAuthToken:
        return OAuthToken(
            access_token="ACCESS",
            refresh_token="REFRESH",
            expires_in=3600,
            token_type="Bearer",
        )

    config_path = tmp_path / "config.json"
    monkeypatch.setenv("SKYLIGHT_CONFIG", str(config_path))
    monkeypatch.setattr(main, "login_headless", fake_login_headless)
    result = runner.invoke(
        main.app,
        [
            "auth",
            "login",
            "--email",
            "person@example.com",
            "--password",
            "secret",
            "--fingerprint",
            "device-1",
            "--save",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["saved"] is True
    assert "authorization_header" not in payload
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    profile = saved["profiles"]["default"]
    assert profile["auth_header"] == "Bearer ACCESS"
    assert profile["refresh_token"] == "REFRESH"
    assert profile["device_fingerprint"] == "device-1"


def test_auth_login_prompts_for_missing_credentials(monkeypatch: Any) -> None:
    def fake_login_headless(**kwargs: Any) -> OAuthToken:
        assert kwargs["email"] == "person@example.com"
        assert kwargs["password"] == "secret"
        return OAuthToken(
            access_token="ACCESS",
            refresh_token="REFRESH",
            expires_in=3600,
            token_type="Bearer",
    )

    monkeypatch.setattr(main, "login_headless", fake_login_headless)
    result = runner.invoke(
        main.app,
        ["auth", "login", "--fingerprint", "device-1"],
        input="person@example.com\nsecret\n",
    )

    assert result.exit_code == 0
    payload = json.loads(result.output[result.output.index("{") :])
    assert payload["authorization_header_redacted"] == "Bearer REDACTED"


def test_auth_login_no_input_fails_fast() -> None:
    result = runner.invoke(
        main.app,
        ["auth", "login", "--fingerprint", "device-1", "--no-input"],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stderr)
    assert payload["error"]["kind"] == "config_error"
    assert "Missing email" in payload["error"]["message"]


def test_auth_refresh_can_show_secret(monkeypatch: Any) -> None:
    def fake_refresh_oauth_token(**kwargs: Any) -> OAuthToken:
        assert kwargs["refresh_token"] == "OLD_REFRESH"
        assert kwargs["fingerprint"] == "device-1"
        return OAuthToken(
            access_token="NEW_ACCESS",
            refresh_token="NEW_REFRESH",
            expires_in=3600,
            token_type="Bearer",
        )

    monkeypatch.setattr(main, "refresh_oauth_token", fake_refresh_oauth_token)
    result = runner.invoke(
        main.app,
        [
            "auth",
            "refresh",
            "--refresh-token",
            "OLD_REFRESH",
            "--fingerprint",
            "device-1",
            "--show-secret",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["authorization_header"] == "Bearer NEW_ACCESS"
    assert payload["refresh_token"] == "NEW_REFRESH"


def test_auth_refresh_uses_saved_refresh_token(monkeypatch: Any, tmp_path) -> None:
    def fake_refresh_oauth_token(**kwargs: Any) -> OAuthToken:
        assert kwargs["refresh_token"] == "OLD_REFRESH"
        assert kwargs["fingerprint"] == "device-1"
        return OAuthToken(
            access_token="NEW_ACCESS",
            refresh_token="NEW_REFRESH",
            expires_in=3600,
            token_type="Bearer",
        )

    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "profiles": {
                    "default": {
                        "refresh_token": "OLD_REFRESH",
                        "device_fingerprint": "device-1",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SKYLIGHT_CONFIG", str(config_path))
    monkeypatch.setattr(main, "refresh_oauth_token", fake_refresh_oauth_token)
    result = runner.invoke(main.app, ["auth", "refresh", "--save"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["saved"] is True
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["profiles"]["default"]["auth_header"] == "Bearer NEW_ACCESS"
    assert saved["profiles"]["default"]["refresh_token"] == "NEW_REFRESH"


def test_doctor_reports_missing_setup() -> None:
    result = runner.invoke(main.app, ["doctor", "--no-live"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "needs_setup"
    assert "run `skylightctl auth login --save`" in payload["next_steps"]


def test_frames_use_first_saves_frame(monkeypatch: Any, tmp_path) -> None:
    class FakeClient:
        def __init__(self, settings: Any) -> None:
            self.settings = settings

        def request(
            self,
            _method: str,
            path: str,
            *,
            params: dict[str, object] | None = None,
            json_body: Any | None = None,
        ) -> dict[str, Any]:
            if path == "/api/frames":
                return {"data": [{"id": "FRAME1"}]}
            return {"data": {"id": "FRAME1"}}

    config_path = tmp_path / "config.json"
    monkeypatch.setenv("SKYLIGHT_CONFIG", str(config_path))
    monkeypatch.setattr(main, "SkylightClient", FakeClient)
    result = runner.invoke(
        main.app,
        ["--auth-header", "Bearer TOKEN", "frames", "use", "--first"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["frame_id"] == "FRAME1"
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["profiles"]["default"]["frame_id"] == "FRAME1"


def test_chore_create_dry_run_redacts_auth_header() -> None:
    result = runner.invoke(
        main.app,
        [
            "--auth-header",
            "Basic SECRET",
            "chores",
            "create",
            "--frame-id",
            "FRAME",
            "--summary",
            "Take out trash",
            "--start",
            "2026-05-10",
            "--category-id",
            "CATEGORY",
        ],
    )

    assert result.exit_code == 0
    assert "SECRET" not in result.output
    payload = json.loads(result.output)
    assert payload["dry_run"] is True
    assert payload["request"]["headers"]["Authorization"] == "Basic REDACTED"
    assert payload["request"]["url"] == "https://app.ourskylight.com/api/frames/FRAME/chores"
    assert payload["request"]["body"]["summary"] == "Take out trash"
    assert payload["request"]["body"]["start"] == "2026-05-10"
    assert payload["request"]["body"]["category_id"] == "CATEGORY"


def test_chore_update_dry_run_uses_current_put_shape() -> None:
    result = runner.invoke(
        main.app,
        [
            "chores",
            "update",
            "--frame-id",
            "FRAME",
            "--chore-id",
            "CHORE",
            "--summary",
            "Updated",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["dry_run"] is True
    assert payload["request"]["method"] == "PUT"
    assert payload["request"]["url"] == "https://app.ourskylight.com/api/frames/FRAME/chores/CHORE"
    assert payload["request"]["body"] == {"summary": "Updated"}


def test_chore_complete_dry_run_infers_instance_date() -> None:
    result = runner.invoke(
        main.app,
        [
            "chores",
            "complete",
            "--frame-id",
            "FRAME",
            "--chore-id",
            "18731133-2026-04-28-0600",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["request"]["method"] == "PUT"
    assert (
        payload["request"]["url"]
        == "https://app.ourskylight.com/api/frames/FRAME/chores/18731133/completions"
    )
    assert payload["request"]["body"] == {
        "status": "complete",
        "instance_date": "2026-04-28",
    }


def test_task_box_create_dry_run_does_not_require_auth() -> None:
    result = runner.invoke(
        main.app,
        [
            "task-box",
            "create",
            "--frame-id",
            "FRAME",
            "--summary",
            "Pack lunch",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["dry_run"] is True
    assert "Authorization" not in payload["request"]["headers"]


def test_raw_delete_dry_run() -> None:
    result = runner.invoke(
        main.app,
        ["raw", "delete", "/api/frames/FRAME/chores/CHORE"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["dry_run"] is True
    assert payload["request"]["method"] == "DELETE"


def test_smoke_read_uses_first_frame(monkeypatch: Any) -> None:
    class FakeClient:
        def __init__(self, settings: Any) -> None:
            self.settings = settings

        def request(
            self,
            _method: str,
            path: str,
            *,
            params: dict[str, object] | None = None,
            json_body: Any | None = None,
        ) -> dict[str, Any]:
            if path == "/api/frames":
                return {"data": [{"id": "FRAME1"}]}
            return {"data": []}

    monkeypatch.setattr(main, "SkylightClient", FakeClient)
    result = runner.invoke(main.app, ["--auth-header", "Bearer TOKEN", "smoke", "read"])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "ok"
    assert payload["frame_id"] == "FRAME1"


def test_list_chores_builds_expected_request(monkeypatch: Any) -> None:
    calls: list[dict[str, Any]] = []

    class FakeClient:
        def __init__(self, settings: Any) -> None:
            self.settings = settings

        def request(
            self,
            method: str,
            path: str,
            *,
            params: dict[str, object] | None = None,
            json_body: Any | None = None,
        ) -> dict[str, Any]:
            calls.append(
                {
                    "method": method,
                    "path": path,
                    "params": params,
                    "json_body": json_body,
                    "auth_header": self.settings.auth_header,
                }
            )
            return {"ok": True}

    monkeypatch.setattr(main, "SkylightClient", FakeClient)

    result = runner.invoke(
        main.app,
        [
            "--auth-header",
            "Bearer TOKEN",
            "chores",
            "list",
            "--frame-id",
            "FRAME",
            "--after",
            "2026-05-01",
            "--before",
            "2026-05-09",
            "--include-late",
            "--filter",
            "linked_to_profile",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.output) == {"ok": True}
    assert calls == [
        {
            "method": "GET",
            "path": "/api/frames/FRAME/chores",
            "params": {
                "after": "2026-05-01",
                "before": "2026-05-09",
                "include_late": True,
                "filter": "linked_to_profile",
            },
            "json_body": None,
            "auth_header": "Bearer TOKEN",
        }
    ]


def test_raw_get_rejects_bad_query() -> None:
    result = runner.invoke(
        main.app,
        [
            "--auth-header",
            "Basic SECRET",
            "raw",
            "get",
            "/api/frames/FRAME/categories",
            "--query",
            "bad-query",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stderr)
    assert payload["error"]["kind"] == "usage_error"
