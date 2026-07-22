#!/usr/bin/env python
"""Retry the studies whose Q2 rerun failed, with a hard wall-clock cap so a stalled
Anthropic stream can't hang for hours. Each entry: (model, study, pmid, outdir).
Stale/failed outputs are quarantined first so a failed retry leaves NO file (eval then
treats the study as a genuine miss rather than scoring a stale one)."""
from __future__ import annotations

import concurrent.futures as cf
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA = HERE / "cmd.clean.linkml.yaml"
CAP_S = 1500  # 25 min per study; well above healthy runtimes, far below a 4h hang

RETRIES = [
    ("claude-sonnet-5", "TettAJ_2019_b", "31607556", "out"),
    ("claude-haiku-4-5", "LiJ_2017", "28143587", "out_haiku"),
    ("claude-haiku-4-5", "ContevilleLC_2019", "31417531", "out_haiku"),
]


def quarantine(outdir: str, study: str) -> None:
    q = HERE / outdir / ".stale_pre_q2"
    q.mkdir(parents=True, exist_ok=True)
    for p in (HERE / outdir).glob(f"{study}.*"):
        if p.is_file():
            shutil.move(str(p), str(q / p.name))


def run_one(model: str, study: str, pmid: str, outdir: str) -> tuple[str, str, str]:
    quarantine(outdir, study)
    od = HERE / outdir
    cmd = [
        "metaextract", "--paper-id", pmid, "--schema", str(SCHEMA), "--model", model,
        "--out", str(od / f"{study}.json"), "--csv", str(od / f"{study}.csv"),
        "--csv-provenance",
    ]
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=CAP_S)
        dt = time.time() - t0
        status = "ok" if proc.returncode == 0 and (od / f"{study}.json").exists() \
            else f"FAIL rc={proc.returncode}"
        tail = (proc.stderr.strip().splitlines() or ["<no stderr>"])[-1]
    except subprocess.TimeoutExpired:
        dt = time.time() - t0
        status, tail = f"TIMEOUT>{CAP_S}s", "killed (wall-clock cap)"
    (od / f"{study}.runlog.txt").write_text(
        f"cmd: {' '.join(cmd)}\nstatus: {status}\nelapsed_s: {dt:.1f}\n"
        f"--- stderr ---\n{locals().get('proc').stderr if 'proc' in locals() else ''}\n"
        if 'proc' in locals() else
        f"cmd: {' '.join(cmd)}\nstatus: {status}\nelapsed_s: {dt:.1f}\n(killed)\n"
    )
    return f"{model} {study}", status, f"{dt:.0f}s | {tail}"


def main() -> None:
    os.environ["ANTHROPIC_API_KEY"] = (
        Path.home() / "OmicsMLRepo/MetaHarmonizerEval/vignettes/keys/llm_baseline"
    ).read_text().strip()
    print(f"retrying {len(RETRIES)} studies (cap={CAP_S}s each), parallel\n", flush=True)
    with cf.ThreadPoolExecutor(max_workers=len(RETRIES)) as ex:
        futs = [ex.submit(run_one, *r) for r in RETRIES]
        for f in cf.as_completed(futs):
            label, status, detail = f.result()
            print(f"  {label}: {status} ({detail})", flush=True)
    print("\nRETRIES DONE", flush=True)


if __name__ == "__main__":
    main()
