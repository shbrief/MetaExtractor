#!/usr/bin/env python
"""Reproducibly select N random cMD studies and build an extraction manifest.

For each selected study we read the *_sample.tsv gold table and pull, by
HEADER NAME (column order varies across studies):
  - pmid          -> drives extraction (metaextract --paper-id)
  - sample_id     -> BioSample IDs, used as the audit key in evaluation
We keep only studies with a single clean numeric PMID and >=1 sample.
"""
from __future__ import annotations

import csv
import json
import random
import sys
from pathlib import Path

CURATED = Path.home() / "Projects/cMD_architecture/curatedMetagenomicDataCuration/inst/curated"
SEED = 42
N_TOTAL = 20

def read_tsv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="") as fh:
        r = csv.DictReader(fh, delimiter="\t")
        rows = list(r)
        return (r.fieldnames or []), rows

def clean_pmid(rows: list[dict[str, str]]) -> str | None:
    vals = {(row.get("pmid") or "").strip() for row in rows}
    vals = {v for v in vals if v and v.lower() not in {"na", "nan", "null"}}
    # normalise "34618582" / "34618582.0"
    norm = set()
    for v in vals:
        try:
            norm.add(str(int(float(v))))
        except ValueError:
            norm.add(v)
    if len(norm) == 1:
        pmid = next(iter(norm))
        return pmid if pmid.isdigit() else None
    return None  # zero, or ambiguous multi-PMID studies -> skip

def main() -> None:
    tsvs = sorted(CURATED.glob("*/*_sample.tsv"))
    print(f"found {len(tsvs)} *_sample.tsv studies", file=sys.stderr)

    rng = random.Random(SEED)
    rng.shuffle(tsvs)

    manifest: list[dict] = []
    skipped: list[tuple[str, str]] = []
    for path in tsvs:
        study = path.parent.name
        header, rows = read_tsv(path)
        if "pmid" not in header:
            skipped.append((study, "no pmid column")); continue
        if "sample_id" not in header:
            skipped.append((study, "no sample_id column")); continue
        pmid = clean_pmid(rows)
        if not pmid:
            skipped.append((study, "no single clean pmid")); continue
        sample_ids = [(row.get("sample_id") or "").strip() for row in rows]
        sample_ids = [s for s in sample_ids if s]
        if not sample_ids:
            skipped.append((study, "no sample ids")); continue
        manifest.append({
            "study": study,
            "pmid": pmid,
            "n_samples": len(sample_ids),
            "gold_tsv": str(path),
            "sample_ids_head": sample_ids[:3],
        })
        if len(manifest) >= N_TOTAL:
            break

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("manifest.json")
    out.write_text(json.dumps(manifest, indent=2))
    print(f"\nselected {len(manifest)} studies (seed={SEED}) -> {out}", file=sys.stderr)
    for i, m in enumerate(manifest):
        tag = "PILOT" if i < 5 else "     "
        print(f"  {tag} {i+1:>2}. {m['study']:<28} pmid={m['pmid']:<10} n_samples={m['n_samples']}", file=sys.stderr)
    if skipped:
        print(f"\nskipped {len(skipped)} while drawing (showing first 10):", file=sys.stderr)
        for s, why in skipped[:10]:
            print(f"    - {s}: {why}", file=sys.stderr)

if __name__ == "__main__":
    main()
