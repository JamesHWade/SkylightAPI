from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Any, Never
from urllib.parse import quote

import httpx
import typer

from skylight_cli import __version__
from skylight_cli.client import SkylightClient
from skylight_cli.config import (
    Settings,
    public_settings,
    require_auth,
    require_frame_id,
    resolve_settings,
    save_profile,
)
from skylight_cli.errors import ApiError, ConfigError
from skylight_cli.oauth import OAuthToken, login_headless, refresh_oauth_token
from skylight_cli.output import emit_json

app = typer.Typer(
    no_args_is_help=True,
    invoke_without_command=True,
    help="Agent-friendly CLI for the unofficial Skylight API reference.",
)
auth_app = typer.Typer(no_args_is_help=True, help="Authentication helpers.")
frames_app = typer.Typer(no_args_is_help=True, help="Frame operations.")
chores_app = typer.Typer(no_args_is_help=True, help="Chore operations.")
categories_app = typer.Typer(no_args_is_help=True, help="Category operations.")
devices_app = typer.Typer(no_args_is_help=True, help="Device operations.")
lists_app = typer.Typer(no_args_is_help=True, help="List operations.")
task_box_app = typer.Typer(no_args_is_help=True, help="Task box operations.")
calendars_app = typer.Typer(no_args_is_help=True, help="Calendar operations.")
rewards_app = typer.Typer(no_args_is_help=True, help="Reward operations.")
raw_app = typer.Typer(no_args_is_help=True, help="Low-level endpoint escape hatch.")
config_app = typer.Typer(no_args_is_help=True, help="Configuration inspection.")
discover_app = typer.Typer(no_args_is_help=True, help="Safe route drift discovery.")
smoke_app = typer.Typer(no_args_is_help=True, help="Read-only live smoke checks.")

app.add_typer(auth_app, name="auth")
app.add_typer(frames_app, name="frames")
app.add_typer(chores_app, name="chores")
app.add_typer(categories_app, name="categories")
app.add_typer(devices_app, name="devices")
app.add_typer(lists_app, name="lists")
app.add_typer(task_box_app, name="task-box")
app.add_typer(calendars_app, name="calendars")
app.add_typer(rewards_app, name="rewards")
app.add_typer(raw_app, name="raw")
app.add_typer(config_app, name="config")
app.add_typer(discover_app, name="discover")
app.add_typer(smoke_app, name="smoke")

DEFAULT_ROUTE_PROBES = [
    "/api/frames",
    "/api/frames/{frameId}",
    "/api/frames/{frameId}/chores",
    "/api/frames/{frameId}/categories",
    "/api/frames/{frameId}/devices",
    "/api/frames/{frameId}/lists",
    "/api/frames/{frameId}/task_box/items",
    "/api/frames/{frameId}/source_calendars",
    "/api/frames/{frameId}/calendar_events",
    "/api/frames/{frameId}/rewards",
    "/api/frames/{frameId}/reward_points",
    "/api/frames/{frameId}/tasks",
    "/api/frames/{frameId}/routines",
    "/api/frames/{frameId}/profiles",
]

CHORE_INSTANCE_ID_RE = re.compile(r"^(\d+)-(\d{4}-\d{2}-\d{2})")


@dataclass(frozen=True)
class CliState:
    profile: str | None
    base_url: str | None
    auth_header: str | None
    frame_id: str | None
    timeout: float | None
    compact: bool


@app.callback()
def callback(
    ctx: typer.Context,
    profile: Annotated[
        str | None,
        typer.Option("--profile", help="Config profile. Env: SKYLIGHT_PROFILE."),
    ] = None,
    base_url: Annotated[
        str | None,
        typer.Option("--base-url", help="API base URL. Env: SKYLIGHT_BASE_URL."),
    ] = None,
    auth_header: Annotated[
        str | None,
        typer.Option(
            "--auth-header",
            help="Complete Authorization header value. Env: SKYLIGHT_AUTH_HEADER.",
        ),
    ] = None,
    frame_id: Annotated[
        str | None,
        typer.Option("--frame-id", help="Default frame id. Env: SKYLIGHT_FRAME_ID."),
    ] = None,
    timeout: Annotated[
        float | None,
        typer.Option("--timeout", help="HTTP timeout in seconds. Env: SKYLIGHT_TIMEOUT."),
    ] = None,
    compact: Annotated[
        bool,
        typer.Option("--compact", help="Emit compact JSON without indentation."),
    ] = False,
    version: Annotated[
        bool,
        typer.Option("--version", help="Show version and exit."),
    ] = False,
) -> None:
    if version:
        emit_json({"version": __version__}, compact=compact)
        raise typer.Exit()

    ctx.obj = CliState(
        profile=profile,
        base_url=base_url,
        auth_header=auth_header,
        frame_id=frame_id,
        timeout=timeout,
        compact=compact,
    )


@app.command("capabilities")
def capabilities(ctx: typer.Context) -> None:
    """Print the stable command surface for agents."""
    state = _state(ctx)
    emit_json(
        {
            "version": __version__,
            "defaults": {
                "json": True,
                "write_safety": "mutations require --execute; otherwise dry-run",
                "auth_env": "SKYLIGHT_AUTH_HEADER",
                "frame_env": "SKYLIGHT_FRAME_ID",
            },
            "commands": [
                {"name": "auth login", "method": "OAuth", "operationId": None},
                {"name": "auth refresh", "method": "OAuth", "operationId": None},
                {"name": "doctor", "method": "GET", "operationId": None},
                {"name": "smoke read", "method": "GET", "operationId": None},
                {"name": "frames list", "method": "GET", "operationId": "listFrames"},
                {"name": "frames get", "method": "GET", "operationId": "getFrame"},
                {"name": "frames use", "method": "GET", "operationId": None},
                {"name": "chores list", "method": "GET", "operationId": "listChores"},
                {"name": "chores create", "method": "POST", "operationId": "createChore"},
                {"name": "chores update", "method": "PUT", "operationId": "updateChore"},
                {"name": "chores complete", "method": "PUT", "operationId": "setChoreCompletion"},
                {"name": "chores skip", "method": "PUT", "operationId": "setChoreCompletion"},
                {"name": "chores delete", "method": "DELETE", "operationId": "deleteChore"},
                {"name": "categories list", "method": "GET", "operationId": "listCategories"},
                {"name": "devices list", "method": "GET", "operationId": "listDevices"},
                {"name": "lists list", "method": "GET", "operationId": "listLists"},
                {"name": "lists get", "method": "GET", "operationId": "getList"},
                {
                    "name": "task-box create",
                    "method": "POST",
                    "operationId": "createTaskBoxItem",
                },
                {
                    "name": "calendars sources",
                    "method": "GET",
                    "operationId": "listSourceCalendars",
                },
                {
                    "name": "calendars events",
                    "method": "GET",
                    "operationId": "listCalendarEvents",
                },
                {"name": "rewards list", "method": "GET", "operationId": "listRewards"},
                {"name": "rewards points", "method": "GET", "operationId": "listRewardPoints"},
                {"name": "raw get", "method": "GET", "operationId": None},
                {"name": "raw post", "method": "POST", "operationId": None},
                {"name": "raw put", "method": "PUT", "operationId": None},
                {"name": "raw patch", "method": "PATCH", "operationId": None},
                {"name": "raw delete", "method": "DELETE", "operationId": None},
                {"name": "discover routes", "method": "GET", "operationId": None},
                {"name": "config show", "method": None, "operationId": None},
            ],
        },
        compact=state.compact,
    )


