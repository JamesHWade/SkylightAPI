from __future__ import annotations

import json
import stat
import sys

import pytest

from skylight_cli.config import load_config, public_settings, resolve_settings, save_profile
from skylight_cli.errors import ConfigError


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


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX file modes")
def test_save_profile_locks_down_created_parent(tmp_path) -> None:
    config_path = tmp_path / "skylightctl" / "config.json"
    save_profile(config_path=config_path, profile="default", values={"frame_id": "FRAME"})

    parent_mode = stat.S_IMODE(config_path.parent.stat().st_mode)
    file_mode = stat.S_IMODE(config_path.stat().st_mode)
    assert parent_mode == 0o700
    assert file_mode == 0o600


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX file modes")
def test_save_profile_does_not_chmod_existing_parent(tmp_path) -> None:
    # Simulates SKYLIGHT_CONFIG=~/skylight.json: parent already exists and we
    # must not narrow its permissions.
    tmp_path.chmod(0o755)
    config_path = tmp_path / "config.json"
    save_profile(config_path=config_path, profile="default", values={"frame_id": "FRAME"})

    parent_mode = stat.S_IMODE(config_path.parent.stat().st_mode)
    file_mode = stat.S_IMODE(config_path.stat().st_mode)
    assert parent_mode == 0o755, "must not narrow permissions of a pre-existing dir"
    assert file_mode == 0o600


def test_load_config_wraps_io_errors(tmp_path) -> None:
    with pytest.raises(ConfigError, match="Cannot read config"):
        load_config(tmp_path)


def test_save_profile_wraps_io_errors(tmp_path) -> None:
    blocked = tmp_path / "blocked"
    blocked.mkdir()

    with pytest.raises(ConfigError, match="Cannot read config"):
        save_profile(config_path=blocked, profile="default", values={"frame_id": "FRAME"})

    file_parent = tmp_path / "file-parent"
    file_parent.write_text("not a directory", encoding="utf-8")

    with pytest.raises(ConfigError, match="Cannot write config"):
        save_profile(
            config_path=file_parent / "config.json",
            profile="default",
            values={"frame_id": "FRAME"},
        )
