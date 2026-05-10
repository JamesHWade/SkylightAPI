"""Headless OAuth login + refresh against Skylight's Rails-style auth flow.

Implements the same dance documented in `docs/auth.md`:

  1. GET  /auth/session/new      -> scrape Rails CSRF authenticity_token
  2. POST /auth/session          -> form login (302 on success, 200 on bad creds)
  3. GET  /oauth/authorize       -> 302 with code in redirect query
  4. POST /oauth/token           -> exchange code or refresh_token for bearer

This is not a browser flow. It impersonates a browser only at the HTTP layer
(User-Agent + Accept) so the Rails endpoints behave the same as for the mobile
client.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from skylight_cli.errors import ConfigError

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
BROWSER_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
CLIENT_ID = "skylight-mobile"
SCOPE = "everything"
REDIRECT_URI = "https://ourskylight.com/welcome"


@dataclass(frozen=True)
class OAuthToken:
    access_token: str
    refresh_token: str | None
    expires_in: int | None
    token_type: str | None
    issued_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def authorization_header(self) -> str:
        return f"Bearer {self.access_token}"

    @property
    def expires_at(self) -> datetime | None:
        if self.expires_in is None:
            return None
        return self.issued_at + timedelta(seconds=self.expires_in)

    def is_expired(
        self,
        *,
        now: datetime | None = None,
        leeway: timedelta = timedelta(seconds=30),
    ) -> bool:
        expires_at = self.expires_at
        if expires_at is None:
            return False
        current = now or datetime.now(UTC)
        return current + leeway >= expires_at


def login_headless(
    *,
    base_url: str,
    email: str,
    password: str,
    fingerprint: str,
    timeout: float,
    transport: httpx.BaseTransport | None = None,
) -> OAuthToken:
    root = base_url.rstrip("/")
    with httpx.Client(
        timeout=timeout,
        follow_redirects=False,
        transport=transport,
        headers={"User-Agent": BROWSER_USER_AGENT, "Accept": BROWSER_ACCEPT},
    ) as client:
        csrf = fetch_csrf_token(client, root)
        post_session(client, root, email, password, csrf)
        code = fetch_auth_code(client, root, fingerprint)
        return exchange_auth_code(client, root, code, fingerprint)


def refresh_oauth_token(
    *,
    base_url: str,
    refresh_token: str,
    fingerprint: str,
    timeout: float,
    transport: httpx.BaseTransport | None = None,
) -> OAuthToken:
    with httpx.Client(timeout=timeout, transport=transport) as client:
        return post_oauth_token(
            client,
            base_url.rstrip("/"),
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": CLIENT_ID,
                "skylight_api_client_device_fingerprint": fingerprint,
            },
        )


def fetch_csrf_token(client: httpx.Client, root: str) -> str:
    response = client.get(f"{root}/auth/session/new")
    if response.status_code != 200:
        raise ConfigError(_status_error("fetching login page", response))

    parser = CSRFParser()
    parser.feed(response.text)
    token = parser.input_token or parser.meta_token
    if not token:
        raise ConfigError("authenticity_token not found in login page")
    return token


def post_session(
    client: httpx.Client,
    root: str,
    email: str,
    password: str,
    csrf_token: str,
) -> None:
    response = client.post(
        f"{root}/auth/session",
        data={"authenticity_token": csrf_token, "email": email, "password": password},
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": root,
            "Referer": f"{root}/auth/session/new",
        },
    )
    # Rails returns 302 on successful login; 200 means the form was re-rendered
    # with errors (typically bad credentials).
    if response.status_code == 200:
        raise ConfigError(
            "login was rejected; the server re-rendered the login form. "
            "Credentials are likely invalid."
        )
    if response.status_code != 302:
        raise ConfigError(_status_error("posting login form", response))


def fetch_auth_code(client: httpx.Client, root: str, fingerprint: str) -> str:
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
        "skylight_api_client_device_fingerprint": fingerprint,
    }
    response = client.get(f"{root}/oauth/authorize?{urlencode(params)}")
    location = response.headers.get("location")
    if not location:
        raise ConfigError(_status_error("fetching OAuth authorization code", response))

    query = parse_qs(urlparse(location).query)
    code_values = query.get("code", [])
    if not code_values or not code_values[0]:
        if "/auth/session" in location:
            raise ConfigError(
                "login did not complete; credentials may be invalid or additional account "
                "verification may be required"
            )
        raise ConfigError(f"no OAuth code in redirect location: {location}")
    return code_values[0]


def exchange_auth_code(
    client: httpx.Client,
    root: str,
    code: str,
    fingerprint: str,
) -> OAuthToken:
    return post_oauth_token(
        client,
        root,
        {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPE,
            "skylight_api_client_device_fingerprint": fingerprint,
        },
    )


def post_oauth_token(client: httpx.Client, root: str, data: dict[str, str]) -> OAuthToken:
    response = client.post(f"{root}/oauth/token", data=data)
    if response.status_code != 200:
        raise ConfigError(_status_error("exchanging OAuth token", response))

    try:
        payload = response.json()
    except ValueError as exc:
        raise ConfigError(
            f"OAuth token response was not valid JSON: {_response_preview(response)}"
        ) from exc
    if not isinstance(payload, dict):
        raise ConfigError("OAuth token response was not a JSON object")

    access_token = payload.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise ConfigError("OAuth token response did not include access_token")

    return OAuthToken(
        access_token=access_token,
        refresh_token=_optional_str(payload.get("refresh_token"), "refresh_token"),
        expires_in=_optional_int(payload.get("expires_in"), "expires_in"),
        token_type=_optional_str(payload.get("token_type"), "token_type"),
    )


def _optional_str(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value or None
    raise ConfigError(
        f"OAuth response field '{field_name}' must be a string, got {type(value).__name__}"
    )


def _optional_int(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ConfigError(f"OAuth response field '{field_name}' must be a number, got bool")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError as exc:
            raise ConfigError(
                f"OAuth response field '{field_name}' is not a valid integer: {value!r}"
            ) from exc
    raise ConfigError(
        f"OAuth response field '{field_name}' has unexpected type {type(value).__name__}"
    )


class CSRFParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.input_token: str | None = None
        self.meta_token: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key: value for key, value in attrs}
        if tag == "input" and attr.get("name") == "authenticity_token":
            self.input_token = attr.get("value")
        if tag == "meta" and attr.get("name") == "csrf-token":
            self.meta_token = attr.get("content")


def _status_error(action: str, response: httpx.Response) -> str:
    return f"{action} failed with HTTP {response.status_code}: {_response_preview(response)}"


def _response_preview(response: httpx.Response) -> str:
    try:
        payload: Any = response.json()
    except ValueError:
        payload = response.text
    return str(payload)[:500]