@app.command("doctor")
def doctor(
    ctx: typer.Context,
    live: Annotated[
        bool,
        typer.Option(
            "--live/--no-live",
            help="Run read-only API checks in addition to local config checks.",
        ),
    ] = True,
) -> None:
    """Check whether skylightctl is configured and ready for agent use."""
    state = _state(ctx)
    settings = _settings(ctx, require_config_auth=False, require_config_frame=False)
    checks = [
        _doctor_check("config_file", settings.config_path.exists(), str(settings.config_path)),
        _doctor_check(
            "auth_header",
            bool(settings.auth_header),
            "saved or env Authorization header",
        ),
        _doctor_check("refresh_token", bool(settings.refresh_token), "needed for token rotation"),
        _doctor_check(
            "device_fingerprint",
            bool(settings.device_fingerprint),
            "needed for token refresh",
        ),
        _doctor_check("frame_id", bool(settings.frame_id), "needed for frame-scoped commands"),
        _doctor_check("api_version", bool(settings.api_version), settings.api_version),
    ]

    live_results: list[dict[str, Any]] = []
    if live and settings.auth_header:
        client = SkylightClient(settings)
        frames_result, frames_body = _read_check(client, "frames.list", "/api/frames")
        live_results.append(frames_result)
        frame_id = settings.frame_id
        if not frame_id:
            frame_id = _first_resource_id(frames_body)
        if frame_id:
            frame_result, _frame_body = _read_check(
                client,
                "frames.get",
                f"/api/frames/{frame_id}",
            )
            live_results.append(frame_result)
    elif live:
        live_results.append(
            {
                "name": "frames.list",
                "ok": False,
                "skipped": True,
                "reason": "auth header is not configured",
            }
        )

    ready = all(check["ok"] for check in checks) and all(
        result.get("ok") or result.get("skipped") for result in live_results
    )
    emit_json(
        {
            "status": "ok" if ready else "needs_setup",
            "ready": ready,
            "profile": settings.profile,
            "config_path": str(settings.config_path),
            "base_url": settings.base_url,
            "checks": checks,
            "live": live_results,
            "next_steps": _doctor_next_steps(settings, checks),
        },
        compact=state.compact,
    )


@config_app.command("show")
def config_show(ctx: typer.Context) -> None:
    """Show resolved config with secrets redacted."""
    state = _state(ctx)
    try:
        settings = _settings(ctx, require_config_auth=False, require_config_frame=False)
    except ConfigError as exc:
        _exit_error(state, "config_error", str(exc))
    emit_json(public_settings(settings), compact=state.compact)


@auth_app.command("login")
def auth_login(
    ctx: typer.Context,
    email: Annotated[
        str | None,
        typer.Option("--email", help="Skylight account email. Env: SKYLIGHT_EMAIL."),
    ] = None,
    password: Annotated[
        str | None,
        typer.Option("--password", help="Skylight account password. Env: SKYLIGHT_PASSWORD."),
    ] = None,
    show_secret: Annotated[
        bool,
        typer.Option("--show-secret", help="Print the full Authorization header."),
    ] = False,
    save: Annotated[
        bool,
        typer.Option("--save", help="Save tokens to the selected config profile."),
    ] = False,
    fingerprint: Annotated[
        str | None,
        typer.Option(
            "--fingerprint",
            help="Stable device UUID. Env: SKYLIGHT_DEVICE_FINGERPRINT.",
        ),
    ] = None,
    no_input: Annotated[
        bool,
        typer.Option("--no-input", help="Do not prompt; fail if credentials are missing."),
    ] = False,
) -> None:
    """Authenticate through Skylight's headless OAuth form flow and build a Bearer header."""
    state = _state(ctx)
    settings = _settings(ctx, require_config_auth=False, require_config_frame=False)
    resolved_email = email or os.getenv("SKYLIGHT_EMAIL")
    resolved_password = password or os.getenv("SKYLIGHT_PASSWORD")
    resolved_fingerprint = (
        fingerprint
        or os.getenv("SKYLIGHT_DEVICE_FINGERPRINT")
        or settings.device_fingerprint
        or str(uuid.uuid4())
    )
    resolved_email = _resolve_prompted_value(
        state,
        value=resolved_email,
        prompt="Skylight email",
        no_input=no_input,
        missing_message="Missing email. Pass --email, set SKYLIGHT_EMAIL, or run interactively.",
    )
    resolved_password = _resolve_prompted_value(
        state,
        value=resolved_password,
        prompt="Skylight password",
        no_input=no_input,
        hide_input=True,
        missing_message=(
            "Missing password. Pass --password, set SKYLIGHT_PASSWORD, or run interactively."
        ),
    )

    try:
        token = login_headless(
            base_url=settings.base_url,
            email=resolved_email,
            password=resolved_password,
            fingerprint=resolved_fingerprint,
            timeout=settings.timeout,
        )
    except ConfigError as exc:
        _exit_error(state, "auth_error", str(exc))
    except httpx.HTTPError as exc:
        _exit_error(state, "network_error", str(exc))

    if save:
        _save_oauth_settings(settings, token, resolved_fingerprint)

    payload = _oauth_payload(
        token,
        show_secret=show_secret,
        fingerprint=resolved_fingerprint,
    )
    if save:
        payload["saved"] = True
        payload["profile"] = settings.profile
        payload["config_path"] = str(settings.config_path)
    emit_json(payload, compact=state.compact)


