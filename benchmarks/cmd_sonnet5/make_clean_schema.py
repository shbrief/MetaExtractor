#!/usr/bin/env python
"""Build the benchmark's target schema ``cmd.clean.linkml.yaml`` from the cMD LinkML schema.

Two deterministic edits:

1. Downgrade ontology-reachable LinkML enums to plain string/list fields.
   MetaExtractor's LinkML adapter only expands enums with static
   ``permissible_values``; enums defined via ``reachable_from`` (dynamic ontology
   subtrees) have nothing to enumerate, so those slots become free text
   (``range: string``), treated as string (single) or list (multivalued).
2. Nothing else. The fan-out annotations (``scope``, ``propagate_study_value``,
   ``unit_of``) now come from the schema table itself — the ``scope``,
   ``propagate.study.value`` and ``unit.of`` columns of ``cmd_schema.csv``, emitted
   into ``--src`` by the registry's ``build_schema_artifacts.py`` — so they are no
   longer duplicated here. Scope drives deterministic fan-out only (it is not sent to
   the model): a ``sample``-scoped study-level value is propagated to samples only when
   it is a single, non-aggregate, non-heterogeneous value for a cohort reported without
   subgroups, and only for slots annotated ``propagate_study_value``; other
   sample-scoped slots are filled only from sample-level evidence.

  python make_clean_schema.py --src /path/to/cmd.linkml.yaml [OUT]

``--src`` defaults to ``$CMD_LINKML_SCHEMA``.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import yaml



def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?", default="cmd.clean.linkml.yaml")
    ap.add_argument("--src", default=os.environ.get("CMD_LINKML_SCHEMA"))
    args = ap.parse_args()
    if not args.src:
        raise SystemExit("pass --src or set CMD_LINKML_SCHEMA to the cMD cmd.linkml.yaml")
    data = yaml.safe_load(Path(args.src).read_text())
    enums = data.get("enums") or {}
    dynamic = {n for n, d in enums.items() if not (d or {}).get("permissible_values")}
    slots = data.get("slots") or {}
    changed = [sn for sn, sd in slots.items() if sd and sd.get("range") in dynamic]
    for sn in changed:
        slots[sn]["range"] = "string"
    ann = {sn: (sd or {}).get("annotations") or {} for sn, sd in slots.items()}
    scoped = sorted(sn for sn, a in ann.items() if a.get("scope"))
    Path(args.out).write_text(yaml.safe_dump(data, sort_keys=False))
    print(f"downgraded {len(changed)} slots (dynamic enums -> string): {changed}")
    print(f"scope from source on {len(scoped)} slots "
          f"(unannotated: {sorted(set(slots) - set(scoped))})")
    print(f"propagate_study_value: "
          f"{sorted(sn for sn, a in ann.items() if a.get('propagate_study_value'))}")
    print(f"unit_of: {({sn: a['unit_of'] for sn, a in ann.items() if a.get('unit_of')})}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
