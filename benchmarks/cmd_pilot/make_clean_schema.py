#!/usr/bin/env python
"""Downgrade ontology-reachable LinkML enums to plain string/list fields.

MetaExtractor's LinkML adapter only expands enums with static
`permissible_values`; enums defined via `reachable_from` (dynamic ontology
subtrees) resolve to empty allowed_values and crash schema loading. Papers
can't be extracted against an un-enumerated ontology anyway, so we convert
those slots to free-text (`range: string`), which the adapter then treats as
string (single) or list (multivalued).
"""
from __future__ import annotations
import sys
from pathlib import Path
import yaml

SRC = Path.home() / "OmicsMLRepo/MetaHarmonizerSchemaRegistry/schema/curatedmetagenomicdata/cmd.linkml.yaml"

def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("cmd.clean.linkml.yaml")
    data = yaml.safe_load(SRC.read_text())
    enums = data.get("enums") or {}
    dynamic = {n for n, d in enums.items() if not (d or {}).get("permissible_values")}
    slots = data.get("slots") or {}
    changed = [sn for sn, sd in slots.items() if sd and sd.get("range") in dynamic]
    for sn in changed:
        slots[sn]["range"] = "string"
    out.write_text(yaml.safe_dump(data, sort_keys=False))
    print(f"downgraded {len(changed)} slots (dynamic enums -> string): {changed}")
    print(f"wrote {out}")

if __name__ == "__main__":
    main()
