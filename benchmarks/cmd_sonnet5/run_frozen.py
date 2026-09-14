#!/usr/bin/env python
"""Frozen multi-repeat cMD benchmark: fresh extractions, an append-only attempt
ledger, and the scoring pipeline — all from one committed code snapshot.

  run        extract every (model, repeat, study) into an EMPTY output tree
  eval       bench.py eval on every run dir
  harmonize  bench.py harmonize on the tree
  aggregate  aggregate.py on the tree
  verify     check ledger completeness and on-disk checksums

Guarantees of ``run``:

* refuses a dirty working tree (tracked files) and a non-empty output tree, so
  no output is reused from an earlier pipeline version (``--resume`` only
  continues a tree whose ledger was written by the *same* commit);
* runs the repository's own ``src`` (``python -m metaextractor.cli``);
* every attempt — failures included — is appended to ``TREE/ledger.jsonl`` with
  UTC times, status, its own stderr log, the git commit, checksums of the schema,
  manifest, and age rules, and checksums of every output file;
* one retry per task after a failed attempt (``--retries``), with a hard
  wall-clock cap per attempt.

  CMD_CURATION_DIR=... python run_frozen.py run --out out_v2 --api-key file:~/key
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import platform
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from bench_paths import (AGE_RULES, HERE, MANIFEST, SCHEMA, SRC, curation_dir, git_state,
                         load_manifest, sha256)

MODELS = {"sonnet": "claude-sonnet-5", "haiku": "claude-haiku-4-5"}
OUTPUT_SUFFIXES = (".json", ".csv", ".text.txt", ".meta.json")
_LOCK = threading.Lock()


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _curation_commit() -> str:
    try:
        return subprocess.run(["git", "-C", str(curation_dir()), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def _ledger_rows(tree: Path) -> list[dict]:
    lp = tree / "ledger.jsonl"
    if not lp.exists():
        return []
    return [json.loads(l) for l in lp.read_text().splitlines() if l.strip()]


def _append(tree: Path, row: dict) -> None:
    with _LOCK, (tree / "ledger.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


def _paths(tree: Path, mkey: str, k: int, study: str) -> dict[str, Path]:
    d = tree / f"{mkey}_r{k}"
    return {"json": d / f"{study}.json", "csv": d / f"{study}.csv",
            "text": d / f"{study}.text.txt", "meta": d / f"{study}.meta.json"}


def _task(tree: Path, mkey: str, k: int, m: dict, args, static: dict) -> str:
    p = _paths(tree, mkey, k, m["study"])
    p["json"].parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "metaextractor.cli",
           "--paper-id", m["pmid"], "--schema", str(SCHEMA), "--model", MODELS[mkey],
           "--age-rules", str(AGE_RULES),
           "--out", str(p["json"]), "--csv", str(p["csv"]), "--csv-provenance",
           "--save-text", str(p["text"]), "--run-meta", str(p["meta"])]
    if args.api_key:
        cmd += ["--api-key", args.api_key]
    env = {**os.environ, "PYTHONPATH": str(SRC)}
    status = "not_run"
    for attempt in range(1, args.retries + 2):
        for f in p.values():
            f.unlink(missing_ok=True)
        log = p["json"].parent / f"{m['study']}.attempt{attempt}.log"
        start, t0 = _utc(), time.time()
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=args.cap)
            rc, stderr = proc.returncode, proc.stderr
            status = "ok" if rc == 0 and p["json"].exists() else f"fail_rc{rc}"
        except subprocess.TimeoutExpired as e:
            rc = None
            stderr = (e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or ""))
            status = f"timeout_{args.cap}s"
        elapsed = round(time.time() - t0, 1)
        log.write_text(f"cmd: {' '.join(c if not c.startswith('sk-') else '<key>' for c in cmd)}\n"
                       f"status: {status}\nreturncode: {rc}\nelapsed_s: {elapsed}\n"
                       f"--- stderr ---\n{stderr}\n", encoding="utf-8")
        _append(tree, {
            "model_key": mkey, "model": MODELS[mkey], "repeat": k, "study": m["study"],
            "pmid": m["pmid"], "attempt": attempt, "status": status, "returncode": rc,
            "start_utc": start, "end_utc": _utc(), "elapsed_s": elapsed,
            "log": str(log.relative_to(tree)), "stderr_tail": stderr[-2000:],
            "outputs_sha256": {k2: sha256(f) for k2, f in p.items()},
            **static,
        })
        if status == "ok":
            break
    return f"{mkey}_r{k}/{m['study']}: {status} (attempt {attempt})"


def cmd_run(args) -> None:
    tree = Path(args.out)
    if not tree.is_absolute():
        tree = HERE / tree
    gs = git_state()
    if gs["dirty"] and not args.allow_dirty:
        raise SystemExit("working tree has uncommitted changes to tracked files; commit first "
                         "(or --allow-dirty for a smoke test that is not the frozen run)")
    existing = _ledger_rows(tree)
    if tree.exists() and any(tree.iterdir()):
        if not args.resume:
            raise SystemExit(f"{tree} is not empty; the frozen run never reuses outputs "
                             f"(use --resume to continue a run from the same commit)")
        commits = {r["git"]["commit"] for r in existing}
        if commits and commits != {gs["commit"]}:
            raise SystemExit(f"--resume refused: ledger commits {commits} != HEAD {gs['commit']}")
    tree.mkdir(parents=True, exist_ok=True)
    done = {(r["model_key"], r["repeat"], r["study"]) for r in existing if r["status"] == "ok"}

    manifest = load_manifest()
    if args.studies:
        manifest = [m for m in manifest if m["study"] in set(args.studies)]
    static = {
        "git": gs,
        "schema_sha256": sha256(SCHEMA), "manifest_sha256": sha256(MANIFEST),
        "age_rules_sha256": sha256(AGE_RULES), "curation_commit": _curation_commit(),
        "api_key_source": (args.api_key.split(":", 1)[0] if args.api_key and ":" in args.api_key
                           else ("literal" if args.api_key else "env")),
        "python": platform.python_version(), "platform": platform.platform(),
        "cap_s": args.cap, "max_retries": args.retries,
    }
    tasks = [(mk, k, m) for k in range(1, args.repeats + 1) for m in manifest
             for mk in args.models if (mk, k, m["study"]) not in done]
    run_info = {"started_utc": _utc(), "tasks": len(tasks), "workers": args.workers,
                "models": {mk: MODELS[mk] for mk in args.models}, "repeats": args.repeats,
                "studies": [m["study"] for m in manifest], **static}
    with _LOCK, (tree / "runs.jsonl").open("a") as fh:
        fh.write(json.dumps(run_info) + "\n")
    print(f"frozen run: {len(tasks)} task(s), workers={args.workers}, commit {gs['commit'][:10]}",
          flush=True)
    n = 0
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(_task, tree, mk, k, m, args, static) for mk, k, m in tasks]
        for f in cf.as_completed(futs):
            n += 1
            print(f"[{n}/{len(tasks)}] {f.result()}", flush=True)
    print("FROZEN RUN DONE", flush=True)


def _tree(args) -> Path:
    t = Path(args.out)
    return t if t.is_absolute() else HERE / t


def cmd_eval(args) -> None:
    for d in sorted(_tree(args).glob("*_r*")):
        if d.is_dir():
            subprocess.run([sys.executable, str(HERE / "bench.py"), "eval", str(d)], check=True)


def cmd_harmonize(args) -> None:
    subprocess.run([sys.executable, str(HERE / "bench.py"), "harmonize", str(_tree(args))],
                   check=True)


def cmd_aggregate(args) -> None:
    subprocess.run([sys.executable, str(HERE / "aggregate.py"), str(_tree(args))], check=True)


def cmd_verify(args) -> None:
    tree = _tree(args)
    rows = _ledger_rows(tree)
    last: dict[tuple, dict] = {}
    for r in rows:
        last[(r["model_key"], r["repeat"], r["study"])] = r
    problems = []
    for key, r in sorted(last.items()):
        if r["status"] != "ok":
            problems.append(f"{key}: final status {r['status']}")
            continue
        for kind, digest in r["outputs_sha256"].items():
            f = _paths(tree, *key)[kind]
            if digest is None or sha256(f) != digest:
                problems.append(f"{key}: {kind} checksum mismatch or missing")
    commits = {r["git"]["commit"] for r in rows}
    dirty = any(r["git"]["dirty"] for r in rows)
    print(f"tasks {len(last)}, attempts {len(rows)}, commits {sorted(commits)}, dirty {dirty}")
    for p in problems:
        print("PROBLEM:", p)
    if problems or len(commits) != 1 or dirty:
        raise SystemExit(1)
    print("VERIFIED")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--out", default="out_v2")
    r.add_argument("--models", nargs="+", default=list(MODELS), choices=list(MODELS))
    r.add_argument("--repeats", type=int, default=3)
    r.add_argument("--studies", nargs="+", default=None)
    r.add_argument("--workers", type=int, default=4)
    r.add_argument("--cap", type=int, default=1500, help="wall-clock seconds per attempt")
    r.add_argument("--retries", type=int, default=1)
    r.add_argument("--api-key", default=None,
                   help="literal key, env:VAR, or file:PATH (default: ANTHROPIC_API_KEY)")
    r.add_argument("--resume", action="store_true")
    r.add_argument("--allow-dirty", action="store_true")
    for name in ("eval", "harmonize", "aggregate", "verify"):
        s = sub.add_parser(name)
        s.add_argument("--out", default="out_v2")
    args = ap.parse_args()
    {"run": cmd_run, "eval": cmd_eval, "harmonize": cmd_harmonize,
     "aggregate": cmd_aggregate, "verify": cmd_verify}[args.cmd](args)


if __name__ == "__main__":
    main()
