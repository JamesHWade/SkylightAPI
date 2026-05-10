# skylightctl cheat sheet

Reference for the agent loop. Every command emits JSON unless `--output human` is set. All mutations dry-run unless `--execute` is passed.

Keep this file in sync with `cli/src/skylight_cli/main.py`. The `capabilities` command (`skylightctl capabilities`) is the source of truth for the stable surface.

If the installed `skylightctl` is missing commands from this file, run from a
fresh checkout instead:

```bash
cd cli
uv run skylightctl capabilities
```

## Global flags

```
--profile <name>        # config profile (env: SKYLIGHT_PROFILE)
--base-url <url>        # override base URL (env: SKYLIGHT_BASE_URL)
--auth-header <value>   # full Authorization header (env: SKYLIGHT_AUTH_HEADER)
--frame-id <id>         # default frame (env: SKYLIGHT_FRAME_ID)
--timeout <seconds>     # HTTP timeout (env: SKYLIGHT_TIMEOUT)
--output {json,human}   # default json
--compact               # single-line JSON
--version               # print version and exit
```

## Setup

```bash
skylightctl auth login --save         # interactive email + hidden password; saves to ~/.config/skylightctl/config.json (0600)
skylightctl auth refresh              # rotate the saved refresh token
skylightctl frames use --first        # save the first frame as the default
skylightctl config show               # resolved config, secrets redacted
```

Use `--show-secret` only when the user explicitly needs to export tokens to a shell. Never paste that output into chat or commits.

## Inspection (run these first)

```bash
skylightctl capabilities              # stable command surface + version
skylightctl doctor                    # config + live read checks
skylightctl doctor --no-live          # skip the live API call
skylightctl smoke read                # read-only sanity sweep across resources
skylightctl discover routes           # probe known routes for 401-vs-404 drift
skylightctl discover routes --path /api/frames/{frameId}/something --probe-frame-id FRAME
```

If `doctor` returns any `false` check, fix it before continuing — most are resolved by `auth login --save`.

## Reads

```bash
skylightctl frames list
skylightctl frames get --frame-id "$FRAME_ID"

skylightctl chores list --after 2026-05-01 --before 2026-05-10

skylightctl categories list

skylightctl devices list

skylightctl lists list
skylightctl lists get --list-id "$LIST_ID"

skylightctl calendars sources
skylightctl calendars events --date-min 2026-05-10 --date-max 2026-05-17

skylightctl rewards list
skylightctl rewards points
```

## Writes (dry-run by default)

Each of these prints the redacted request that would be sent. Add `--execute` only after the user has reviewed the dry-run.

```bash
skylightctl chores create --summary "Take out trash" --start 2026-05-10
skylightctl chores update --chore-id "$CHORE_ID" --summary "Updated title"
skylightctl chores complete --chore-id "$CHORE_ID"
skylightctl chores skip --chore-id "$CHORE_ID"
skylightctl chores delete --chore-id "$CHORE_ID"

skylightctl task-box create --summary "Buy milk"
```

Recommended pattern for an agent:

```bash
skylightctl chores create --summary "Take out trash" --start 2026-05-10           # show dry-run to user
# (await confirmation)
skylightctl chores create --summary "Take out trash" --start 2026-05-10 --execute # then send
```

## Raw escape hatches

Use only for endpoints not yet promoted to first-class commands. Same `--execute` rule applies.

```bash
skylightctl raw get    /api/frames/FRAME_ID/categories
skylightctl raw post   /api/frames/FRAME_ID/chores            --body '{"summary":"Test"}'
skylightctl raw put    /api/frames/FRAME_ID/chores/CHORE_ID   --body '{"summary":"Test"}'
skylightctl raw patch  /api/frames/FRAME_ID/rewards/REWARD_ID --body '{"name":"Test"}'
skylightctl raw delete /api/frames/FRAME_ID/chores/CHORE_ID
```

`--body` accepts inline JSON or `@path/to/file.json` to load from disk.

## Output format quick guide

| Situation                              | Use                |
|----------------------------------------|--------------------|
| Agent parsing the result               | default JSON       |
| Logs / shell pipelines                 | `--compact`        |
| Person reading setup or a dry-run      | `--output human`   |
| Showing a user the planned mutation    | `--output human` on the dry-run, JSON on the `--execute` |

## Environment variables

```
SKYLIGHT_BASE_URL=https://app.ourskylight.com
SKYLIGHT_CONFIG=~/.config/skylightctl/config.json
SKYLIGHT_DEVICE_FINGERPRINT=<stable UUID>
SKYLIGHT_REFRESH_TOKEN=<oauth refresh token>
SKYLIGHT_AUTH_HEADER="Bearer <access_token>"
SKYLIGHT_FRAME_ID=<frame id>
SKYLIGHT_PROFILE=default
SKYLIGHT_TIMEOUT=30
SKYLIGHT_API_VERSION=2026-03-01
```

Precedence: CLI flag > env var > profile config > built-in default.
