#!/usr/bin/env python
"""Frozen multi-repeat cMD benchmark: one frozen retrieval per study, fresh
extractions, an append-only attempt ledger, and the scoring pipeline — all from one
committed code snapshot.

  fetch      retrieve each study ONCE into TREE/_fetch/<study>/ (text, tables, checksums)
  run        extract every (model, repeat, study) from those frozen retrievals
  harmonize  MetaHarmonizer crosswalks for the tree's extracted terms (TREE/crosswalks/)
  eval       bench.py eval on every run dir (post-harmonization scores)
  aggregate  aggregate.py on the tree
  verify     check ledger completeness and on-disk checksums

Every extraction of a study reads the same frozen retrieval, so repeats and models
differ only in the model calls, not in what the retrieval endpoints returned that
minute. Fetch attempts go to ``TREE/fetch_ledger.jsonl``; a retrieval without an
article body is retried (``--fetch-retries``) and, if it stays abstract-only,
recorded as such.

Guarantees of ``run``:

* refuses a dirty working tree (tracked files), a tree without a frozen retrieval
  for every study, and a tree that already holds extraction outputs, so no output is
  reused from an earlier pipeline version (``--resume`` only continues a tree whose
  ledger was written by the *same* commit);
* runs the repository's own ``src`` (``python -m metaextractor.cli``), mapping table
  columns with MetaHarmonizer SchemaMapper and the committed ``schemamapper/``
  dictionaries; refuses when MetaHarmonizer is missing or its checkout is modified;
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

from bench_paths import (AGE_RULES, HERE, MANIFEST, SCHEMA, SCHEMAMAPPER_DICTS,
                         SCHEMAMAPPER_STAGES, SRC, curation_dir, git_state, load_manifest, sha256)

MODELS = {"sonnet": "claude-sonnet-5", "haiku": "claude-haiku-4-5"}
FETCH_DIR = "_fetch"
# Entries a tree may hold before ``run`` (written by ``fetch``).
PRE_RUN_ENTRIES = {FETCH_DIR, "fetch_ledger.jsonl"}
OUTPUT_SUFFIXES = (".json", ".csv", ".text.txt", ".meta.json")
_LOCK = threading.Lock()


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _metaharmonizer_state() -> dict:
    """Installed MetaHarmonizer version and, for a source checkout, its commit and dirtiness."""
    try:
        import metaharmonizer
        from importlib.metadata import version
    except ImportError:
        return {"installed": False}
    root = Path(metaharmonizer.__file__).resolve().parent
    def _git(*a):
        try:
            return subprocess.run(["git", "-C", str(root), *a], capture_output=True, text=True,
                                  check=True).stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return ""
    return {"installed": True, "version": version("metaharmonizer"), "path": str(root),
            "commit": _git("rev-parse", "HEAD") or None,
            "dirty": bool(_git("status", "--porcelain", "--untracked-files=no", "--", "."))}


def _curation_commit() -> str:
    try:
        return subprocess.run(["git", "-C", str(curation_dir()), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def _ledger_rows(tree: Path, name: str = "ledger.jsonl") -> list[dict]:
    lp = tree / name
    if not lp.exists():
        return []
    return [json.loads(l) for l in lp.read_text().splitlines() if l.strip()]


def _append(tree: Path, row: dict, name: str = "ledger.jsonl") -> None:
    with _LOCK, (tree / name).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=str) + "\n")


def _paths(tree: Path, mkey: str, k: int, study: str) -> dict[str, Path]:
    d = tree / f"{mkey}_r{k}"
    return {"json": d / f"{study}.json", "csv": d / f"{study}.csv",
            "text": d / f"{study}.text.txt", "meta": d / f"{study}.meta.json"}


def _task(tree: Path, mkey: str, k: int, m: dict, args, static: dict) -> str:
    p = _paths(tree, mkey, k, m["study"])
    p["json"].parent.mkdir(parents=True, exist_ok=True)
    fetch_dir = tree / FETCH_DIR / m["study"]
    cmd = [sys.executable, "-m", "metaextractor.cli",
           "--paper-id", m["pmid"], "--schema", str(SCHEMA), "--model", MODELS[mkey],
           "--age-rules", str(AGE_RULES),
           "--fetch-cache", str(fetch_dir), "--require-fetch-cache",
           "--out", str(p["json"]), "--csv", str(p["csv"]), "--csv-provenance",
           "--save-text", str(p["text"]), "--run-meta", str(p["meta"]),
           "--column-mapper", "schemamapper", "--sm-target", str(SCHEMAMAPPER_DICTS["target"]),
           "--sm-alias", str(SCHEMAMAPPER_DICTS["alias"]),
           "--sm-values", str(SCHEMAMAPPER_DICTS["values"]),
           "--sm-stages", ",".join(map(str, SCHEMAMAPPER_STAGES or ()))]
    if args.api_key:
        cmd += ["--api-key", args.api_key]
    # SchemaMapper's embedding model is loaded from the local cache, never re-downloaded.
    env = {**os.environ, "PYTHONPATH": str(SRC), "HF_HUB_OFFLINE": "1"}
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
        attempt_meta = _archive_attempt_meta(p["meta"], attempt)
        log.write_text(f"cmd: {' '.join(c if not c.startswith('sk-') else '<key>' for c in cmd)}\n"
                       f"status: {status}\nreturncode: {rc}\nelapsed_s: {elapsed}\n"
                       f"--- stderr ---\n{stderr}\n", encoding="utf-8")
        _append(tree, {
            "model_key": mkey, "model": MODELS[mkey], "repeat": k, "study": m["study"],
            "pmid": m["pmid"], "attempt": attempt, "status": status, "returncode": rc,
            "start_utc": start, "end_utc": _utc(), "elapsed_s": elapsed,
            "log": str(log.relative_to(tree)), "stderr_tail": stderr[-2000:],
            "outputs_sha256": {k2: sha256(f) for k2, f in p.items()},
            "attempt_meta": attempt_meta,
            "frozen_retrieval": _fetch_checksums(fetch_dir),
            **static,
        })
        if status == "ok":
            break
    return f"{mkey}_r{k}/{m['study']}: {status} (attempt {attempt})"


def _archive_attempt_meta(meta: Path, attempt: int) -> dict | None:
    """Copy this attempt's ``<study>.meta.json`` to ``<study>.attempt<n>.meta.json``.

    The next attempt deletes ``<study>.meta.json`` before it starts, so without this copy
    the usage and cost of a failed attempt followed by a retry would be lost. Returns the
    copy's path, checksum, status, usage, and cost for the ledger (``None`` when the attempt
    wrote no metadata, e.g. it was killed at the wall-clock cap).
    """
    if not meta.exists():
        return None
    dst = meta.with_name(meta.name.replace(".meta.json", f".attempt{attempt}.meta.json"))
    dst.write_bytes(meta.read_bytes())
    d = json.loads(dst.read_text())
    return {"path": dst.name, "sha256": sha256(dst), "status": d.get("status"),
            "usage": d.get("usage"), "cost_usd": (d.get("cost_estimate") or {}).get("total_usd")}


def _fetch_checksums(fetch_dir: Path) -> dict | None:
    rec = fetch_dir / "fetched.json"
    if not rec.exists():
        return None
    r = json.loads(rec.read_text())
    return {"record_sha256": sha256(rec), "text_sha256": r.get("text_sha256"),
            "tables_sha256": r.get("tables_sha256")}


def cmd_fetch(args) -> None:
    from metaextractor.fetcher import FetchError, fetch_paper, save_fetched

    tree = _tree(args)
    gs = git_state()
    if gs["dirty"] and not args.allow_dirty:
        raise SystemExit("working tree has uncommitted changes to tracked files; commit first")
    manifest = load_manifest()
    if args.studies:
        manifest = [m for m in manifest if m["study"] in set(args.studies)]
    tree.mkdir(parents=True, exist_ok=True)
    for m in manifest:
        d = tree / FETCH_DIR / m["study"]
        if (d / "fetched.json").exists():
            print(f"{m['study']}: frozen retrieval exists, kept", flush=True)
            continue
        best = None
        for attempt in range(1, args.fetch_retries + 2):
            start, t0 = _utc(), time.time()
            row = {"study": m["study"], "pmid": m["pmid"], "attempt": attempt, "start_utc": start,
                   "git": gs}
            try:
                paper = fetch_paper(m["pmid"])
                status = "ok" if paper.has_body else "abstract_only"
                row.update(status=status, source=paper.source, has_body=paper.has_body,
                           rungs=paper.retrieval_attempts, n_tables=len(paper.supplementary_tables),
                           sra_manifest_source=paper.sra_manifest_source,
                           text_chars=len(paper.text))
                if best is None or (paper.has_body and not best.has_body):
                    best = paper
            except FetchError as e:
                status = "error"
                row.update(status=status, error=str(e))
            row.update(end_utc=_utc(), elapsed_s=round(time.time() - t0, 1))
            _append(tree, row, "fetch_ledger.jsonl")
            print(f"{m['study']}: attempt {attempt} {status}", flush=True)
            if status == "ok":
                break
            time.sleep(args.fetch_wait)
        if best is None:
            print(f"{m['study']}: NO retrieval; run will refuse this study", flush=True)
            continue
        rec = save_fetched(best, d)
        print(f"{m['study']}: froze {rec['source']} (body={rec['has_body']}, "
              f"{rec['n_tables']} tables, manifest={rec['sra_manifest_source']})", flush=True)


def cmd_run(args) -> None:
    tree = Path(args.out)
    if not tree.is_absolute():
        tree = HERE / tree
    gs = git_state()
    if gs["dirty"] and not args.allow_dirty:
        raise SystemExit("working tree has uncommitted changes to tracked files; commit first "
                         "(or --allow-dirty for a smoke test that is not the frozen run)")
    if not SCHEMAMAPPER_STAGES:
        raise SystemExit("bench_paths.SCHEMAMAPPER_STAGES is not set; decide the SchemaMapper stages "
                         "on the development studies and commit it before a frozen run")
    mh = _metaharmonizer_state()
    if not mh["installed"]:
        raise SystemExit("MetaHarmonizer is not installed; the table path maps columns with SchemaMapper")
    if mh.get("dirty") and not args.allow_dirty:
        raise SystemExit(f"MetaHarmonizer checkout {mh['path']} has uncommitted changes; commit first")
    existing = _ledger_rows(tree)
    if tree.exists() and any(p.name not in PRE_RUN_ENTRIES for p in tree.iterdir()):
        if not args.resume:
            raise SystemExit(f"{tree} already holds extraction outputs; the frozen run never "
                             f"reuses outputs (use --resume to continue a run from the same commit)")
        commits = {r["git"]["commit"] for r in existing}
        if commits and commits != {gs["commit"]}:
            raise SystemExit(f"--resume refused: ledger commits {commits} != HEAD {gs['commit']}")
    tree.mkdir(parents=True, exist_ok=True)
    done = {(r["model_key"], r["repeat"], r["study"]) for r in existing if r["status"] == "ok"}

    manifest = load_manifest()
    if args.studies:
        manifest = [m for m in manifest if m["study"] in set(args.studies)]
    missing = [m["study"] for m in manifest
               if not (tree / FETCH_DIR / m["study"] / "fetched.json").exists()]
    if missing:
        raise SystemExit(f"no frozen retrieval for {missing}; run `run_frozen.py fetch` first")
    static = {
        "git": gs,
        "schema_sha256": sha256(SCHEMA), "manifest_sha256": sha256(MANIFEST),
        "age_rules_sha256": sha256(AGE_RULES), "curation_commit": _curation_commit(),
        "schemamapper_dicts_sha256": {k: sha256(v) for k, v in SCHEMAMAPPER_DICTS.items()},
        "schemamapper_stages": list(SCHEMAMAPPER_STAGES),
        "metaharmonizer": _metaharmonizer_state(),
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
    """Needs MetaHarmonizer and the field corpora (see harmonize/regen_crosswalks.py)."""
    subprocess.run([sys.executable, str(HERE / "harmonize" / "regen_crosswalks.py"),
                    "--tree", str(_tree(args))], check=True)


def cmd_aggregate(args) -> None:
    subprocess.run([sys.executable, str(HERE / "aggregate.py"), str(_tree(args))], check=True)


def cmd_verify(args) -> None:
    from metaextractor.fetcher import FetchError, load_fetched

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
    for r in rows:
        am = r.get("attempt_meta")
        if am and sha256(tree / f"{r['model_key']}_r{r['repeat']}" / am["path"]) != am["sha256"]:
            problems.append(f"{r['model_key']}_r{r['repeat']}/{am['path']}: checksum mismatch or missing")
    for fr in sorted((tree / FETCH_DIR).glob("*/fetched.json")):
        try:
            load_fetched(fr.parent)
        except FetchError as e:
            problems.append(f"frozen retrieval {fr.parent.name}: {e}")
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
    f = sub.add_parser("fetch")
    f.add_argument("--out", default="out_v2")
    f.add_argument("--studies", nargs="+", default=None)
    f.add_argument("--fetch-retries", type=int, default=2,
                   help="re-fetches when the retrieval has no article body")
    f.add_argument("--fetch-wait", type=float, default=30.0, help="seconds between fetch attempts")
    f.add_argument("--allow-dirty", action="store_true")
    for name in ("eval", "harmonize", "aggregate", "verify"):
        s = sub.add_parser(name)
        s.add_argument("--out", default="out_v2")
    args = ap.parse_args()
    {"fetch": cmd_fetch, "run": cmd_run, "eval": cmd_eval, "harmonize": cmd_harmonize,
     "aggregate": cmd_aggregate, "verify": cmd_verify}[args.cmd](args)


if __name__ == "__main__":
    main()
