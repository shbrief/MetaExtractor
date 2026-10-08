"""Load, validate and pin reviewer verdict files.

A verdict only means something against the exact extraction it was formed on. If
the draft is re-extracted and a value changes, a verdict recorded against the old
value is not evidence about the new one. So every verdict file carries
``draft_sha256`` and :func:`load_verdicts` refuses a file whose pin does not match
the draft it is being read against.

Validation is against ``schemas/review_verdict.schema.json``, which ships as
package data. ``jsonschema`` is used when available; without it the same required
keys and enums are checked by hand, so a missing optional dependency weakens the
error messages but never silently accepts a malformed file.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Verdict values the format allows. Mirrors the enum in the JSON Schema.
VERDICT_VALUES = frozenset({
    "supported", "unsupported", "wrong_value", "cannot_determine", "gold_wrong",
})
MODES = frozenset({"draft", "adjudication"})


class VerdictError(ValueError):
    """A verdict file is malformed, or is pinned to a different draft."""


@dataclass(frozen=True)
class VerdictFile:
    """One reviewer's verdicts for one draft."""

    path: Path | None
    draft_sha256: str
    mode: str
    reviewer: str
    paper_id: str | None
    verdicts: dict[str, dict[str, Any]]   # unit_id -> {verdict, comment, ...}
    notes: str | None = None

    @property
    def judged(self) -> int:
        return len(self.verdicts)

    def verdict_of(self, unit_id: str) -> str | None:
        entry = self.verdicts.get(unit_id)
        return entry.get("verdict") if entry else None


def verdict_schema() -> dict[str, Any]:
    """The verdict JSON Schema, read from package data."""
    try:
        from importlib.resources import files
        text = (files("metaextractor") / "schemas" / "review_verdict.schema.json").read_text(
            encoding="utf-8")
    except (ImportError, FileNotFoundError, ModuleNotFoundError):
        local = Path(__file__).resolve().parent.parent / "schemas" / "review_verdict.schema.json"
        text = local.read_text(encoding="utf-8")
    return json.loads(text)


def _validate_by_hand(payload: Any) -> None:
    """Structural checks used when ``jsonschema`` is not installed."""
    if not isinstance(payload, dict):
        raise VerdictError("verdict file must be a JSON object")
    for key in ("schema_version", "draft_sha256", "mode", "reviewer", "verdicts"):
        if key not in payload:
            raise VerdictError(f"missing required key {key!r}")
    if payload["schema_version"] != 1:
        raise VerdictError(f"unsupported schema_version {payload['schema_version']!r}; expected 1")
    sha = payload["draft_sha256"]
    if not (isinstance(sha, str) and len(sha) == 64
            and all(c in "0123456789abcdef" for c in sha)):
        raise VerdictError("draft_sha256 must be 64 lowercase hex characters")
    if payload["mode"] not in MODES:
        raise VerdictError(f"mode must be one of {sorted(MODES)}, got {payload['mode']!r}")
    if not (isinstance(payload["reviewer"], str) and payload["reviewer"].strip()):
        raise VerdictError("reviewer must be a non-empty string")
    if not isinstance(payload["verdicts"], list):
        raise VerdictError("verdicts must be an array")
    for i, v in enumerate(payload["verdicts"]):
        if not isinstance(v, dict):
            raise VerdictError(f"verdicts[{i}] must be an object")
        if not v.get("unit_id"):
            raise VerdictError(f"verdicts[{i}] is missing unit_id")
        if v.get("verdict") not in VERDICT_VALUES:
            raise VerdictError(
                f"verdicts[{i}] has verdict {v.get('verdict')!r}; "
                f"expected one of {sorted(VERDICT_VALUES)}")


def validate_verdicts(payload: Any) -> None:
    """Validate a parsed verdict payload, raising :class:`VerdictError`.

    Prefers ``jsonschema`` for its error messages; falls back to equivalent
    hand-written checks so validation never silently becomes a no-op.
    """
    try:
        import jsonschema
    except ImportError:
        _validate_by_hand(payload)
        return
    try:
        jsonschema.validate(payload, verdict_schema())
    except jsonschema.ValidationError as e:
        where = "/".join(str(p) for p in e.absolute_path) or "(root)"
        raise VerdictError(f"{where}: {e.message}") from e


def load_verdicts(path: str | Path, *, expect_sha256: str | None = None) -> VerdictFile:
    """Read and validate one verdict file.

    Args:
        path: the verdict JSON a reviewer returned.
        expect_sha256: the draft's digest. When given, a mismatch raises rather
            than returning verdicts that describe a different extraction.
    """
    p = Path(path)
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise VerdictError(f"{p}: not valid JSON: {e}") from e

    validate_verdicts(payload)

    if expect_sha256 is not None and payload["draft_sha256"] != expect_sha256:
        raise VerdictError(
            f"{p}: verdicts are pinned to draft {payload['draft_sha256'][:12]} but the "
            f"draft given is {expect_sha256[:12]}. A verdict is only evidence about the "
            "extraction it was formed on; re-review the current draft rather than "
            "carrying these over."
        )

    seen: dict[str, dict[str, Any]] = {}
    for v in payload["verdicts"]:
        uid = v["unit_id"]
        if uid in seen:
            raise VerdictError(f"{p}: duplicate verdict for unit {uid!r}")
        seen[uid] = v

    return VerdictFile(
        path=p,
        draft_sha256=payload["draft_sha256"],
        mode=payload["mode"],
        reviewer=payload["reviewer"],
        paper_id=payload.get("paper_id"),
        verdicts=seen,
        notes=payload.get("notes"),
    )