@auth_app.command("refresh")
def auth_refresh(
    ctx: typer.Context,
    refresh_token: Annotated[
        str | None,
        typer.Option("--refresh-token", help="OAuth refresh token. Env: SKYLIGHT_REFRESH_TOKEN."),
    ] = None,
    fingerprint: Annotated[
        str | None,
        typer.Option(
            "--fingerprint",
            help="Stable device UUID used for login. Env: SKYLIGHT_DEVICE_FINGERPRINT.",
        ),
    ] = None,
    show_secret: Annotated[
        bool,
        typer.Option("--show-secret", help="Print refreshed tokens."),
    ] = False,
    save: Annotated[
        bool,
        typer.Option("--save", help="Save refreshed tokens to the selected config profile."),
    ] = False,
) -> None:
    """Refresh OAuth credentials and build a Bearer auth header."""
    state = _state(ctx)
    settings = _settings(ctx, require_config_auth=False, require_config_frame=False)
    resolved_refresh_token = (
        refresh_token or os.getenv("SKYLIGHT_REFRESH_TOKEN") or settings.refresh_token
    )
    resolved_fingerprint = (
        fingerprint or os.getenv("SKYLIGHT_DEVICE_FINGERPRINT") or settings.device_fingerprint
    )
    if not resolved_refresh_token:
        _exit_error(
            state,
            "config_error",
            "Missing refresh token. Pass --refresh-token or set SKYLIGHT_REFRESH_TOKEN.",
        )
    if not resolved_fingerprint:
        _exit_error(
            state,
            "config_error",
            "Missing fingerprint. Pass --fingerprint or set SKYLIGHT_DEVICE_FINGERPRINT.",
        )

    try:
        token = refresh_oauth_token(
            base_url=settings.base_url,
            refresh_token=resolved_refresh_token,
            fingerprint=resolved_fingerprint,
            timeout=settings.timeout,
        )
    except ConfigError as exc:
        _exit_error(state, "auth_error", str(exc))
    except httpx.HTTPError as exc:
        _exit_error(state, "network_error", str(exc))

    if save:
        _save_oauth_settings(settings, token, resolved_fingerprint)

    payload = _oauth_payload(
        token,
        show_secret=show_secret,
        fingerprint=resolved_fingerprint,
    )
    if save:
        payload["saved"] = True
        payload["profile"] = settings.profile
        payload["config_path"] = str(settings.config_path)
    emit_json(payload, compact=state.compact)


@frames_app.command("list")
def list_frames(ctx: typer.Context) -> None:
    """List frames the authenticated account can see."""
    _emit_request(ctx, "GET", "/api/frames")


@frames_app.command("get")
def get_frame(
    ctx: typer.Context,
    frame_id: Annotated[
        str | None,
        typer.Option("--frame-id", help="Frame id. Falls back to SKYLIGHT_FRAME_ID."),
    ] = None,
) -> None:
    """Fetch a single frame by id."""
    settings = _settings(ctx, frame_id=frame_id)
    frame = require_frame_id(settings)
    _emit_request(ctx, "GET", f"/api/frames/{frame}")


@frames_app.command("use")
def use_frame(
    ctx: typer.Context,
    frame_id: Annotated[
        str | None,
        typer.Argument(help="Frame id to save. Omit with --first to use the first frame."),
    ] = None,
    first: Annotated[
        bool,
        typer.Option("--first", help="Save the first frame returned by frames list."),
    ] = False,
    verify: Annotated[
        bool,
        typer.Option("--verify/--no-verify", help="Verify the frame with a read-only request."),
    ] = True,
) -> None:
    """Save the default frame id in the selected profile."""
    state = _state(ctx)
    settings = _settings(ctx, require_config_frame=False)
    selected_frame = frame_id
    source = "argument"

    if first:
        try:
            frames_body = SkylightClient(settings).request("GET", "/api/frames")
        except ApiError as exc:
            _exit_error(
                state,
                "api_error",
                str(exc),
                details={"status_code": exc.status_code, "body": exc.body},
            )
        except ConfigError as exc:
            _exit_error(state, "config_error", str(exc))
        except httpx.HTTPError as exc:
            _exit_error(state, "network_error", str(exc))
        selected_frame = _first_resource_id(frames_body)
        source = "first"
        if not selected_frame:
            _exit_error(state, "api_error", "No frames were returned by /api/frames.")

    if not selected_frame:
        _exit_error(state, "usage_error", "Pass a frame id or use --first.")

    if verify:
        try:
            SkylightClient(settings).request("GET", f"/api/frames/{selected_frame}")
        except ApiError as exc:
            _exit_error(
                state,
                "api_error",
                str(exc),
                details={"status_code": exc.status_code, "body": exc.body},
            )
        except ConfigError as exc:
            _exit_error(state, "config_error", str(exc))
        except httpx.HTTPError as exc:
            _exit_error(state, "network_error", str(exc))

    _save_frame_settings(settings, selected_frame)
    emit_json(
        {
            "saved": True,
            "profile": settings.profile,
            "config_path": str(settings.config_path),
            "frame_id": selected_frame,
            "source": source,
            "verified": verify,
        },
        compact=state.compact,
    )


@chores_app.command("list")
def list_chores(
    ctx: typer.Context,
    frame_id: Annotated[
        str | None,
        typer.Option("--frame-id", help="Frame id. Falls back to SKYLIGHT_FRAME_ID."),
    ] = None,
    after: Annotated[
        str | None,
        typer.Option("--after", help="Start date, YYYY-MM-DD."),
    ] = None,
    before: Annotated[
        str | None,
        typer.Option("--before", help="End date, YYYY-MM-DD."),
    ] = None,
    include_late: Annotated[
        bool,
        typer.Option("--include-late", help="Include late chores."),
    ] = False,
    filter_value: Annotated[
        str | None,
        typer.Option("--filter", help="Optional filter, e.g. linked_to_profile."),
    ] = None,
) -> None:
    """List chores in the selected frame, optionally bounded by date."""
    settings = _settings(ctx, frame_id=frame_id)
    frame = require_frame_id(settings)
    params: dict[str, object] = {
        "after": after,
        "before": before,
        "include_late": include_late if include_late else None,
        "filter": filter_value,
    }
    _emit_request(ctx, "GET", f"/api/frames/{frame}/chores", params=params)


