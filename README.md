# Unofficial Skylight API

Community-maintained notes, OpenAPI metadata, and an experimental
agent-friendly CLI for the Skylight API observed at:

```text
https://app.ourskylight.com
```

This project is unofficial and not affiliated with Skylight. Use it only with
accounts and devices you own or are authorized to manage.

## What Is Here

- `docs/openapi/openapi.yaml` - living OpenAPI reference for observed routes.
- `docs/auth.md` - OAuth login and token refresh notes.
- `examples/` - redacted request and response captures.
- `cli/` - `skylightctl`, a JSON-first CLI intended for agents and scripts.

## CLI Quickstart

Run from a checkout:

```bash
cd cli
uv sync --extra dev
uv run skylightctl --help
```

Or install the CLI as a local user tool:

```bash
uv tool install /path/to/SkylightAPI/cli
skylightctl --help
```

Authenticate without storing the password in an environment variable:

```bash
skylightctl auth login --save
```

The login command prompts for email and a hidden password, then saves the Bearer
token, refresh token, and device fingerprint in:

```text
~/.config/skylightctl/config.json
```

The config file is written with `0600` permissions. Secrets are redacted from
normal output; use `--show-secret` only when you explicitly need shell exports.

Save the default frame after login:

```bash
skylightctl frames use --first
```

Check whether the CLI is ready:

```bash
skylightctl doctor
skylightctl smoke read
```

`smoke read` only performs read-only requests and reports status, response
shape, and item counts. It does not print full account data.

## Common Commands

```bash
skylightctl capabilities
skylightctl config show
skylightctl frames list
skylightctl chores list --after 2026-05-01 --before 2026-05-10
skylightctl categories list
skylightctl lists list
skylightctl calendars events --date-min 2026-05-10 --date-max 2026-05-17
skylightctl rewards points
```

Most commands return JSON. Use `--compact` for single-line JSON.

## Safe Writes

Mutation commands dry-run by default and print the redacted request that would
be sent. Add `--execute` only after inspecting the request.

```bash
skylightctl chores create --summary "Take out trash" --start 2026-05-10
skylightctl chores update --chore-id CHORE_ID --summary "Updated title"
skylightctl chores complete --chore-id CHORE_ID
skylightctl chores skip --chore-id CHORE_ID
skylightctl chores delete --chore-id CHORE_ID
```

Raw escape hatches are available for endpoints that are not promoted to first
class commands yet:

```bash
skylightctl raw get /api/frames/FRAME_ID/categories
skylightctl raw post /api/frames/FRAME_ID/chores --body '{"summary":"Test"}'
skylightctl raw put /api/frames/FRAME_ID/chores/CHORE_ID --body '{"summary":"Test"}'
skylightctl raw patch /api/frames/FRAME_ID/rewards/REWARD_ID --body '{"name":"Test"}'
skylightctl raw delete /api/frames/FRAME_ID/chores/CHORE_ID
```

## Authentication Model

Current public client evidence and live testing point to OAuth Bearer tokens:

```http
Authorization: Bearer <access_token>
skylight-api-version: 2026-03-01
```

The older `POST /api/sessions` path from an upstream PR currently returns an
unsupported-version error, so `skylightctl` intentionally does not use it. The
CLI refreshes saved OAuth credentials automatically after an authenticated
request receives `401`, then retries once and persists the rotated refresh
token.

## Agent Notes

Agents should start with:

```bash
skylightctl capabilities
skylightctl doctor
skylightctl smoke read
```

Then prefer first-class commands over `raw`. For writes, agents should present
the dry-run request unless they have explicit permission to pass `--execute`.

## Development

```bash
cd cli
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run ty check
```

Validate the OpenAPI file:

```bash
npx --yes @openapitools/openapi-generator-cli validate -i docs/openapi/openapi.yaml
```

## Repository Workflow

- Respect Skylight's terms and privacy laws.
- Capture only your own account/device traffic.
- Redact tokens, emails, frame IDs, names, and personal data before committing.
- Document observed route changes in `docs/openapi/openapi.yaml`.
- Keep examples under `examples/` redacted.

## Roadmap

- Promote more current routes from live smoke checks and maintained clients.
- Add guarded commands for list items, rewards, and calendar writes.
- Add schema assertions to `smoke read` as endpoint shapes stabilize.
- Capture pagination, rate limits, and error shapes.
