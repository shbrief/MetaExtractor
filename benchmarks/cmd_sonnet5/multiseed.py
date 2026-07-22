#!/usr/bin/env python
"""Multi-seed benchmark: run each study N times per model to quantify run-to-run
variance, with a hard wall-clock cap per extraction so a stalled Anthropic stream
can't hang for hours. Runs the *fixed* fetcher (Europe PMC fallback is now strictly
additive: supplementary tables are recovered via S3 even when the body came from
Europe PMC), so the remaining spread is genuine LLM / pipeline variance.

Layout:  out_ms/<modelkey>_r<k>/<study>.json (+ .csv, .runlog.txt)
Resumable: an existing <study>.json is skipped unless --force.

  python multiseed.py run   [--force] [--workers 6]
  python multiseed.py eval                      # eval every run dir
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA = HERE / "cmd.clean.linkml.yaml"
MS = HERE / "out_ms"
MODELS = {"sonnet": "claude-sonnet-5", "haiku": "claude-haiku-4-5"}
RUNS = 3
CAP_S = 1500  # 25 min; healthy runs are <800s, a stall gets killed well short of hours


def _manifest() -> list[dict]:
    return json.loads((HERE / "manifest.json").read_text())


def _tasks() -> list[tuple[str, str, int, dict]]:
    out = []
    for mkey, model in MODELS.items():
        for k in range(1, RUNS + 1):
            for m in _manifest():
                out.append((mkey, model, k, m))
    return out


def _one(mkey: str, model: str, k: int, m: dict, force: bool) -> str:
    study, pmid = m["study"], m["pmid"]
    od = MS / f"{mkey}_r{k}"
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
    src = ""
    for line in stderr.splitlines():
        if "fetched" in line:
            src = line.strip(); break
    return f"{mkey}_r{k}/{study}: {status} in {dt:.0f}s | {src}"


def cmd_run(args) -> None:
    os.environ["ANTHROPIC_API_KEY"] = (
        Path.home() / "OmicsMLRepo/MetaHarmonizerEval/vignettes/keys/llm_baseline"
    ).read_text().strip()
    tasks = _tasks()
    print(f"multiseed: {len(tasks)} extractions "
          f"({len(MODELS)} models x {RUNS} runs x {len(_manifest())} studies), "
          f"workers={args.workers}, cap={CAP_S}s\n", flush=True)
    done = 0
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(_one, *t, args.force) for t in tasks]
        for f in cf.as_completed(futs):
            done += 1
            print(f"[{done}/{len(tasks)}] {f.result()}", flush=True)
    print("\nMULTISEED RUN DONE", flush=True)


def cmd_eval(args) -> None:
    import subprocess as sp
    for mkey in MODELS:
        for k in range(1, RUNS + 1):
            od = MS / f"{mkey}_r{k}"
            if not od.exists():
                continue
            sp.run([sys.executable, str(HERE / "bench.py"), "eval",
                    str(HERE / "manifest.json"), str(od)], check=False)
    print("MULTISEED EVAL DONE", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("--force", action="store_true")
    r.add_argument("--workers", type=int, default=6)
    sub.add_parser("eval")
    args = ap.parse_args()
    {"run": cmd_run, "eval": cmd_eval}[args.cmd](args)


if __name__ == "__main__":
    main()
