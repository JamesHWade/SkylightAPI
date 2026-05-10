# Authentication Guide

> **Unofficial reference** - Use only with accounts you own or are authorized to use. Never commit real tokens.

## Current Flow: Headless OAuth

The legacy `POST /api/sessions` endpoint now returns an unsupported-version error
in live testing and is no longer documented here as a working path.

Current public client evidence points to Skylight's OAuth flow:

1. `GET https://app.ourskylight.com/auth/session/new`
2. Extract the Rails `authenticity_token` from the login form.
3. `POST https://app.ourskylight.com/auth/session` with `email`, `password`, and `authenticity_token`.
4. `GET https://app.ourskylight.com/oauth/authorize` with:
   - `client_id=skylight-mobile`
   - `response_type=code`
   - `redirect_uri=https://ourskylight.com/welcome`
   - `scope=everything`
   - `skylight_api_client_device_fingerprint=<stable UUID>`
5. Extract `code` from the redirect location.
6. `POST https://app.ourskylight.com/oauth/token` with the authorization code.
7. Use the returned access token as:

```http
Authorization: Bearer <access_token>
skylight-api-version: 2026-03-01
```

`skylightctl auth login` implements this flow. Use a stable device fingerprint
and persist the returned refresh token; refresh tokens rotate when used.

```bash
cd cli
uv run skylightctl auth login --save
```

If `SKYLIGHT_EMAIL` and `SKYLIGHT_PASSWORD` are not set and flags are not passed,
the command prompts interactively. Password entry is hidden. Use `--no-input` in
CI or agent runs when missing credentials should fail immediately.

`--save` stores the Bearer token, refresh token, and device fingerprint in the
selected `skylightctl` config profile with file mode `0600`. It does not print
the token values. Use `--show-secret` only when you need shell exports.

After `--save`, later commands read the saved profile automatically. If you do
not use `--save`, pass `--show-secret` and set the emitted
`SKYLIGHT_AUTH_HEADER` and `SKYLIGHT_REFRESH_TOKEN` values yourself.

## Refreshing Tokens

```bash
export SKYLIGHT_DEVICE_FINGERPRINT="same-uuid-used-for-login"
export SKYLIGHT_REFRESH_TOKEN="..."

cd cli
uv run skylightctl auth refresh --save
```

Persist the new refresh token returned by the refresh command.

Normal authenticated CLI requests also refresh automatically after a `401`
response when a saved refresh token and device fingerprint are available. The
request is retried once and the rotated refresh token is persisted.

## Capturing Tokens via Proxy

If OAuth login fails locally, capture the official app's current traffic:

1. Install and trust a proxy root certificate with Proxyman, Charles, or mitmproxy.
2. Enable SSL proxying for `app.ourskylight.com`.
3. Log into the Skylight app.
4. Capture an authenticated API request.
5. Copy the `Authorization` header and any app/client version headers.

## Electron/Chromium Apps

If the desktop app is Electron/Chromium-based:

```bash
open -na "/Applications/Skylight.app" --args --remote-debugging-port=9222
```

Then inspect the target from Chrome at `chrome://inspect` and copy request
headers from the Network tab.

## Redaction & Sharing

- Replace tokens, refresh tokens, cookies, emails, and people-linked IDs with `REDACTED`.
- Keep response structure intact when adding examples.
- Use stable placeholders for related IDs if structure matters.

See also: `../SECURITY.md` and `../CONTRIBUTING.md`.