@chores_app.command("create")
def create_chore(
    ctx: typer.Context,
    summary: Annotated[str, typer.Option("--summary", help="Chore summary.")],
    start: Annotated[str, typer.Option("--start", help="Start date, YYYY-MM-DD.")],
    frame_id: Annotated[
        str | None,
        typer.Option("--frame-id", help="Frame id. Falls back to SKYLIGHT_FRAME_ID."),
    ] = None,
    status: Annotated[
        str,
        typer.Option("--status", help="Initial status, e.g. pending|complete|skipped."),
    ] = "pending",
    start_time: Annotated[
        str | None,
        typer.Option("--start-time", help="Optional local time such as 10:00."),
    ] = None,
    recurring: Annotated[
        bool,
        typer.Option("--recurring", help="Mark chore as recurring."),
    ] = False,
    category_id: Annotated[
        str | None,
        typer.Option("--category-id", help="Optional category relationship id."),
    ] = None,
    reward_points: Annotated[
        int | None,
        typer.Option("--reward-points", help="Optional reward point value."),
    ] = None,
    emoji_icon: Annotated[
        str | None,
        typer.Option("--emoji-icon", help="Optional emoji icon value."),
    ] = None,
    routine: Annotated[
        bool | None,
        typer.Option("--routine/--no-routine", help="Optional routine flag."),
    ] = None,
    execute: Annotated[
        bool,
        typer.Option("--execute", help="Send the mutation. Without this, only print dry-run."),
    ] = False,
) -> None:
    """Create a chore using the current flat write body."""
    settings = _settings(ctx, frame_id=frame_id, require_config_auth=execute)
    frame = require_frame_id(settings)
    body = _chore_write_body(
        summary=summary,
        status=status,
        start=start,
        start_time=start_time,
        recurring=recurring,
        category_id=category_id,
        reward_points=reward_points,
        emoji_icon=emoji_icon,
        routine=routine,
    )
    _emit_mutation(ctx, "POST", f"/api/frames/{frame}/chores", body, execute=execute)


@chores_app.command("update")
def update_chore(
    ctx: typer.Context,
    chore_id: Annotated[str, typer.Option("--chore-id", help="Chore id.")],
    frame_id: Annotated[
        str | None,
        typer.Option("--frame-id", help="Frame id. Falls back to SKYLIGHT_FRAME_ID."),
    ] = None,
    summary: Annotated[str | None, typer.Option("--summary", help="New chore summary.")] = None,
    start: Annotated[
        str | None,
        typer.Option("--start", help="New start date, YYYY-MM-DD."),
    ] = None,
    status: Annotated[
        str | None,
        typer.Option("--status", help="New status, for example pending."),
    ] = None,
    start_time: Annotated[
        str | None,
        typer.Option("--start-time", help="Optional local time such as 10:00."),
    ] = None,
    recurring: Annotated[
        bool | None,
        typer.Option("--recurring/--not-recurring", help="Optional recurring flag."),
    ] = None,
    category_id: Annotated[
        str | None,
        typer.Option("--category-id", help="Optional category relationship id."),
    ] = None,
    reward_points: Annotated[
        int | None,
        typer.Option("--reward-points", help="Optional reward point value."),
    ] = None,
    emoji_icon: Annotated[
        str | None,
        typer.Option("--emoji-icon", help="Optional emoji icon value."),
    ] = None,
    routine: Annotated[
        bool | None,
        typer.Option("--routine/--no-routine", help="Optional routine flag."),
    ] = None,
    execute: Annotated[
        bool,
        typer.Option("--execute", help="Send the mutation. Without this, only print dry-run."),
    ] = False,
) -> None:
    """Update a chore with a flat current-API body."""
    state = _state(ctx)
    settings = _settings(ctx, frame_id=frame_id, require_config_auth=execute)
    frame = require_frame_id(settings)
    body = _chore_write_body(
        summary=summary,
        status=status,
        start=start,
        start_time=start_time,
        recurring=recurring,
        category_id=category_id,
        reward_points=reward_points,
        emoji_icon=emoji_icon,
        routine=routine,
    )
    if not body:
        _exit_error(state, "usage_error", "Pass at least one chore field to update.")
    _emit_mutation(ctx, "PUT", f"/api/frames/{frame}/chores/{chore_id}", body, execute=execute)


@chores_app.command("complete")
def complete_chore(
    ctx: typer.Context,
    chore_id: Annotated[str, typer.Option("--chore-id", help="Chore id or recurring instance id.")],
    frame_id: Annotated[
        str | None,
        typer.Option("--frame-id", help="Frame id. Falls back to SKYLIGHT_FRAME_ID."),
    ] = None,
    instance_date: Annotated[
        str | None,
        typer.Option("--instance-date", help="Recurring instance date, YYYY-MM-DD."),
    ] = None,
    execute: Annotated[
        bool,
        typer.Option("--execute", help="Send the mutation. Without this, only print dry-run."),
    ] = False,
) -> None:
    """Mark a chore or recurring chore instance complete."""
    _emit_chore_completion(
        ctx,
        chore_id=chore_id,
        status="complete",
        frame_id=frame_id,
        instance_date=instance_date,
        execute=execute,
    )


@chores_app.command("skip")
def skip_chore(
    ctx: typer.Context,
    chore_id: Annotated[str, typer.Option("--chore-id", help="Chore id or recurring instance id.")],
    frame_id: Annotated[
        str | None,
        typer.Option("--frame-id", help="Frame id. Falls back to SKYLIGHT_FRAME_ID."),
    ] = None,
    instance_date: Annotated[
        str | None,
        typer.Option("--instance-date", help="Recurring instance date, YYYY-MM-DD."),
    ] = None,
    execute: Annotated[
        bool,
        typer.Option("--execute", help="Send the mutation. Without this, only print dry-run."),
    ] = False,
) -> None:
    """Skip a recurring chore instance."""
    _emit_chore_completion(
        ctx,
        chore_id=chore_id,
        status="skipped",
        frame_id=frame_id,
        instance_date=instance_date,
        execute=execute,
    )


@chores_app.command("delete")
def delete_chore(
    ctx: typer.Context,
    chore_id: Annotated[str, typer.Option("--chore-id", help="Chore id.")],
    frame_id: Annotated[
        str | None,
        typer.Option("--frame-id", help="Frame id. Falls back to SKYLIGHT_FRAME_ID."),
    ] = None,
    execute: Annotated[
        bool,
        typer.Option("--execute", help="Send the mutation. Without this, only print dry-run."),
    ] = False,
) -> None:
    """Delete a chore."""
    settings = _settings(ctx, frame_id=frame_id, require_config_auth=execute)
    frame = require_frame_id(settings)
    _emit_mutation(ctx, "DELETE", f"/api/frames/{frame}/chores/{chore_id}", None, execute=execute)


@categories_app.command("list")
def list_categories(
    ctx: typer.Context,
    frame_id: Annotated[
        str | None,
        typer.Option("--frame-id", help="Frame id. Falls back to SKYLIGHT_FRAME_ID."),
    ] = None,
) -> None:
    """List chore categories for a frame."""
    settings = _settings(ctx, frame_id=frame_id)
    frame = require_frame_id(settings)
    _emit_request(ctx, "GET", f"/api/frames/{frame}/categories")


