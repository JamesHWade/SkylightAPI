#!/usr/bin/env python3
"""Validate repo-local Codex skill metadata without external dependencies."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"
MAX_SKILL_NAME_LENGTH = 64
MAX_DESCRIPTION_LENGTH = 1024
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FRONTMATTER_KEY_RE = re.compile(r"^([A-Za-z0-9_-]+):(?:\s+(.+))?$")
AGENT_KEY_RE = re.compile(r"^(\s*)([A-Za-z0-9_-]+)\s*:(?:\s+(.*))?\s*$")


def main() -> int:
    errors: list[str] = []
    if not SKILLS_DIR.exists():
        print("No skills directory found.")
        return 0

    skill_dirs = sorted(path for path in SKILLS_DIR.iterdir() if path.is_dir())
    if not skill_dirs:
        errors.append("skills/ exists but contains no skill directories.")

    for skill_dir in skill_dirs:
        errors.extend(validate_skill(skill_dir))

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(f"Validated {len(skill_dirs)} skill(s).")
    return 0


def validate_skill(skill_dir: Path) -> list[str]:
    errors: list[str] = []
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return [f"{skill_dir.relative_to(ROOT)} is missing SKILL.md"]

    frontmatter, frontmatter_errors = parse_frontmatter(skill_md)
    errors.extend(frontmatter_errors)
    if frontmatter_errors:
        return errors

    allowed_keys = {"name", "description"}
    unexpected = sorted(set(frontmatter) - allowed_keys)
    if unexpected:
        errors.append(
            f"{skill_md.relative_to(ROOT)} has unexpected frontmatter keys: "
            f"{', '.join(unexpected)}"
        )

    name = frontmatter.get("name", "").strip()
    description = frontmatter.get("description", "").strip()

    if not name:
        errors.append(f"{skill_md.relative_to(ROOT)} is missing frontmatter name")
    elif not NAME_RE.match(name):
        errors.append(f"{skill_md.relative_to(ROOT)} name must be hyphen-case: {name}")
    elif len(name) > MAX_SKILL_NAME_LENGTH:
        errors.append(
            f"{skill_md.relative_to(ROOT)} name is too long: "
            f"{len(name)} characters"
        )

    if name and skill_dir.name != name:
        errors.append(
            f"{skill_dir.relative_to(ROOT)} directory name must match skill name {name}"
        )

    if not description:
        errors.append(f"{skill_md.relative_to(ROOT)} is missing frontmatter description")
    elif len(description) > MAX_DESCRIPTION_LENGTH:
        errors.append(
            f"{skill_md.relative_to(ROOT)} description is too long: "
            f"{len(description)} characters"
        )
    elif "<" in description or ">" in description:
        errors.append(f"{skill_md.relative_to(ROOT)} description cannot contain angle brackets")

    agent_yaml = skill_dir / "agents" / "openai.yaml"
    if agent_yaml.exists():
        errors.extend(validate_agent_yaml(agent_yaml, name))

    return errors


def parse_frontmatter(path: Path) -> tuple[dict[str, str], list[str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        return {}, [f"{path.relative_to(ROOT)} must start with YAML frontmatter"]

    try:
        end_index = lines[1:].index("---") + 1
    except ValueError:
        return {}, [f"{path.relative_to(ROOT)} has no closing frontmatter marker"]

    frontmatter: dict[str, str] = {}
    errors: list[str] = []
    for line_number, line in enumerate(lines[1:end_index], start=2):
        if not line.strip():
            continue
        match = FRONTMATTER_KEY_RE.match(line)
        if not match:
            errors.append(
                f"{path.relative_to(ROOT)}:{line_number} has unsupported "
                "frontmatter syntax"
            )
            continue
        key, value = match.groups()
        if key in frontmatter:
            errors.append(f"{path.relative_to(ROOT)}:{line_number} repeats key {key}")
        frontmatter[key] = clean_scalar(value or "")

    return frontmatter, errors


def validate_agent_yaml(path: Path, skill_name: str) -> list[str]:
    errors: list[str] = []
    values: dict[str, str] = {}
    current_section: str | None = None
    section_indent: int | None = None

    for line_number, raw in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = AGENT_KEY_RE.match(raw)
        if not match:
            continue
        indent, key, raw_value = match.groups()
        indent_len = len(indent)
        value = (raw_value or "").strip()

        if indent_len == 0:
            current_section = key if value == "" else None
            section_indent = None
            continue

        if current_section != "interface":
            continue

        if section_indent is None:
            section_indent = indent_len
        elif indent_len != section_indent:
            continue

        if value.startswith("|") or value.startswith(">"):
            errors.append(
                f"{path.relative_to(ROOT)}:{line_number} interface.{key} uses an "
                "unsupported block scalar; inline the value as a quoted or "
                "unquoted single-line string"
            )
            continue

        values[key] = clean_scalar(_strip_inline_comment(value))

    for key in ("display_name", "short_description", "default_prompt"):
        if not values.get(key):
            errors.append(f"{path.relative_to(ROOT)} is missing interface.{key}")

    short_description = values.get("short_description", "")
    if short_description and not 25 <= len(short_description) <= 64:
        errors.append(
            f"{path.relative_to(ROOT)} interface.short_description must be "
            "25-64 characters"
        )

    default_prompt = values.get("default_prompt", "")
    if skill_name and default_prompt and f"${skill_name}" not in default_prompt:
        errors.append(
            f"{path.relative_to(ROOT)} interface.default_prompt must mention "
            f"${skill_name}"
        )

    return errors


def clean_scalar(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _strip_inline_comment(value: str) -> str:
    """Strip a trailing ' # ...' comment from an unquoted YAML scalar."""
    if value.startswith(('"', "'")):
        return value
    hash_index = value.find(" #")
    if hash_index == -1:
        return value
    return value[:hash_index].rstrip()


if __name__ == "__main__":
    raise SystemExit(main())
