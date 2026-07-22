#!/usr/bin/env python
"""Run SchemaMapper (target = cMD) over the free-text keys the extractor dumped
into `uncurated_metadata`, to see how many map back to a real cMD field.

Input: one CSV whose COLUMN HEADERS are the unique uncurated_metadata strings
(SchemaMapper maps column names -> schema fields). Output: the Stage-3 mapping
CSV plus a short summary of recovery rate.
"""
from __future__ import annotations
import json, os, pathlib, re
import pandas as pd

HERE = pathlib.Path(__file__).resolve().parent
BENCH = HERE.parent
REG = pathlib.Path.home() / "OmicsMLRepo/MetaHarmonizerSchemaRegistry/schema/curatedmetagenomicdata"
SCHEMA = REG / "cmd_target_attrs.csv"
ALIAS = REG / "cmd_target_attrs_alias_haiku.csv"

os.environ.setdefault("SM_OUTPUT_DIR", str(HERE / "sm_out"))
(HERE / "sm_out").mkdir(exist_ok=True)


def sanitize(s: str) -> str:
    s = re.sub(r"\s+", " ", str(s)).strip()
    return s[:80]


def main():
    MANI = json.loads((BENCH / "manifest.json").read_text())
    keys: list[str] = []
    for outdir in ("out", "out_haiku"):
        for m in MANI:
            p = BENCH / outdir / f"{m['study']}.json"
            if not p.exists():
                continue
            d = json.loads(p.read_text())
            for c in [d.get("fields") or {}] + list(d.get("samples") or []):
                v = c.get("uncurated_metadata")
                if isinstance(v, dict):
                    v = v.get("value")
                if isinstance(v, list):
                    keys += [str(x) for x in v]
                elif v:
                    keys.append(str(v))
    # unique, drop not_reported, sanitize + dedupe headers
    seen, cols = set(), []
    for k in keys:
        if str(k).strip().lower() in ("not_reported", "na", "nan", ""):
            continue
        h = sanitize(k)
        base, i = h, 1
        while h in seen:
            i += 1
            h = f"{base} #{i}"
        seen.add(h)
        cols.append(h)
    inp = HERE / "sm_input_uncurated.csv"
    pd.DataFrame([["" for _ in cols]], columns=cols).to_csv(inp, index=False)
    print(f"built SchemaMapper input: {len(cols)} candidate columns -> {inp}")

    from metaharmonizer import SchemaMapEngine
    eng = SchemaMapEngine(
        input_path=str(inp),
        target_schema_path=str(SCHEMA),
        alias_dict_path=str(ALIAS),
        top_k=3,
    )
    res = eng.run_schema_mapping()
    out = HERE / "sm_uncurated_mapping.csv"
    res.to_csv(out, index=False)
    print(f"wrote {out}  ({len(res)} rows)")
    # recovery summary
    if "match1_score" in res.columns:
        strong = res[pd.to_numeric(res["match1_score"], errors="coerce") >= 0.80]
        print(f"strong matches (match1_score>=0.80): {len(strong)}/{len(res)}")
        print(strong[["query", "match1", "match1_score"]].head(25).to_string(index=False))


if __name__ == "__main__":
    main()
