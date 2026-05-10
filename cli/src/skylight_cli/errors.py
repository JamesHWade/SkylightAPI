from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class ConfigError(Exception):
    """Configuration is missing or invalid."""


@dataclass
class ApiError(Exception):
    status_code: int
    method: str
    path: str
    body: Any

    def __str__(self) -> str:
        return f"{self.method} {self.path} failed with HTTP {self.status_code}"