@devices_app.command("list")
def list_devices(
    ctx: typer.Context,
    frame_id: Annotated[
        str | None,
        typer.Option("--frame-id", help="Frame id. Falls back to SKYLIGHT_FRAME_ID."),
    ] = None,
) -> None:
    """List devices linked to a frame."""
    settings = _settings(ctx, frame_id=frame_id)
    frame = require_frame_id(settings)
    _emit_request(ctx, "GET", f"/api/frames/{frame}/devices")


@lists_app.command("list")
def list_lists(
    ctx: typer.Context,
    frame_id: Annotated[
        str | None,
        typer.Option("--frame-id", help="Frame id. Falls back to SKYLIGHT_FRAME_ID."),
    ] = None,
) -> None:
    """List shopping/task lists for a frame."""
    settings = _settings(ctx, frame_id=frame_id)
    frame = require_frame_id(settings)
    _emit_request(ctx, "GET", f"/api/frames/{frame}/lists")


@lists_app.command("get")
def get_list(
    ctx: typer.Context,
    list_id: Annotated[str, typer.Option("--list-id", help="List id.")],
    frame_id: Annotated[
        str | None,
        typer.Option("--frame-id", help="Frame id. Falls back to SKYLIGHT_FRAME_ID."),
    ] = None,
) -> None:
    """Fetch a single list with its items."""
    settings = _settings(ctx, frame_id=frame_id)
    frame = require_frame_id(settings)
    _emit_request(ctx, "GET", f"/api/frames/{frame}/lists/{list_id}")


@task_box_app.command("create")
def create_task_box_item(
    ctx: typer.Context,
    summary: Annotated[str, typer.Option("--summary", help="Task summary.")],
    frame_id: Annotated[
        str | None,
        typer.Option("--frame-id", help="Frame id. Falls back to SKYLIGHT_FRAME_ID."),
    ] = None,
    emoji_icon: Annotated[
        str | None,
        typer.Option("--emoji-icon", help="Optional emoji icon value."),
    ] = None,
    routine: Annotated[
        bool | None,
        typer.Option("--routine/--no-routine", help="Optional routine flag."),
    ] = None,
    reward_points: Annotated[
        int | None,
        typer.Option("--reward-points", help="Optional reward point value."),
    ] = None,
    execute: Annotated[
        bool,
        typer.Option("--execute", help="Send the mutation. Without this, only print dry-run."),
    ] = False,
) -> None:
    """Create a task-box item using the JSON:API write envelope."""
    settings = _settings(ctx, frame_id=frame_id, require_config_auth=execute)
    frame = require_frame_id(settings)
    body = {
        "data": {
            "type": "task_box_item",
            "attributes": _without_none(
                {
                    "summary": summary,
                    "emoji_icon": emoji_icon,
                    "routine": routine,
                    "reward_points": reward_points,
                }
            ),
        }
    }
    _emit_mutation(ctx, "POST", f"/api/frames/{frame}/task_box/items", body, execute=execute)


@calendars_app.command("sources")
def list_source_calendars(
    ctx: typer.Context,
    frame_id: Annotated[
        str | None,
        typer.Option("--frame-id", help="Frame id. Falls back to SKYLIGHT_FRAME_ID."),
    ] = None,
) -> None:
    """List source calendars connected to a frame."""
    settings = _settings(ctx, frame_id=frame_id)
    frame = require_frame_id(settings)
    _emit_request(ctx, "GET", f"/api/frames/{frame}/source_calendars")


@calendars_app.command("events")
def list_calendar_events(
    ctx: typer.Context,
    date_min: Annotated[str, typer.Option("--date-min", help="Start date, YYYY-MM-DD.")],
    date_max: Annotated[str, typer.Option("--date-max", help="End date, YYYY-MM-DD.")],
    frame_id: Annotated[
        str | None,
        typer.Option("--frame-id", help="Frame id. Falls back to SKYLIGHT_FRAME_ID."),
    ] = None,
    timezone: Annotated[
        str | None,
        typer.Option("--timezone", help="Optional IANA timezone."),
    ] = None,
    include: Annotated[
        str | None,
        typer.Option(
            "--include",
            help="Optional include CSV such as categories,calendar_account.",
        ),
    ] = None,
) -> None:
    """List calendar events in a date window."""
    settings = _settings(ctx, frame_id=frame_id)
    frame = require_frame_id(settings)
    _emit_request(
        ctx,
        "GET",
        f"/api/frames/{frame}/calendar_events",
        params={
            "date_min": date_min,
            "date_max": date_max,
            "timezone": timezone,
            "include": include,
        },
    )


@rewards_app.command("list")
def list_rewards(
    ctx: typer.Context,
    frame_id: Annotated[
        str | None,
        typer.Option("--frame-id", help="Frame id. Falls back to SKYLIGHT_FRAME_ID."),
    ] = None,
    redeemed_at_min: Annotated[
        str | None,
        typer.Option("--redeemed-at-min", help="Optional date-time lower bound."),
    ] = None,
) -> None:
    """List rewards configured on a frame."""
    settings = _settings(ctx, frame_id=frame_id)
    frame = require_frame_id(settings)
    _emit_request(
        ctx,
        "GET",
        f"/api/frames/{frame}/rewards",
        params={"redeemed_at_min": redeemed_at_min},
    )


@rewards_app.command("points")
def list_reward_points(
    ctx: typer.Context,
    frame_id: Annotated[
        str | None,
        typer.Option("--frame-id", help="Frame id. Falls back to SKYLIGHT_FRAME_ID."),
    ] = None,
) -> None:
    """List reward-point balances per profile in a frame."""
    settings = _settings(ctx, frame_id=frame_id)
    frame = require_frame_id(settings)
    _emit_request(ctx, "GET", f"/api/frames/{frame}/reward_points")


@raw_app.command("get")
def raw_get(
    ctx: typer.Context,
    path: Annotated[str, typer.Argument(help="API path, for example /api/frames/ID/categories.")],
    query: Annotated[
        list[str] | None,
        typer.Option("--query", "-q", help="Query item as key=value. Repeatable."),
    ] = None,
) -> None:
    """Send a raw GET to any API path with optional query items."""
    state = _state(ctx)
    try:
        params = _parse_query(query)
    except ConfigError as exc:
        _exit_error(state, "usage_error", str(exc))
    _emit_request(ctx, "GET", path, params=params)


