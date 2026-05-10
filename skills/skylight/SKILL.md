---
name: skylight
description: Use when working with the unofficial Skylight API at app.ourskylight.com or the skylightctl CLI — managing chores, frames, categories, lists, task-box items, calendar events, or rewards. Trigger on mentions of Skylight, ourskylight, skylightctl, or this SkylightAPI repository, and on requests to inspect, list, create, update, complete, skip, or delete any of those resources.
---

# Skylight skill

Procedural guide for operating the unofficial Skylight API safely. The companion CLI is `skylightctl`; the API reference lives at `docs/openapi/openapi.yaml`. The full command cheat sheet is at `references/commands.md`.

## When to engage

Engage this skill when the user is:

- Operating an account on `app.ourskylight.com`.
- Running `skylightctl` or asking how to.
- Editing `docs/openapi/openapi.yaml`, `examples/`, or anything under `cli/`.
- Capturing a new endpoint to add to the reference.

Do **not** engage for unrelated calendar, chore, or reminder apps — Skylight is a specific product (digital photo frames with shared chores/lists/calendar).

## Standing rules

- **Dry-run first.** Every mutation command prints a redacted request preview unless `--execute` is passed. Always show the dry-run to the user, then ask before re-running with `--execute`.
- **JSON is the default.** Only pass `--output human` when a person is reading the result. Agents should parse the JSON.
- **Never log secrets.** Do not run `--show-secret`, do not echo `Authorization` headers, do not paste raw config files. The CLI redacts by default — keep it that way.
- **Redact before committing.** Tokens, emails, frame IDs, and personal data must be scrubbed from any new fixture in `examples/` or any pasted output.
- **Prefer first-class commands over `raw`.** Use `raw {get,post,put,patch,delete}` only for endpoints that don't yet have a dedicated subcommand. If you reach for `raw` repeatedly, that's a signal to promote the route in `main.py` and `openapi.yaml`.
- **Ownership.** Only run against accounts and devices the user owns or is authorized to manage.

## The agent loop

Run these in order at the start of any Skylight task:

1. `skylightctl capabilities` — confirms the stable command surface and version. If a command you expect is missing, the CLI is older than this skill.
2. `skylightctl doctor` — checks config + a live read. Stop here and surface the failure if any check is `false`.
3. `skylightctl smoke read` — read-only sanity check across the main resources. Reports counts and shapes without dumping account data.

Then choose first-class commands for the task. For mutations:

1. Run without `--execute` and show the user the dry-run preview.
2. Get explicit confirmation.
3. Re-run with `--execute`, capture the response, and report what changed.

## Auth model

- OAuth Bearer (`Authorization: Bearer <access_token>`) plus `skylight-api-version: 2026-03-01`.
- Refresh requires both a saved `refresh_token` and a stable `device_fingerprint`. If either is missing, `auth login --save` is the fix.
- The legacy `POST /api/sessions` flow is intentionally not implemented; do not suggest it.
- On `401`, the CLI refreshes once automatically and persists the rotated refresh token. If persistence fails, the request fails loudly — do not retry blindly.

## Adding a new endpoint

When the user wants to document a route they've observed:

1. Capture the request/response with a proxy (Charles, Proxyman, mitmproxy) or DevTools.
2. **Redact** tokens, emails, names, frame IDs, GPS, and anything personally identifying. Keep the structure intact.
3. Save the redacted pair under `examples/` with a descriptive name.
4. Update `docs/openapi/openapi.yaml` — small, focused diff, one endpoint at a time, JSON:API shape where applicable.
5. If the endpoint is reach-worthy, add a first-class subcommand in `cli/src/skylight_cli/main.py` and register it in the `capabilities` payload (around line 176).

## Don't

- Don't bypass the dry-run by piping `yes` into `--execute` or otherwise auto-confirming writes.
- Don't `git add -A` after running CLI commands — config files, logs, or cached responses with secrets may be sitting in the working tree. Stage specific files.
- Don't suggest editing the OpenAPI spec without a redacted example to back it up.
- Don't auto-retry failed mutations. The dry-run-then-execute contract exists so the agent can stop and ask.

## See also

- `references/commands.md` — full cheat sheet keyed by task.
- `../../docs/openapi/openapi.yaml` — schemas and observed routes.
- `../../docs/auth.md` — OAuth login + refresh details.
- `../../examples/` — redacted request/response fixtures.
