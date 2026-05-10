from __future__ import annotations

from dataclasses import replace
from typing import Any

import httpx

from skylight_cli.config import Settings, redacted_auth_header, save_profile
from skylight_cli.errors import ApiError, ConfigError
from skylight_cli.oauth import refresh_oauth_token

QueryParams = dict[str, str]


class SkylightClient:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
        auto_refresh: bool = True,
    ) -> None:
        self._settings = settings
        self._transport = transport
        self._auto_refresh = auto_refresh

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, object] | None = None,
        json_body: Any | None = None,
    ) -> Any:
        normalized_params = clean_params(params)
        request_path = normalize_path(path)

        response = self._send(method, request_path, params=normalized_params, json_body=json_body)

        if response.status_code == 401 and self._auto_refresh and self._refresh_credentials():
            response = self._send(
                method,
                request_path,
                params=normalized_params,
                json_body=json_body,
            )

        if response.status_code == 304:
            return {"status": 304, "not_modified": True}

        body = decode_response(response)
        if not response.is_success:
            raise ApiError(
                status_code=response.status_code,
                method=method.upper(),
                path=request_path,
                body=body,
            )

        return body

    def preview_request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, object] | None = None,
        json_body: Any | None = None,
    ) -> dict[str, Any]:
        request_path = normalize_path(path)
        normalized_params = clean_params(params)
        url = build_url(self._settings.base_url, request_path)

        if normalized_params:
            url = str(httpx.URL(url, params=normalized_params))

        request: dict[str, Any] = {
            "method": method.upper(),
            "url": url,
            "headers": self._headers(redact=True),
        }
        if normalized_params:
            request["params"] = normalized_params
        if json_body is not None:
            request["body"] = json_body
        return request

    def _headers(self, *, redact: bool) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "skylight-api-version": self._settings.api_version,
        }
        if self._settings.auth_header:
            auth_header = (
                redacted_auth_header(self._settings.auth_header)
                if redact
                else self._settings.auth_header
            )
            if auth_header:
                headers["Authorization"] = auth_header
        return headers

    def _send(
        self,
        method: str,
        path: str,
        *,
        params: QueryParams,
        json_body: Any | None,
    ) -> httpx.Response:
        with httpx.Client(
            base_url=self._settings.base_url,
            timeout=self._settings.timeout,
            transport=self._transport,
            headers=self._headers(redact=False),
        ) as client:
            return client.request(
                method,
                path,
                params=params,
                json=json_body,
            )

    def _refresh_credentials(self) -> bool:
        if not self._settings.refresh_token or not self._settings.device_fingerprint:
            return False

        try:
            token = refresh_oauth_token(
                base_url=self._settings.base_url,
                refresh_token=self._settings.refresh_token,
                fingerprint=self._settings.device_fingerprint,
                timeout=self._settings.timeout,
                transport=self._transport,
            )
        except (ConfigError, httpx.HTTPError):
            return False

        refresh_token = token.refresh_token or self._settings.refresh_token
        self._settings = replace(
            self._settings,
            auth_header=token.authorization_header,
            refresh_token=refresh_token,
        )
        try:
            save_profile(
                config_path=self._settings.config_path,
                profile=self._settings.profile,
                values={
                    "auth_header": token.authorization_header,
                    "refresh_token": refresh_token,
                    "device_fingerprint": self._settings.device_fingerprint,
                    "base_url": self._settings.base_url,
                    "api_version": self._settings.api_version,
                    "frame_id": self._settings.frame_id,
                },
            )
        except ConfigError:
            return False

        return True


def clean_params(params: dict[str, object] | None) -> QueryParams:
    if not params:
        return {}

    cleaned: QueryParams = {}
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, bool):
            cleaned[key] = str(value).lower()
        else:
            cleaned[key] = str(value)
    return cleaned


def normalize_path(path: str) -> str:
    if not path:
        return "/"
    return "/" + path.lstrip("/")


def build_url(base_url: str, path: str) -> str:
    return base_url.rstrip("/") + normalize_path(path)


def decode_response(response: httpx.Response) -> Any:
    if not response.content:
        return None

    content_type = response.headers.get("content-type", "")
    if "json" in content_type:
        return response.json()

    try:
        return response.json()
    except ValueError:
        return response.text