@raw_app.command("post")
def raw_post(
    ctx: typer.Context,
    path: Annotated[str, typer.Argument(help="API path.")],
    body: Annotated[
        str,
        typer.Option(
            "--body",
            help="JSON body string, or @path/to/file.json to load from disk.",
        ),
    ],
    query: Annotated[
        list[str] | None,
        typer.Option("--query", "-q", help="Query item as key=value. Repeatable."),
    ] = None,
    execute: Annotated[
        bool,
        typer.Option("--execute", help="Send the mutation. Without this, only print dry-run."),
    ] = False,
) -> None:
    """Preview or send a raw POST request."""
    state = _state(ctx)
    try:
        parsed_body = _parse_json_source(body)
        params = _parse_query(query)
    except ConfigError as exc:
        _exit_error(state, "usage_error", str(exc))
    _emit_mutation(ctx, "POST", path, parsed_body, params=params, execute=execute)


@raw_app.command("put")
def raw_put(
    ctx: typer.Context,
    path: Annotated[str, typer.Argument(help="API path.")],
    body: Annotated[
        str,
        typer.Option(
            "--body",
            help="JSON body string, or @path/to/file.json to load from disk.",
        ),
    ],
    query: Annotated[
        list[str] | None,
        typer.Option("--query", "-q", help="Query item as key=value. Repeatable."),
    ] = None,
    execute: Annotated[
        bool,
        typer.Option("--execute", help="Send the mutation. Without this, only print dry-run."),
    ] = False,
) -> None:
    """Preview or send a raw PUT request."""
    _emit_raw_body_mutation(ctx, "PUT", path, body, query=query, execute=execute)


@raw_app.command("patch")
def raw_patch(
    ctx: typer.Context,
    path: Annotated[str, typer.Argument(help="API path.")],
    body: Annotated[
        str,
        typer.Option(
            "--body",
            help="JSON body string, or @path/to/file.json to load from disk.",
        ),
    ],
    query: Annotated[
        list[str] | None,
        typer.Option("--query", "-q", help="Query item as key=value. Repeatable."),
    ] = None,
    execute: Annotated[
        bool,
        typer.Option("--execute", help="Send the mutation. Without this, only print dry-run."),
    ] = False,
) -> None:
    """Preview or send a raw PATCH request."""
    _emit_raw_body_mutation(ctx, "PATCH", path, body, query=query, execute=execute)


@raw_app.command("delete")
def raw_delete(
    ctx: typer.Context,
    path: Annotated[str, typer.Argument(help="API path.")],
    query: Annotated[
        list[str] | None,
        typer.Option("--query", "-q", help="Query item as key=value. Repeatable."),
    ] = None,
    body: Annotated[
        str | None,
        typer.Option(
            "--body",
            help="Optional JSON body string, or @path/to/file.json to load from disk.",
        ),
    ] = None,
    execute: Annotated[
        bool,
        typer.Option("--execute", help="Send the mutation. Without this, only print dry-run."),
    ] = False,
) -> None:
    """Preview or send a raw DELETE request."""
    state = _state(ctx)
    try:
        parsed_body = _parse_json_source(body) if body is not None else None
        params = _parse_query(query)
    except ConfigError as exc:
        _exit_error(state, "usage_error", str(exc))
    _emit_mutation(ctx, "DELETE", path, parsed_body, params=params, execute=execute)


@smoke_app.command("read")
def smoke_read(
    ctx: typer.Context,
    frame_id: Annotated[
        str | None,
        typer.Option("--frame-id", help="Frame id. Falls back to config or first listed frame."),
    ] = None,
    fail_fast: Annotated[
        bool,
        typer.Option("--fail-fast", help="Exit non-zero on the first failed read check."),
    ] = False,
) -> None:
    """Run read-only live checks against safe documented endpoints."""
    state = _state(ctx)
    settings = _settings(
        ctx,
        frame_id=frame_id,
        require_config_auth=True,
        require_config_frame=False,
    )
    client = SkylightClient(settings)
    results: list[dict[str, Any]] = []
    frames_result, frames_body = _read_check(client, "frames.list", "/api/frames")
    results.append(frames_result)
    if fail_fast and not frames_result["ok"]:
        _exit_error(state, "api_error", "frames.list failed", details={"results": results})

    smoke_frame = settings.frame_id or _first_resource_id(frames_body)
    frame_source = "config" if settings.frame_id else "frames.list"
    if not smoke_frame:
        results.append(
            {
                "name": "frame_scoped_routes",
                "ok": False,
                "skipped": True,
                "reason": "no frame id configured or returned by frames.list",
            }
        )
    else:
        for check in _read_smoke_cases(smoke_frame):
            result, _body = _read_check(
                client,
                check["name"],
                check["path"],
                params=check.get("params"),
            )
            results.append(result)
            if fail_fast and not result["ok"]:
                _exit_error(
                    state,
                    "api_error",
                    f"{check['name']} failed",
                    details={"results": results},
                )

    failures = [result for result in results if not result.get("ok") and not result.get("skipped")]
    emit_json(
        {
            "status": "ok" if not failures else "failed",
            "checks": len(results),
            "failures": len(failures),
            "frame_id": smoke_frame,
            "frame_id_source": frame_source if smoke_frame else None,
            "results": results,
        },
        compact=state.compact,
    )


@discover_app.command("routes")
def discover_routes(
    ctx: typer.Context,
    path: Annotated[
        list[str] | None,
        typer.Option(
            "--path",
            help=(
                "Route template or concrete path to probe. "
                "Repeatable. Defaults to known candidates."
            ),
        ),
    ] = None,
    probe_frame_id: Annotated[
        str,
        typer.Option("--probe-frame-id", help="Value used for {frameId} in route templates."),
    ] = "ROUTE_PROBE",
    method: Annotated[
        str,
        typer.Option("--method", help="Safe HTTP method to probe."),
    ] = "GET",
    with_auth: Annotated[
        bool,
        typer.Option("--with-auth", help="Include configured Authorization header in probes."),
    ] = False,
    include_body_preview: Annotated[
        bool,
        typer.Option("--include-body-preview", help="Include up to 500 response characters."),
    ] = False,
) -> None:
    """Probe safe routes and classify 401-vs-404 drift signals."""
    state = _state(ctx)
    if method.upper() not in {"GET", "HEAD"}:
        _exit_error(state, "usage_error", "discover routes only supports GET or HEAD")

    settings = _settings(ctx, require_config_auth=False, require_config_frame=False)
    templates = path or DEFAULT_ROUTE_PROBES
    results = []
    safe_frame_id = quote(probe_frame_id, safe="")
    for template in templates:
        concrete_path = template.replace("{frameId}", safe_frame_id)
        results.append(
            _probe_route(
                settings,
                method.upper(),
                template,
                concrete_path,
                include_auth=with_auth,
                include_body_preview=include_body_preview,
            )
        )

    emit_json(
        {
            "base_url": settings.base_url,
            "probe_frame_id": probe_frame_id,
            "interpretation": {
                "401_with_skylight_api_version": "route likely exists and requires auth",
                "404_without_skylight_api_version": "route likely did not match",
            },
            "routes": results,
        },
        compact=state.compact,
    )


