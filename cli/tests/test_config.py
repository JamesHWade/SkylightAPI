from __future__ import annotations

import json

from skylight_cli.config import public_settings, resolve_settings


def test_resolve_settings_uses_cli_env_profile_precedence(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "default_profile": "home",
                "profiles": {
                    "home": {
                        "base_url": "https://profile.example",
                        "auth_header": "Basic PROFILE",
                        "frame_id": "PROFILE_FRAME",
                        "timeout": 10,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SKYLIGHT_AUTH_HEADER", "Bearer ENV")
    monkeypatch.setenv("SKYLIGHT_FRAME_ID", "ENV_FRAME")

    settings = resolve_settings(
        base_url="https://cli.example",
        auth_header=None,
        frame_id="CLI_FRAME",
        config_path=config_path,
    )

    assert settings.base_url == "https://cli.example"
    assert settings.auth_header == "Bearer ENV"
    assert settings.frame_id == "CLI_FRAME"
    assert settings.timeout == 10
    assert settings.profile == "home"


def test_public_settings_redacts_auth_header(tmp_path) -> None:
    settings = resolve_settings(
        auth_header="Basic SECRET",
        frame_id="FRAME",
        config_path=tmp_path / "missing.json",
    )

    assert public_settings(settings)["auth_header"] == "Basic REDACTED"
