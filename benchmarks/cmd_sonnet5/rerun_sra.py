#!/usr/bin/env python
"""Targeted re-run for the refined pipeline (auto SRA/ENA run-manifest fetch).

The manifest fetch is a default pipeline capability now, so it can change any
study whose data-availability accession resolves — not a fixed subset. We
therefore:
  1. seed a refined output tree from the existing out_ms/ (unchanged studies
     keep their results), then
  2. re-run only the studies passed in --studies, 2 models x 3 repeats, with
     --force, overwriting them in the refined tree.

Then `eval` + aggregate.py --dir out_ms_refined give a consistent refined
snapshot. Same CLI, schema, and scoring as multiseed.py — only the pipeline
default changed.

  python rerun_sra.py run  --studies A B C [--workers 4] [--force]
  python rerun_sra.py eval --studies A B C
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA = HERE / "cmd.clean.linkml.yaml"
SRC = HERE / "out_ms"
DST = HERE / "out_ms_refined"
MODELS = {"sonnet": "claude-sonnet-5", "haiku": "claude-haiku-4-5"}
RUNS = 3
CAP_S = 1500
KEY = Path.home() / "OmicsMLRepo/MetaHarmonizerEval/vignettes/keys/llm_baseline"


def _manifest() -> list[dict]:
    return json.loads((HERE / "manifest.json").read_text())


def _seed_refined() -> None:
    """Copy out_ms/ -> out_ms_refined/ once, so unchanged studies keep results."""
    if DST.exists():
        return
    shutil.copytree(SRC, DST)
    print(f"seeded {DST.name} from {SRC.name}", flush=True)


def _one(mkey: str, model: str, k: int, m: dict, force: bool) -> str:
    study, pmid = m["study"], m["pmid"]
    od = DST / f"{mkey}_r{k}"
    od.mkdir(parents=True, exist_ok=True)
    out_json = od / f"{study}.json"
    if out_json.exists() and not force:
        return f"{mkey}_r{k}/{study}: skip (exists)"
    cmd = [
        "metaextract", "--paper-id", pmid, "--schema", str(SCHEMA), "--model", model,
        "--out", str(out_json), "--csv", str(od / f"{study}.csv"), "--csv-provenance",
    ]
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=CAP_S)
        dt = time.time() - t0
        ok = proc.returncode == 0 and out_json.exists()
        status = "ok" if ok else f"FAIL rc={proc.returncode}"
        stderr = proc.stderr
    except subprocess.TimeoutExpired:
        dt = time.time() - t0
        status, stderr = f"TIMEOUT>{CAP_S}s", "(killed: wall-clock cap)"
    (od / f"{study}.runlog.txt").write_text(
        f"cmd: {' '.join(cmd)}\nstatus: {status}\nelapsed_s: {dt:.1f}\n"
        f"--- stderr ---\n{stderr}\n"
    )
    manifest_line = next(
        (l.strip() for l in stderr.splitlines() if "SRA/ENA run manifest" in l), "")
    return f"{mkey}_r{k}/{study}: {status} in {dt:.0f}s | {manifest_line}"


def cmd_run(args) -> None:
    os.environ["ANTHROPIC_API_KEY"] = KEY.read_text().strip()
    _seed_refined()
    wanted = set(args.studies)
    studies = [m for m in _manifest() if m["study"] in wanted]
    missing = wanted - {m["study"] for m in studies}
    if missing:
        sys.exit(f"unknown studies: {sorted(missing)}")
    tasks = [(mk, mdl, k, m) for mk, mdl in MODELS.items()
             for k in range(1, RUNS + 1) for m in studies]
    print(f"rerun_sra: {len(tasks)} extractions "
          f"({len(MODELS)} models x {RUNS} runs x {len(studies)} studies), "
          f"workers={args.workers}\n", flush=True)
    done = 0
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(_one, *t, args.force) for t in tasks]
        for f in cf.as_completed(futs):
            done += 1
            print(f"[{done}/{len(tasks)}] {f.result()}", flush=True)
    print("\nRERUN DONE", flush=True)


def cmd_eval(args) -> None:
    for mkey in MODELS:
        for k in range(1, RUNS + 1):
            od = DST / f"{mkey}_r{k}"
            if not od.exists():
                continue
            subprocess.run([sys.executable, str(HERE / "bench.py"), "eval",
                            str(HERE / "manifest.json"), str(od)], check=False)
    print("EVAL DONE", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--studies", nargs="+", required=True)
    r.add_argument("--force", action="store_true")
    r.add_argument("--workers", type=int, default=4)
    e = sub.add_parser("eval")
    e.add_argument("--studies", nargs="*", default=[])
    args = ap.parse_args()
    {"run": cmd_run, "eval": cmd_eval}[args.cmd](args)


if __name__ == "__main__":
    main()