def run() -> None:
    app()


def _settings(
    ctx: typer.Context,
    *,
    frame_id: str | None = None,
    require_config_auth: bool = True,
    require_config_frame: bool = True,
) -> Settings:
    state = _state(ctx)
    try:
        settings = resolve_settings(
            profile=state.profile,
            base_url=state.base_url,
            auth_header=state.auth_header,
            frame_id=frame_id or state.frame_id,
            timeout=state.timeout,
        )
        if require_config_auth:
            require_auth(settings)
        if require_config_frame:
            require_frame_id(settings)
    except ConfigError as exc:
        _exit_error(state, "config_error", str(exc))

    return settings


def _emit_request(
    ctx: typer.Context,
    method: str,
    path: str,
    *,
    params: dict[str, object] | None = None,
) -> None:
    state = _state(ctx)
    settings = _settings(ctx, require_config_frame=False)
    try:
        data = SkylightClient(settings).request(method, path, params=params)
    except ApiError as exc:
        _exit_error(
            state,
            "api_error",
            str(exc),
            details={"status_code": exc.status_code, "body": exc.body},
        )
    except ConfigError as exc:
        _exit_error(state, "config_error", str(exc))
    except httpx.HTTPError as exc:
        _exit_error(state, "network_error", str(exc))

    emit_json(data, compact=state.compact)


def _emit_mutation(
    ctx: typer.Context,
    method: str,
    path: str,
    body: Any,
    *,
    params: dict[str, object] | None = None,
    execute: bool,
) -> None:
    state = _state(ctx)
    settings = _settings(
        ctx,
        require_config_auth=execute,
        require_config_frame=False,
    )
    client = SkylightClient(settings)
    if not execute:
        emit_json(
            {
                "dry_run": True,
                "message": "Pass --execute to send this request.",
                "request": client.preview_request(method, path, params=params, json_body=body),
            },
            compact=state.compact,
        )
        return

    try:
        data = client.request(method, path, params=params, json_body=body)
    except ApiError as exc:
        _exit_error(
            state,
            "api_error",
            str(exc),
            details={"status_code": exc.status_code, "body": exc.body},
        )
    except ConfigError as exc:
        _exit_error(state, "config_error", str(exc))
    except httpx.HTTPError as exc:
        _exit_error(state, "network_error", str(exc))

    emit_json(data, compact=state.compact)


def _read_check(
    client: SkylightClient,
    name: str,
    path: str,
    *,
    params: dict[str, object] | None = None,
) -> tuple[dict[str, Any], Any | None]:
    try:
        body = client.request("GET", path, params=params)
    except ApiError as exc:
        return (
            {
                "name": name,
                "method": "GET",
                "path": path,
                "ok": False,
                "status_code": exc.status_code,
                "body_shape": _body_shape(exc.body),
            },
            None,
        )
    except ConfigError as exc:
        return (
            {
                "name": name,
                "method": "GET",
                "path": path,
                "ok": False,
                "error": str(exc),
                "kind": "config_error",
            },
            None,
        )
    except httpx.HTTPError as exc:
        return (
            {
                "name": name,
                "method": "GET",
                "path": path,
                "ok": False,
                "error": str(exc),
            },
            None,
        )

    return (
        {
            "name": name,
            "method": "GET",
            "path": path,
            "ok": True,
            "data_count": _data_count(body),
            "body_shape": _body_shape(body),
        },
        body,
    )


def _read_smoke_cases(frame_id: str) -> list[dict[str, Any]]:
    today = date.today()
    after = (today - timedelta(days=7)).isoformat()
    before = (today + timedelta(days=7)).isoformat()
    return [
        {"name": "frames.get", "path": f"/api/frames/{frame_id}"},
        {
            "name": "chores.list",
            "path": f"/api/frames/{frame_id}/chores",
            "params": {"after": after, "before": before},
        },
        {"name": "categories.list", "path": f"/api/frames/{frame_id}/categories"},
        {"name": "devices.list", "path": f"/api/frames/{frame_id}/devices"},
        {"name": "lists.list", "path": f"/api/frames/{frame_id}/lists"},
        {"name": "calendars.sources", "path": f"/api/frames/{frame_id}/source_calendars"},
        {
            "name": "calendars.events",
            "path": f"/api/frames/{frame_id}/calendar_events",
            "params": {"date_min": today.isoformat(), "date_max": before},
        },
        {"name": "rewards.list", "path": f"/api/frames/{frame_id}/rewards"},
        {"name": "rewards.points", "path": f"/api/frames/{frame_id}/reward_points"},
    ]


def _data_count(body: Any) -> int | None:
    if isinstance(body, dict):
        data = body.get("data")
        if isinstance(data, list):
            return len(data)
        if isinstance(data, dict):
            return 1
    return None


def _body_shape(body: Any) -> str:
    if isinstance(body, dict):
        keys = ",".join(sorted(str(key) for key in body)[:5])
        return f"object:{keys}"
    if isinstance(body, list):
        return "array"
    if body is None:
        return "empty"
    return type(body).__name__


def _state(ctx: typer.Context) -> CliState:
    if isinstance(ctx.obj, CliState):
        return ctx.obj
    return CliState(
        profile=None,
        base_url=None,
        auth_header=None,
        frame_id=None,
        timeout=None,
        compact=False,
    )


def _exit_error(
    state: CliState,
    kind: str,
    message: str,
    *,
    details: dict[str, Any] | None = None,
) -> Never:
    error: dict[str, Any] = {"kind": kind, "message": message}
    if details:
        error["details"] = details
    payload = {"error": error}
    emit_json(payload, err=True, compact=state.compact)
    raise typer.Exit(1)


def _without_none(values: dict[str, object | None]) -> dict[str, object]:
    return {key: value for key, value in values.items() if value is not None}


def _parse_query(items: list[str] | None) -> dict[str, object]:
    parsed: dict[str, object] = {}
    for item in items or []:
        key, separator, value = item.partition("=")
        if not separator or not key:
            raise ConfigError(f"Invalid query item '{item}'; expected key=value")
        parsed[key] = value
    return parsed


