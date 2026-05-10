from __future__ import annotations

import json
from typing import Any

import typer


def emit_json(data: Any, *, err: bool = False, compact: bool = False) -> None:
    kwargs: dict[str, Any] = {"sort_keys": True}
    if not compact:
        kwargs["indent"] = 2
    typer.echo(json.dumps(data, **kwargs), err=err)
