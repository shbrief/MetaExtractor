"""Portable paths and manifest helpers shared by the cMD benchmark scripts.

Nothing here assumes a personal directory layout:

* the MetaExtractor package is imported from this repository's ``src/``;
* the target schema is the committed ``cmd.clean.linkml.yaml``;
* gold tables are resolved against ``$CMD_CURATION_DIR`` — a checkout of
  ``waldronlab/curatedMetagenomicDataCuration`` — using the repository-relative
  ``gold_rel`` path recorded in ``manifest.json``.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SRC = REPO / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

SCHEMA = HERE / "cmd.clean.linkml.yaml"
MANIFEST = HERE / "manifest.json"
AGE_RULES = HERE / "age_rules_cmd.json"
#: MetaHarmonizer SchemaMapper dictionaries for the cMD schema (copied from the registry);
#: used by the harmonization step, not by extraction.
SCHEMAMAPPER_DICTS = {
    "target": HERE / "schemamapper" / "cmd_target_attrs.csv",
    "alias": HERE / "schemamapper" / "cmd_target_attrs_alias_haiku.csv",
    "values": HERE / "schemamapper" / "cmd_target_attrs_allowed_values.json",
}
ORDER_KEY = "study"


def curation_dir() -> Path:
    """Root of the curatedMetagenomicDataCuration checkout (``$CMD_CURATION_DIR``)."""
    v = os.environ.get("CMD_CURATION_DIR")
    if not v:
        raise SystemExit(
            "Set CMD_CURATION_DIR to a checkout of "
            "https://github.com/waldronlab/curatedMetagenomicDataCuration"
        )
    return Path(v).expanduser()


def load_manifest(path: Path | str = MANIFEST, limit: int | None = None) -> list[dict]:
    m = json.loads(Path(path).read_text())
    return m[:limit] if limit else m


def gold_path(entry: dict) -> Path:
    """Resolve a manifest entry's gold ``*_sample.tsv``."""
    if entry.get("gold_rel"):
        return curation_dir() / entry["gold_rel"]
    return Path(entry["gold_tsv"])  # legacy absolute path


def schema_fields() -> list[str]:
    """Target-schema field names, from the committed clean LinkML schema."""
    from metaextractor.schema_loader import load_schema_file
    return [f.name for f in load_schema_file(SCHEMA).fields]


def sha256(path: Path | str) -> str | None:
    p = Path(path)
    if not p.exists():
        return None
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_state() -> dict:
    """Commit, tag(s) pointing at HEAD, and whether tracked files are modified."""
    def _git(*args: str) -> str:
        try:
            return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True,
                                  text=True, check=True).stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return ""
    return {
        "commit": _git("rev-parse", "HEAD"),
        "tags": [t for t in _git("tag", "--points-at", "HEAD").splitlines() if t],
        "dirty": bool(_git("status", "--porcelain", "--untracked-files=no")),
    }