def _parse_json_source(value: str) -> Any:
    if value.startswith("@"):
        path = Path(value[1:])
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigError(f"Cannot read JSON body file {path}: {exc}") from exc
    else:
        source = value

    try:
        return json.loads(source)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON body: {exc}") from exc


def _resolve_prompted_value(
    state: CliState,
    *,
    value: str | None,
    prompt: str,
    missing_message: str,
    no_input: bool,
    hide_input: bool = False,
) -> str:
    if value:
        return value
    if no_input:
        _exit_error(state, "config_error", missing_message)
    return typer.prompt(prompt, hide_input=hide_input)


def _oauth_payload(
    token: OAuthToken,
    *,
    show_secret: bool,
    fingerprint: str,
) -> dict[str, Any]:
    payload = {
        "authorization_header_redacted": "Bearer REDACTED",
        "set_env": "export SKYLIGHT_AUTH_HEADER='Bearer REDACTED'",
        "secret_output": show_secret,
        "token_type": token.token_type,
        "expires_in": token.expires_in,
        "refresh_token_redacted": "REDACTED" if token.refresh_token else None,
        "device_fingerprint": fingerprint,
    }
    if show_secret:
        payload["authorization_header"] = token.authorization_header
        payload["access_token"] = token.access_token
        payload["refresh_token"] = token.refresh_token
        payload["set_env"] = f"export SKYLIGHT_AUTH_HEADER='{token.authorization_header}'"
        if token.refresh_token:
            payload["refresh_env"] = f"export SKYLIGHT_REFRESH_TOKEN='{token.refresh_token}'"
    return payload


def _save_oauth_settings(
    settings: Settings,
    token: OAuthToken,
    fingerprint: str,
) -> None:
    save_profile(
        config_path=settings.config_path,
        profile=settings.profile,
        values={
            "auth_header": token.authorization_header,
            "refresh_token": token.refresh_token,
            "device_fingerprint": fingerprint,
            "base_url": settings.base_url,
            "api_version": settings.api_version,
            "frame_id": settings.frame_id,
        },
    )


def _save_frame_settings(settings: Settings, frame_id: str) -> None:
    save_profile(
        config_path=settings.config_path,
        profile=settings.profile,
        values={
            "frame_id": frame_id,
            "base_url": settings.base_url,
            "api_version": settings.api_version,
        },
    )


def _doctor_check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail}


def _doctor_next_steps(settings: Settings, checks: list[dict[str, Any]]) -> list[str]:
    missing = {check["name"] for check in checks if not check["ok"]}
    steps = []
    if "auth_header" in missing or "refresh_token" in missing or "device_fingerprint" in missing:
        steps.append("run `skylightctl auth login --save`")
    if not settings.frame_id:
        steps.append("run `skylightctl frames use --first` or `skylightctl frames use FRAME_ID`")
    if "config_file" in missing and not steps:
        steps.append("run `skylightctl auth login --save` to create a config profile")
    return steps


def _first_resource_id(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    data = body.get("data")
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            resource_id = first.get("id")
            if isinstance(resource_id, str) and resource_id:
                return resource_id
    if isinstance(data, dict):
        resource_id = data.get("id")
        if isinstance(resource_id, str) and resource_id:
            return resource_id
    return None


def _chore_write_body(
    *,
    summary: str | None,
    status: str | None,
    start: str | None,
    start_time: str | None,
    recurring: bool | None,
    category_id: str | None,
    reward_points: int | None,
    emoji_icon: str | None,
    routine: bool | None,
) -> dict[str, object]:
    return _without_none(
        {
            "summary": summary,
            "status": status,
            "start": start,
            "start_time": start_time,
            "recurring": recurring,
            "category_id": category_id,
            "reward_points": reward_points,
            "emoji_icon": emoji_icon,
            "routine": routine,
        }
    )


def _emit_chore_completion(
    ctx: typer.Context,
    *,
    chore_id: str,
    status: str,
    frame_id: str | None,
    instance_date: str | None,
    execute: bool,
) -> None:
    settings = _settings(ctx, frame_id=frame_id, require_config_auth=execute)
    frame = require_frame_id(settings)
    base_id, body = _chore_completion(chore_id, status=status, instance_date=instance_date)
    _emit_mutation(
        ctx,
        "PUT",
        f"/api/frames/{frame}/chores/{base_id}/completions",
        body,
        execute=execute,
    )


def _chore_completion(
    chore_id: str,
    *,
    status: str,
    instance_date: str | None,
) -> tuple[str, dict[str, object]]:
    base_id = chore_id
    inferred_instance_date = None
    match = CHORE_INSTANCE_ID_RE.match(chore_id)
    if match:
        base_id = match.group(1)
        inferred_instance_date = match.group(2)

    body = _without_none(
        {
            "status": status,
            "instance_date": instance_date or inferred_instance_date,
        }
    )
    return base_id, body


def _emit_raw_body_mutation(
    ctx: typer.Context,
    method: str,
    path: str,
    body: str,
    *,
    query: list[str] | None,
    execute: bool,
) -> None:
    state = _state(ctx)
    try:
        parsed_body = _parse_json_source(body)
        params = _parse_query(query)
    except ConfigError as exc:
        _exit_error(state, "usage_error", str(exc))
    _emit_mutation(ctx, method, path, parsed_body, params=params, execute=execute)


def _probe_route(
    settings: Settings,
    method: str,
    template: str,
    path: str,
    *,
    include_auth: bool,
    include_body_preview: bool,
) -> dict[str, Any]:
    url = settings.base_url.rstrip("/") + "/" + path.lstrip("/")
    headers = {"Accept": "application/json", "skylight-api-version": settings.api_version}
    if include_auth and settings.auth_header:
        headers["Authorization"] = settings.auth_header

    try:
        with httpx.Client(timeout=settings.timeout, headers=headers) as client:
            response = client.request(method, url)
    except httpx.HTTPError as exc:
        return {
            "template": template,
            "path": path,
            "method": method,
            "error": str(exc),
        }

    api_version = response.headers.get("skylight-api-version")
    classification = "unknown"
    if response.status_code == 401 and api_version:
        classification = "route_requires_auth"
    elif response.status_code == 404 and not api_version:
        classification = "route_not_found"

    result = {
        "template": template,
        "path": path,
        "method": method,
        "status_code": response.status_code,
        "classification": classification,
        "skylight_api_version": api_version,
        "content_type": response.headers.get("content-type"),
    }
    if include_body_preview:
        result["body_preview"] = response.text[:500] if response.text else None
    return result
