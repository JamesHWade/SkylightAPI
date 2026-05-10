from __future__ import annotations

import json
import os
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from skylight_cli.errors import ConfigError

DEFAULT_BASE_URL = "https://app.ourskylight.com"
DEFAULT_PROFILE = "default"
DEFAULT_TIMEOUT = 30.0
DEFAULT_API_VERSION = "2026-03-01"

API_VERSION_ENV = "SKYLIGHT_API_VERSION"
AUTH_HEADER_ENV = "SKYLIGHT_AUTH_HEADER"
BASE_URL_ENV = "SKYLIGHT_BASE_URL"
CONFIG_ENV = "SKYLIGHT_CONFIG"
DEVICE_FINGERPRINT_ENV = "SKYLIGHT_DEVICE_FINGERPRINT"
FRAME_ID_ENV = "SKYLIGHT_FRAME_ID"
PROFILE_ENV = "SKYLIGHT_PROFILE"
REFRESH_TOKEN_ENV = "SKYLIGHT_REFRESH_TOKEN"
TIMEOUT_ENV = "SKYLIGHT_TIMEOUT"


@dataclass(frozen=True)
class Settings:
    base_url: str
    auth_header: str | None
    frame_id: str | None
    refresh_token: str | None
    device_fingerprint: str | None
    timeout: float
    api_version: str
    profile: str
    config_path: Path


def default_config_path() -> Path:
    configured = os.getenv(CONFIG_ENV)
    if configured:
        return Path(configured).expanduser()

    config_home = os.getenv("XDG_CONFIG_HOME")
    if config_home:
        return Path(config_home).expanduser() / "skylightctl" / "config.json"

    return Path.home() / ".config" / "skylightctl" / "config.json"


def load_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or default_config_path()
    if not config_path.exists():
        return {}

    try:
        raw = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Cannot read config at {config_path}: {exc}") from exc

    try:
        data = json.loads(raw)
    except JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON config at {config_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError(f"Config at {config_path} must be a JSON object")

    return data


def resolve_settings(
    *,
    profile: str | None = None,
    base_url: str | None = None,
    auth_header: str | None = None,
    frame_id: str | None = None,
    timeout: float | None = None,
    config_path: Path | None = None,
) -> Settings:
    resolved_config_path = config_path or default_config_path()
    config = load_config(resolved_config_path)
    profile_name = profile or os.getenv(PROFILE_ENV) or _string_value(config, "default_profile")
    if not profile_name:
        profile_name = DEFAULT_PROFILE

    profile_data = _profile_data(config, profile_name)

    timeout_value = _resolve_timeout(timeout, profile_data)

    return Settings(
        base_url=_first_string(base_url, os.getenv(BASE_URL_ENV), profile_data.get("base_url"))
        or DEFAULT_BASE_URL,
        auth_header=_first_string(
            auth_header,
            os.getenv(AUTH_HEADER_ENV),
            profile_data.get("auth_header"),
        ),
        frame_id=_first_string(frame_id, os.getenv(FRAME_ID_ENV), profile_data.get("frame_id")),
        refresh_token=_first_string(
            os.getenv(REFRESH_TOKEN_ENV),
            profile_data.get("refresh_token"),
        ),
        device_fingerprint=_first_string(
            os.getenv(DEVICE_FINGERPRINT_ENV),
            profile_data.get("device_fingerprint"),
        ),
        timeout=timeout_value,
        api_version=_first_string(os.getenv(API_VERSION_ENV), profile_data.get("api_version"))
        or DEFAULT_API_VERSION,
        profile=profile_name,
        config_path=resolved_config_path,
    )


def require_auth(settings: Settings) -> None:
    if not settings.auth_header:
        raise ConfigError(
            "Missing auth header. Set SKYLIGHT_AUTH_HEADER or pass --auth-header with "
            "the complete Authorization value, for example 'Bearer ...'."
        )


def require_frame_id(settings: Settings) -> str:
    if not settings.frame_id:
        raise ConfigError("Missing frame id. Set SKYLIGHT_FRAME_ID or pass --frame-id.")
    return settings.frame_id


def redacted_auth_header(auth_header: str | None) -> str | None:
    if not auth_header:
        return None

    scheme, _, _secret = auth_header.partition(" ")
    if scheme:
        return f"{scheme} REDACTED"

    return "REDACTED"


def public_settings(settings: Settings) -> dict[str, Any]:
    return {
        "profile": settings.profile,
        "config_path": str(settings.config_path),
        "base_url": settings.base_url,
        "frame_id": settings.frame_id,
        "auth_header": redacted_auth_header(settings.auth_header),
        "refresh_token": "REDACTED" if settings.refresh_token else None,
        "device_fingerprint": settings.device_fingerprint,
        "timeout": settings.timeout,
        "api_version": settings.api_version,
    }


def save_profile(
    *,
    config_path: Path,
    profile: str,
    values: dict[str, Any],
) -> None:
    config = load_config(config_path)
    profiles = config.get("profiles")
    if profiles is None:
        profiles = {}
        config["profiles"] = profiles
    if not isinstance(profiles, dict):
        raise ConfigError("Config key 'profiles' must be an object")

    existing = profiles.get(profile, {})
    if existing is None:
        existing = {}
    if not isinstance(existing, dict):
        raise ConfigError(f"Config profile '{profile}' must be an object")

    existing.update({key: value for key, value in values.items() if value is not None})
    profiles[profile] = existing
    config.setdefault("default_profile", profile)

    try:
        parent = config_path.parent
        parent_existed = parent.exists()
        parent.mkdir(parents=True, exist_ok=True)
        if not parent_existed:
            # Only lock down a directory we just created. The user may have pointed
            # SKYLIGHT_CONFIG at a shared dir like $HOME or ~/.config; chmod-ing
            # those would break unrelated tools.
            parent.chmod(0o700)
        config_path.write_text(
            json.dumps(config, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        config_path.chmod(0o600)
    except OSError as exc:
        raise ConfigError(f"Cannot write config at {config_path}: {exc}") from exc


def _profile_data(config: dict[str, Any], profile: str) -> dict[str, Any]:
    profiles = config.get("profiles", {})
    if profiles is None:
        return {}
    if not isinstance(profiles, dict):
        raise ConfigError("Config key 'profiles' must be an object")

    value = profiles.get(profile, {})
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"Config profile '{profile}' must be an object")
    return value


def _resolve_timeout(timeout: float | None, profile_data: dict[str, Any]) -> float:
    if timeout is not None:
        return timeout

    env_value = os.getenv(TIMEOUT_ENV)
    if env_value:
        return _parse_timeout(env_value, TIMEOUT_ENV)

    profile_value = profile_data.get("timeout")
    if profile_value is not None:
        return _parse_timeout(profile_value, "profile timeout")

    return DEFAULT_TIMEOUT


def _parse_timeout(value: object, source: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ConfigError(f"Invalid {source}: expected a number")

    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"Invalid {source}: expected a number") from exc

    if parsed <= 0:
        raise ConfigError(f"Invalid {source}: expected a positive number")

    return parsed


def _first_string(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return None


def _string_value(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if isinstance(value, str) and value:
        return value
    return None
