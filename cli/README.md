# Skylight CLI

`skylightctl` is a JSON-first CLI for the unofficial Skylight API reference. It
is built for agents and scripts: predictable command names, redacted previews,
and dry-run writes by default.

## Install

Development use from this repository:

```bash
cd cli
uv sync --extra dev
uv run skylightctl --help
```

User-level install from a checkout:

```bash
uv tool install /path/to/SkylightAPI/cli
skylightctl --help
```

## Setup

Interactive login prompts for email and a hidden password:

```bash
skylightctl auth login --save
```

`--save` writes the Bearer token, refresh token, and device fingerprint to
`~/.config/skylightctl/config.json` with `0600` permissions. Normal output
redacts secrets. Use `--show-secret` only when shell exports are needed.

Save a default frame:

```bash
skylightctl frames use --first
```

Check readiness:

```bash
skylightctl doctor
skylightctl smoke read
```

`smoke read` performs read-only requests and reports status, response shape, and
counts without dumping full account data.

## Configuration

Optional environment variables:

```bash
SKYLIGHT_BASE_URL=https://app.ourskylight.com
SKYLIGHT_CONFIG=~/.config/skylightctl/config.json
SKYLIGHT_DEVICE_FINGERPRINT=<stable UUID>
SKYLIGHT_REFRESH_TOKEN=<oauth refresh token>
SKYLIGHT_PROFILE=default
SKYLIGHT_TIMEOUT=30
SKYLIGHT_API_VERSION=2026-03-01
```

Config files are JSON:

```json
{
  "default_profile": "default",
  "profiles": {
    "default": {
      "auth_header": "Bearer REDACTED",
      "refresh_token": "REDACTED",
      "device_fingerprint": "REDACTED",
      "frame_id": "REDACTED",
      "base_url": "https://app.ourskylight.com",
      "api_version": "2026-03-01"
    }
  }
}
```

Precedence is CLI option, environment variable, profile config, built-in default.

## Agent Usage

Start here:

```bash
skylightctl capabilities
skylightctl doctor
skylightctl smoke read
```

Common reads:

```bash
skylightctl frames list
skylightctl chores list --after 2026-05-01 --before 2026-05-10
skylightctl categories list
skylightctl lists list
skylightctl lists get --list-id "$LIST_ID"
skylightctl calendars events --date-min 2026-05-10 --date-max 2026-05-17
skylightctl rewards points
```

Writes dry-run unless `--execute` is passed:

```bash
skylightctl chores create --summary "Take out trash" --start 2026-05-10
skylightctl chores update --chore-id "$CHORE_ID" --summary "Updated title"
skylightctl chores complete --chore-id "$CHORE_ID"
skylightctl chores skip --chore-id "$CHORE_ID"
skylightctl chores delete --chore-id "$CHORE_ID"
```

Raw escape hatches:

```bash
skylightctl raw get /api/frames/FRAME_ID/categories
skylightctl raw post /api/frames/FRAME_ID/chores --body '{"summary":"Test"}'
skylightctl raw put /api/frames/FRAME_ID/chores/CHORE_ID --body '{"summary":"Test"}'
skylightctl raw patch /api/frames/FRAME_ID/rewards/REWARD_ID --body '{"name":"Test"}'
skylightctl raw delete /api/frames/FRAME_ID/chores/CHORE_ID
```

The legacy `/api/sessions` flow is intentionally not implemented because it now
returns an unsupported-version error in live testing. Saved OAuth credentials are
refreshed automatically after a `401` response, retried once, and persisted.

## Validation

```bash
uv run pytest
uv run ruff check .
uv run ty check
```
