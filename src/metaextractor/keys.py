"""Anthropic API-key resolution shared by the CLI and the web app.

A key reference can be:
  - a literal key (``sk-ant-...``)
  - ``env:VARNAME``  — read from an environment variable
  - ``file:PATH``    — read the first non-empty line of a file (``~`` expanded)
  - ``None`` / empty — auto-discover from ANTHROPIC_API_KEY then CLAUDE_API_KEY

Surrounding whitespace is always stripped, so a trailing newline in a pasted
value or a key file never produces a spurious ``invalid x-api-key``.
"""
from __future__ import annotations

import os
from pathlib import Path

DEFAULT_API_KEY_ENV_VARS = ("ANTHROPIC_API_KEY", "CLAUDE_API_KEY")


class ApiKeyError(ValueError):
    """Raised when an API key reference cannot be resolved."""


def _first_env(names: tuple[str, ...]) -> str | None:
    for name in names:
        val = os.environ.get(name)
        if val and val.strip():
            return val.strip()
    return None


def resolve_api_key(value: str | None) -> str:
    """Resolve an API-key reference to a literal key. See module docstring."""
    if value is None or not value.strip():
        key = _first_env(DEFAULT_API_KEY_ENV_VARS)
        if key:
            return key
        raise ApiKeyError(
            "No API key found. Set the ANTHROPIC_API_KEY environment variable, "
            "or provide a literal key, 'env:VARNAME', or 'file:PATH'."
        )

    value = value.strip()
    if value.startswith("env:"):
        name = value[4:].strip()
        key = os.environ.get(name)
        if not key or not key.strip():
            raise ApiKeyError(f"env:{name}: environment variable is not set or empty")
        return key.strip()
    if value.startswith("file:"):
        return _read_key_file(Path(value[5:].strip()).expanduser())
    # Forgiving fallback: a bare path to an existing file (that isn't itself a
    # key) was almost certainly meant as a key file — reading the path string
    # as the literal key just yields a 401. Real keys start with "sk-".
    if not value.startswith("sk-"):
        candidate = Path(value).expanduser()
        if candidate.is_file():
            return _read_key_file(candidate)
    return value


def key_fingerprint(key: str) -> str:
    """A non-secret fingerprint of a resolved key for display/diagnostics:
    its length and last 4 characters. Never reveals the key itself."""
    key = key or ""
    tail = key[-4:] if len(key) >= 4 else "?"
    return f"len={len(key)}, ends …{tail}"


def _read_key_file(path: Path) -> str:
    if not path.is_file():
        raise ApiKeyError(f"file:{path}: file not found")
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    raise ApiKeyError(f"file:{path}: file is empty")
