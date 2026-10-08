"""CLI: metaextract --paper paper.txt --schema schema.json [--paper-id PMID] [--out result.json]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from metaextractor.extractor import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MAX_TOKENS_CEILING,
    DEFAULT_MIN_TABLE_RELEVANCE,
    DEFAULT_MODEL,
    ExtractionError,
    MetaExtractor,
    estimate_cost_usd,
)
from metaextractor.fetcher import (
    FETCH_RECORD,
    FetchError,
    fetch_paper,
    load_fetched,
    save_fetched,
)
from metaextractor.model import AnthropicModel
from metaextractor.sample_rules import AgeBoundRules
from metaextractor.schema import Schema
from metaextractor.writers import to_csv


def _load_schema(path: Path, class_name: str | None = None) -> Schema:
    """Load a schema file. Auto-detects JSON vs YAML and LinkML vs native."""
    from metaextractor.schema_loader import SchemaLoadError, load_schema_file

    try:
        return load_schema_file(path, class_name=class_name)
    except SchemaLoadError as e:
        raise SystemExit(str(e)) from e


def _resolve_api_key(value: str | None) -> str:
    """Resolve an --api-key value. Supports a literal key, ``env:VARNAME``,
    ``file:PATH``, or auto-discovery from ANTHROPIC_API_KEY / CLAUDE_API_KEY."""
    from metaextractor.keys import ApiKeyError, resolve_api_key

    try:
        return resolve_api_key(value)
    except ApiKeyError as e:
        raise SystemExit(f"--api-key: {e}") from e


def _read_paper(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as e:
            raise SystemExit(
                "PDF input requires the 'pdf' extra: pip install 'metaextractor[pdf]'"
            ) from e
        reader = PdfReader(str(path))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    return path.read_text(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="metaextract",
        description="Extract biomedical metadata from a paper against a JSON schema.",
    )
    parser.add_argument("--paper", type=Path, help="Path to paper text or PDF. If omitted, --paper-id must be a PMID/PMCID and the text is fetched from NCBI.")
    parser.add_argument("--schema", required=True, type=Path, help="Schema file: JSON, YAML, or LinkML YAML (auto-detected).")
    parser.add_argument("--linkml-class", default=None, help="When --schema is a LinkML file with multiple classes, the class whose slots become fields.")
    parser.add_argument("--paper-id", default=None, help="Identifier (PMID, PMCID, or DOI). Used as the paper_id and, when --paper is omitted, to fetch the text.")
    parser.add_argument("--no-supplementary", dest="include_supplementary",
                        action="store_false", default=True,
                        help="Skip the auto supplementary-materials fetch (JATS URLs + Europe PMC ZIP). Does not affect --supplementary.")
    parser.add_argument("--supplementary", nargs="+", type=Path, default=None, metavar="PATH",
                        help="One or more local supplementary files (xlsx/csv/tsv/pdf/txt) to include alongside the paper. Directories are expanded to all supported files inside (non-recursive). Orthogonal to --no-supplementary; combine if you want only local files.")
    parser.add_argument("--no-sra-manifest", dest="include_sra_manifest",
                        action="store_false", default=True,
                        help="Skip the auto SRA/ENA per-sample run-manifest fetch (resolves the study's own project from its data-availability accessions and pulls the ENA read_run manifest). Only applies on the --paper-id fetch path.")
    parser.add_argument("--no-biosample-attributes", dest="include_biosample_attributes",
                        action="store_false", default=True,
                        help="Do not add the runs' BioSample attributes (EBI BioSamples) to the SRA/ENA run manifest as columns.")
    parser.add_argument("--sra-project", default=None, metavar="PRJXXXXXX",
                        help="Explicit SRA/ENA project accession (e.g. PRJEB7369) to fetch the run manifest from, bypassing text resolution. Authoritative when you know the study's project.")
    parser.add_argument("--out", type=Path, default=None, help="Write JSON result to file (default stdout).")
    parser.add_argument("--csv", type=Path, default=None, help="Also write a flat CSV (row per record).")
    parser.add_argument("--csv-provenance", action="store_true",
                        help="In the CSV, add per-field evidence/section/confidence columns.")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS,
                        help=f"Per-batch response cap (default {DEFAULT_MAX_TOKENS}).")
    parser.add_argument("--max-tokens-ceiling", type=int, default=DEFAULT_MAX_TOKENS_CEILING,
                        help="When a response stops at the output cap, it is re-requested with the "
                             "cap doubled, up to this value (default "
                             f"{DEFAULT_MAX_TOKENS_CEILING}).")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
                        help=f"Auto-batch schemas larger than this many fields (default {DEFAULT_BATCH_SIZE}).")
    parser.add_argument("--api-key", default=None, metavar="VALUE",
                        help="Anthropic API key. Accepts a literal key, 'env:VARNAME' to read "
                             "from an environment variable, or 'file:PATH' to read from a file. "
                             "If omitted, auto-discovers from ANTHROPIC_API_KEY or CLAUDE_API_KEY.")
    parser.add_argument("--no-sample-discovery", dest="sample_discovery", action="store_false",
                        default=True,
                        help="Skip the +1 discovery call that enumerates sample IDs before per-batch field extraction (only relevant when supplementary tables are included).")
    parser.add_argument("--min-table-relevance", type=float, default=DEFAULT_MIN_TABLE_RELEVANCE,
                        metavar="0-1",
                        help=f"Deterministic relevance gate for supplementary tables (default "
                             f"{DEFAULT_MIN_TABLE_RELEVANCE}). Tables scoring below this against the "
                             f"schema are skipped before the LLM plan step; measurement/feature "
                             f"matrices are always skipped. Set 0 to keep all non-matrix tables.")
    parser.add_argument("--age-rules", type=Path, default=None, metavar="JSON",
                        help="Enable deterministic age_min/age_max filling with the rules in this "
                             "JSON file (see metaextractor.sample_rules.AgeBoundRules). Off by default.")
    parser.add_argument("--save-text", type=Path, default=None, metavar="PATH",
                        help="Write the exact paper text sent to the model (body plus supplementary "
                             "prose) to PATH, for auditing and evidence checks.")
    parser.add_argument("--fetch-cache", type=Path, default=None, metavar="DIR",
                        help="Frozen retrieval for --paper-id: read the paper text, parsed tables, "
                             "and retrieval record from DIR when it holds one (no network), "
                             "otherwise fetch and write them to DIR.")
    parser.add_argument("--require-fetch-cache", action="store_true",
                        help="With --fetch-cache: fail instead of fetching when DIR holds no "
                             "frozen retrieval.")
    parser.add_argument("--run-meta", type=Path, default=None, metavar="PATH",
                        help="Write a JSON record of request settings, returned model ids, token "
                             "usage, cost estimate, and retrieval provenance to PATH.")
    args = parser.parse_args(argv)
    started_utc = _utc_now()

    api_key = _resolve_api_key(args.api_key)

    tables: list = []
    fetched = None
    if args.paper:
        paper_text = _read_paper(args.paper)
    elif args.paper_id:
        cached = args.fetch_cache is not None and (args.fetch_cache / FETCH_RECORD).exists()
        if args.require_fetch_cache and not cached:
            print(f"ERROR: no frozen retrieval in {args.fetch_cache}", file=sys.stderr)
            return 2
        try:
            if cached:
                fetched = load_fetched(args.fetch_cache)
            else:
                fetched = fetch_paper(
                    args.paper_id,
                    include_supplementary=args.include_supplementary,
                    include_sra_manifest=args.include_sra_manifest,
                    sra_project=args.sra_project,
                    include_biosample_attributes=args.include_biosample_attributes,
                )
                if args.fetch_cache is not None:
                    save_fetched(fetched, args.fetch_cache)
        except FetchError as e:
            print(f"ERROR: fetch failed: {e}", file=sys.stderr)
            return 2
        paper_text = fetched.text
        tables.extend(fetched.supplementary_tables or [])
        print(f"[{'loaded frozen retrieval' if cached else 'fetched'} {fetched.source} "
              f"for {args.paper_id}]", file=sys.stderr)
        if not fetched.has_body:
            print(
                "[note: no article body was reachable for this paper — only an "
                "abstract was retrieved (NCBI PMC and Europe PMC full text were "
                "unavailable). For full text, download the publisher/bioRxiv PDF "
                "and pass it with --paper FILE.pdf (optionally keeping --paper-id "
                "for the identifier). Pass --supplementary PATH [PATH ...] to add "
                "locally-downloaded supplementary files.]",
                file=sys.stderr,
            )
        if fetched.supplementary_included:
            print(f"[supplementary included ({len(fetched.supplementary_included)}): "
                  f"{', '.join(fetched.supplementary_included)}]", file=sys.stderr)
        if fetched.supplementary_tables:
            print(f"[supplementary tables parsed: {len(fetched.supplementary_tables)} "
                  f"(deterministic path; LLM will not see them)]", file=sys.stderr)
        if fetched.sra_manifest_source:
            print(f"[SRA/ENA run manifest: {fetched.sra_manifest_source} "
                  f"(deterministic path)]", file=sys.stderr)
        for w in (fetched.sra_manifest_warnings or []):
            print(f"[SRA/ENA manifest: {w}]", file=sys.stderr)
        if fetched.supplementary_skipped:
            for name, why in fetched.supplementary_skipped:
                print(f"[supplementary skipped: {name} — {why}]", file=sys.stderr)
    else:
        parser.error("either --paper or --paper-id (PMID/PMCID) is required")

    if args.supplementary:
        from metaextractor.supplementary import (
            SKIP_EXTS,
            TEXT_EXTS,
            supplementary_from_local,
        )
        _SUPP_EXTS = TEXT_EXTS | {".xlsx", ".pdf"}
        expanded: list[Path] = []
        for p in args.supplementary:
            if p.is_dir():
                children = sorted(
                    c for c in p.iterdir()
                    if c.is_file()
                    and c.suffix.lower() in _SUPP_EXTS
                    and c.suffix.lower() not in SKIP_EXTS
                )
                if not children:
                    print(
                        f"[supplementary (local) skipped: {p} — directory "
                        f"contained no supported files (xlsx/csv/tsv/pdf/txt)]",
                        file=sys.stderr,
                    )
                expanded.extend(children)
            else:
                expanded.append(p)
        local = supplementary_from_local(expanded)
        if local.text:
            paper_text = f"{paper_text}\n\n{local.text}"
        tables.extend(local.tables)
        if local.included:
            print(f"[supplementary (local) included ({len(local.included)}): "
                  f"{', '.join(local.included)}]", file=sys.stderr)
        if local.tables:
            print(f"[supplementary (local) tables parsed: {len(local.tables)} "
                  f"(deterministic path; LLM will not see them)]", file=sys.stderr)
        for name, why in local.skipped:
            print(f"[supplementary (local) skipped: {name} — {why}]", file=sys.stderr)

    schema_obj = _load_schema(args.schema, class_name=args.linkml_class)

    extractor = MetaExtractor(
        model=args.model,
        max_tokens=args.max_tokens,
        batch_size=args.batch_size,
        sample_discovery=args.sample_discovery,
        api_key=api_key,
        min_table_relevance=args.min_table_relevance,
        age_rules=AgeBoundRules.from_json(args.age_rules) if args.age_rules else None,
        max_tokens_ceiling=args.max_tokens_ceiling,
    )
    if args.save_text:
        args.save_text.write_text(paper_text, encoding="utf-8")
    try:
        result = extractor.extract(
            paper_text, schema_obj, paper_id=args.paper_id, tables=tables or None
        )
    except ExtractionError as e:
        _print_calls(extractor)
        print(f"ERROR: {e}", file=sys.stderr)
        if e.raw_response:
            print("--- raw model response ---", file=sys.stderr)
            print(e.raw_response, file=sys.stderr)
        if args.run_meta:
            # Usage of a failed extraction is billed too; record it.
            c = estimate_cost_usd(extractor.last_usage, args.model)
            _write_run_meta(args, extractor, None, fetched, paper_text, tables, c, started_utc,
                            error=str(e))
        return 2
    _print_calls(extractor)

    if result.table_selection:
        kept = sum(1 for s in result.table_selection if s.selected)
        print(f"[table selection: {kept} kept / {len(result.table_selection)} scored "
              f"(gate={args.min_table_relevance})]", file=sys.stderr)
        for s in result.table_selection:
            tag = "kept" if s.selected else ("matrix" if s.is_matrix else "low-relevance")
            why = "; ".join(s.reasons) or "no schema-matching columns"
            print(f"[  {s.name}: {tag} (score={s.score:.2f}) — {why}]", file=sys.stderr)

    payload = result.model_dump_json(indent=2)
    if args.out:
        args.out.write_text(payload, encoding="utf-8")
    elif not args.csv:
        print(payload)

    if args.csv:
        to_csv(result, args.csv, include_provenance=args.csv_provenance)
        print(f"[wrote CSV: {args.csv}]", file=sys.stderr)

    u = extractor.last_usage
    c = estimate_cost_usd(u, args.model)
    print(
        f"[usage: {u['n_calls']} call(s); "
        f"input={u['input_tokens']:,}, "
        f"cache_write={u['cache_creation_input_tokens']:,}, "
        f"cache_read={u['cache_read_input_tokens']:,}, "
        f"output={u['output_tokens']:,}]",
        file=sys.stderr,
    )
    if "note" in c:
        print(f"[cost: {c['note']}]", file=sys.stderr)
    else:
        print(
            f"[cost: ${c['total_usd']:.4f} "
            f"(input ${c['input_usd']:.4f} + cache_w ${c['cache_write_usd']:.4f} + "
            f"cache_r ${c['cache_read_usd']:.4f} + output ${c['output_usd']:.4f})]",
            file=sys.stderr,
        )
    if args.run_meta:
        _write_run_meta(args, extractor, result, fetched, paper_text, tables, c, started_utc)
    return 0


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _print_calls(extractor) -> None:
    """Report output-budget re-requests (responses that stopped at max_tokens)."""
    truncated = [c for c in extractor.last_calls if c.get("stop_reason") == "max_tokens"]
    for c in truncated:
        what = c.get("table") or f"{c.get('n_fields')} field(s) from {c.get('first_field')!r}"
        print(f"[truncated at max_tokens={c['max_tokens']}: {c['purpose']} ({what}); "
              f"re-requested with a larger budget if below the ceiling]", file=sys.stderr)


def _write_run_meta(args, extractor, result, fetched, paper_text, tables, cost, started_utc,
                    error: str | None = None) -> None:
    import hashlib
    import json
    import platform

    from metaextractor import __version__
    from metaextractor.extractor import PRICING_AS_OF

    # Reported under the same "anthropic_sdk" run-meta key: it really is the
    # Anthropic SDK version, and the benchmark ledger reads that key.
    sdk_version = AnthropicModel.sdk_version()
    meta = {
        "started_utc": started_utc,
        "finished_utc": _utc_now(),
        "paper_id": args.paper_id,
        "status": "failed" if error else "ok",
        "error": error,
        "request": {
            "model_requested": args.model,
            "models_returned": sorted(extractor.last_response_models),
            "max_tokens": args.max_tokens,
            "max_tokens_ceiling": args.max_tokens_ceiling,
            "batch_size": args.batch_size,
            "sample_discovery": args.sample_discovery,
            "min_table_relevance": args.min_table_relevance,
            "sampling_and_thinking": "not set (API defaults: no temperature/top_p/top_k/"
                                     "thinking/effort parameters sent)",
            "age_rules": str(args.age_rules) if args.age_rules else None,
        },
        "usage": dict(extractor.last_usage),
        "calls": list(extractor.last_calls),
        "cost_estimate": {**cost, "pricing_as_of": PRICING_AS_OF},
        "retrieval": None if fetched is None else {
            "frozen_retrieval": str(args.fetch_cache) if args.fetch_cache else None,
            "source": fetched.source, "has_body": fetched.has_body,
            "pmid": fetched.pmid, "pmcid": fetched.pmcid, "doi": fetched.doi,
            "attempts": fetched.retrieval_attempts,
            "supplementary_included": fetched.supplementary_included,
            "supplementary_skipped": fetched.supplementary_skipped,
            "sra_manifest_source": fetched.sra_manifest_source,
            "sra_manifest_warnings": fetched.sra_manifest_warnings,
            "sra_manifest_resolution": fetched.sra_manifest_resolution,
        },
        "local_supplementary": [str(p) for p in (args.supplementary or [])],
        "paper_text_sha256": hashlib.sha256(paper_text.encode("utf-8")).hexdigest(),
        "paper_text_chars": len(paper_text),
        "n_tables": len(tables),
        "output": None if result is None else {
            "granularity": result.granularity, "n_samples": len(result.samples),
            "n_fields": len(result.fields), "n_warnings": len(result.extraction_warnings)},
        "versions": {"metaextractor": __version__, "anthropic_sdk": sdk_version,
                     "python": platform.python_version()},
    }
    args.run_meta.write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
