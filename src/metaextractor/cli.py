"""CLI: metaextract --paper paper.txt --schema schema.json [--paper-id PMID] [--out result.json]"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from metaextractor.extractor import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    ExtractionError,
    MetaExtractor,
    estimate_cost_usd,
)
from metaextractor.fetcher import FetchError, fetch_paper
from metaextractor.schema import Schema
from metaextractor.writers import to_csv


def _load_schema(path: Path, class_name: str | None = None) -> Schema:
    """Load a schema file. Auto-detects JSON vs YAML and LinkML vs native."""
    text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError as e:
            raise SystemExit(
                "YAML schema requires the 'linkml' extra: pip install 'metaextractor[linkml]'"
            ) from e
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)

    from metaextractor.adapters.linkml import is_linkml_schema, linkml_to_schema

    if is_linkml_schema(data):
        return linkml_to_schema(data, class_name=class_name)
    return Schema.from_dict(data)


def _resolve_api_key(value: str | None) -> str | None:
    """Resolve an --api-key value. Supports:
    - ``env:VARNAME`` — read from the given environment variable
    - ``file:PATH`` — read the first non-empty line of the file
    - any other value — treated as a literal key
    - ``None`` — fall back to the ``ANTHROPIC_API_KEY`` environment variable
    """
    if value is None:
        return None
    if value.startswith("env:"):
        name = value[4:]
        key = os.environ.get(name)
        if not key:
            raise SystemExit(f"--api-key env:{name}: environment variable is not set or empty")
        return key
    if value.startswith("file:"):
        path = Path(value[5:]).expanduser()
        if not path.is_file():
            raise SystemExit(f"--api-key file:{path}: file not found")
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped:
                return stripped
        raise SystemExit(f"--api-key file:{path}: file is empty")
    return value


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
    parser.add_argument("--out", type=Path, default=None, help="Write JSON result to file (default stdout).")
    parser.add_argument("--csv", type=Path, default=None, help="Also write a flat CSV (row per record).")
    parser.add_argument("--csv-provenance", action="store_true",
                        help="In the CSV, add per-field evidence/section/confidence columns.")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS,
                        help=f"Per-batch response cap (default {DEFAULT_MAX_TOKENS}).")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
                        help=f"Auto-batch schemas larger than this many fields (default {DEFAULT_BATCH_SIZE}).")
    parser.add_argument("--api-key", default=None, metavar="VALUE",
                        help="Anthropic API key. Accepts a literal key, 'env:VARNAME' to read "
                             "from an environment variable, or 'file:PATH' to read from a file. "
                             "Defaults to the ANTHROPIC_API_KEY environment variable.")
    parser.add_argument("--no-sample-discovery", dest="sample_discovery", action="store_false",
                        default=True,
                        help="Skip the +1 discovery call that enumerates sample IDs before per-batch field extraction (only relevant when supplementary tables are included).")
    args = parser.parse_args(argv)

    tables: list = []
    if args.paper:
        paper_text = _read_paper(args.paper)
    elif args.paper_id:
        try:
            fetched = fetch_paper(args.paper_id, include_supplementary=args.include_supplementary)
        except FetchError as e:
            print(f"ERROR: fetch failed: {e}", file=sys.stderr)
            return 2
        paper_text = fetched.text
        tables.extend(fetched.supplementary_tables or [])
        print(f"[fetched {fetched.source} for {args.paper_id}]", file=sys.stderr)
        if fetched.source == "pubmed_abstract":
            print(
                "[note: no PMC fulltext for this paper — only the PubMed "
                "abstract was retrieved, and no supplementary materials were "
                "fetched automatically. Pass --supplementary PATH [PATH ...] "
                "to include locally-downloaded supplementary files.]",
                file=sys.stderr,
            )
        if fetched.supplementary_included:
            print(f"[supplementary included ({len(fetched.supplementary_included)}): "
                  f"{', '.join(fetched.supplementary_included)}]", file=sys.stderr)
        if fetched.supplementary_tables:
            print(f"[supplementary tables parsed: {len(fetched.supplementary_tables)} "
                  f"(deterministic path; LLM will not see them)]", file=sys.stderr)
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
        api_key=_resolve_api_key(args.api_key),
    )
    try:
        result = extractor.extract(
            paper_text, schema_obj, paper_id=args.paper_id, tables=tables or None
        )
    except ExtractionError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        if e.raw_response:
            print("--- raw model response ---", file=sys.stderr)
            print(e.raw_response, file=sys.stderr)
        return 2

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
    return 0


if __name__ == "__main__":
    sys.exit(main())
