"""``metaextract-review`` — build review packets, ingest verdicts, report.

A separate console script rather than subcommands on ``metaextract``:
``benchmarks/cmd_sonnet5/run_frozen.py`` shells out to that CLI and its flag
surface is load-bearing for every frozen run, so it is left alone.

    metaextract-review packet  RESULT.json [-o packet.html] [--paper TEXT]
    metaextract-review ingest  VERDICT.json ... --draft RESULT.json
    metaextract-review report  VERDICT.json ... [--draft RESULT.json]
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

from metaextractor.output import ExtractionResult
from metaextractor.review.packet import PacketMeta, build_packet, draft_sha256
from metaextractor.review.report import aggregate_verdicts
from metaextractor.review.verdicts import VerdictError, load_verdicts


def _load_result(path: Path) -> ExtractionResult:
    try:
        return ExtractionResult.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as e:  # pydantic ValidationError, JSON errors, OSError
        raise SystemExit(f"{path}: not a readable ExtractionResult: {e}") from e


def _source_links(paper_id: str | None) -> dict[str, str]:
    """Links a reviewer can follow to read the published source.

    Adjudicating against the *paper* rather than against the frozen retrieval is
    ``evaluation/extensions/PLAN.md`` decision 3(a): otherwise a false negative
    for a value in an unfetched supplement is confounded with retrieval coverage.
    """
    if not paper_id:
        return {}
    pid = paper_id.strip()
    bare = pid.split(":", 1)[1] if ":" in pid else pid
    links: dict[str, str] = {}
    if bare.upper().startswith("PMC"):
        links["PMC"] = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{bare}/"
    elif bare.isdigit():
        links["PubMed"] = f"https://pubmed.ncbi.nlm.nih.gov/{bare}/"
        links["PMC"] = f"https://www.ncbi.nlm.nih.gov/pmc/?term={bare}"
    elif bare.startswith("10."):
        links["DOI"] = f"https://doi.org/{bare}"
    return links


def _cmd_packet(args: argparse.Namespace) -> int:
    result = _load_result(args.result)
    paper_text = args.paper.read_text(encoding="utf-8") if args.paper else None

    cells = None
    if args.cells:
        rows = json.loads(args.cells.read_text(encoding="utf-8"))
        cells = rows["cells"] if isinstance(rows, dict) else rows

    meta = PacketMeta(
        paper_id=result.paper_id,
        study=args.study or (args.result.stem if args.result else None),
        model=args.model,
        generated_utc=_dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        source_links=_source_links(result.paper_id),
        notes=args.note,
    )
    html = build_packet(result, meta=meta, paper_text=paper_text, cells=cells)

    out = args.out or args.result.with_suffix(".review.html")
    out.write_text(html, encoding="utf-8")
    sha = draft_sha256(result)
    n_units = html.count('data-unit="')
    print(f"wrote {out}  ({len(html):,} bytes, {n_units} units, "
          f"draft {sha[:12]}, mode {'adjudication' if cells is not None else 'draft'})")
    if paper_text is None:
        print("[note: no --paper, so evidence quotes are shown without a verbatim check]",
              file=sys.stderr)
    return 0


def _cmd_ingest(args: argparse.Namespace) -> int:
    expect = draft_sha256(_load_result(args.draft)) if args.draft else None
    ok, bad = 0, 0
    for p in args.verdicts:
        try:
            vf = load_verdicts(p, expect_sha256=expect)
        except VerdictError as e:
            print(f"REJECTED {p}: {e}", file=sys.stderr)
            bad += 1
            continue
        ok += 1
        print(f"accepted {p}: reviewer={vf.reviewer} mode={vf.mode} "
              f"units={vf.judged} draft={vf.draft_sha256[:12]}")
    if bad:
        print(f"\n{ok} accepted, {bad} rejected", file=sys.stderr)
    return 1 if bad else 0


def _cmd_report(args: argparse.Namespace) -> int:
    expect = None
    n_units = None
    if args.draft:
        result = _load_result(args.draft)
        expect = draft_sha256(result)
        n_units = len([1 for fr in result.fields.values()
                       if fr.value not in (None, "", "not_reported")])
    files = []
    for p in args.verdicts:
        try:
            files.append(load_verdicts(p, expect_sha256=expect))
        except VerdictError as e:
            print(f"REJECTED {p}: {e}", file=sys.stderr)
            return 1
    rep = aggregate_verdicts(files, n_units_total=n_units, min_overlap=args.min_overlap)
    text = rep.summary()
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="metaextract-review",
        description="Build human-review packets from extractions, and aggregate "
                    "the verdicts that come back.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("packet", help="render one extraction as a review packet")
    p.add_argument("result", type=Path, help="an ExtractionResult JSON")
    p.add_argument("-o", "--out", type=Path, default=None,
                   help="output HTML (default: alongside the result, .review.html)")
    p.add_argument("--paper", type=Path, default=None,
                   help="the paper text the extraction was made from; enables the "
                        "verbatim check on every evidence quote")
    p.add_argument("--cells", type=Path, default=None,
                   help="adjudication mode: a JSON list of scored cells "
                        "({sample_idx, field, extracted, gold, decision}). Units "
                        "become these cells rather than every extracted value.")
    p.add_argument("--study", default=None, help="study label for the header")
    p.add_argument("--model", default=None, help="model id for the header")
    p.add_argument("--note", default=None, help="a note shown in the header")
    p.set_defaults(fn=_cmd_packet)

    p = sub.add_parser("ingest", help="validate returned verdict files")
    p.add_argument("verdicts", nargs="+", type=Path)
    p.add_argument("--draft", type=Path, default=None,
                   help="the ExtractionResult the verdicts must be pinned to")
    p.set_defaults(fn=_cmd_ingest)

    p = sub.add_parser("report", help="aggregate verdicts into support rates and kappa")
    p.add_argument("verdicts", nargs="+", type=Path)
    p.add_argument("--draft", type=Path, default=None)
    p.add_argument("--out", type=Path, default=None)
    p.add_argument("--min-overlap", type=int, default=10,
                   help="below this many shared units, kappa is reported as "
                        "unavailable rather than computed (default 10)")
    p.set_defaults(fn=_cmd_report)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
