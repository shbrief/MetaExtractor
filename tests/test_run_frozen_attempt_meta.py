"""run_frozen keeps each attempt's run metadata, so a failed attempt's usage survives its retry."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

BENCH = Path(__file__).resolve().parents[1] / "benchmarks" / "cmd_sonnet5"
sys.path.insert(0, str(BENCH))

import aggregate  # noqa: E402
import run_frozen  # noqa: E402


def _fake_run(outcomes):
    """subprocess.run stand-in: attempt i writes run-meta with outcomes[i] = (status, usd)."""
    calls = iter(outcomes)

    def run(cmd, **kw):
        status, usd = next(calls)
        meta = Path(cmd[cmd.index("--run-meta") + 1])
        meta.write_text(json.dumps({"status": status, "usage": {"n_calls": 4},
                                    "cost_estimate": {"total_usd": usd}}))
        if status == "ok":
            Path(cmd[cmd.index("--out") + 1]).write_text("{}")
        return SimpleNamespace(returncode=0 if status == "ok" else 2, stderr="")
    return run


def test_failed_attempt_meta_is_kept_and_costed(tmp_path, monkeypatch):
    monkeypatch.setattr(run_frozen.subprocess, "run", _fake_run([("failed", 0.07), ("ok", 0.20)]))
    args = SimpleNamespace(api_key=None, retries=1, cap=10)
    m = {"study": "S1", "pmid": "1"}
    msg = run_frozen._task(tmp_path, "haiku", 1, m, args, {"git": {"commit": "c", "dirty": False}})
    assert msg.endswith("ok (attempt 2)")

    run_dir = tmp_path / "haiku_r1"
    assert json.loads((run_dir / "S1.attempt1.meta.json").read_text())["status"] == "failed"
    assert json.loads((run_dir / "S1.attempt2.meta.json").read_text())["status"] == "ok"
    assert json.loads((run_dir / "S1.meta.json").read_text())["status"] == "ok"

    rows = run_frozen._ledger_rows(tmp_path)
    assert [r["attempt_meta"]["cost_usd"] for r in rows] == [0.07, 0.20]
    assert rows[0]["attempt_meta"]["sha256"] == run_frozen.sha256(run_dir / "S1.attempt1.meta.json")

    cost = aggregate.ledger_summary(tmp_path)["cost_all_attempts"]["haiku"]
    assert cost["attempts"] == 2 and cost["calls"] == 8
    assert round(cost["usd"], 2) == 0.27 and cost["usd_failed_attempts"] == 0.07


def test_attempt_without_meta_is_recorded_as_none(tmp_path):
    assert run_frozen._archive_attempt_meta(tmp_path / "S1.meta.json", 1) is None
