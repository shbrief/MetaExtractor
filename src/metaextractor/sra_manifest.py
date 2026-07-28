"""Fetch a study's per-sample SRA/ENA run manifest and turn it into a Table.

This ports the manifest-building step that previously lived in the R curation
pipeline (``bioproject_to_sra_metadata``) into MetaExtractor — but resolves the
study's *own* project authoritatively from its data-availability accessions,
rather than blindly regex-scraping the first BioProject in the text. The R
pipeline's blind scrape could latch onto a **referenced or citing** study's
project (its docstring warned it matched "including references"), which is how
some curated ``_sra_meta.tsv`` files ended up holding an unrelated study's runs.

Flow:
  1. :func:`extract_dataset_accessions` — find INSDC accessions in the paper
     text, each scored by proximity to data-availability language.
  2. :func:`resolve_projects` — choose the study's own project(s): prefer
     BioProject accessions that sit in a data-availability context; otherwise a
     single unambiguous project; otherwise resolve run/sample/secondary
     accessions (in context) to their project via ENA. When the text is
     ambiguous we return nothing rather than guess — a missing manifest is safe,
     a wrong one is not.
  3. :func:`fetch_run_manifest` — ENA ``filereport`` ``read_run`` TSV → Table.

The resulting ``Table`` (``source="ena"``) flows into the deterministic tables
path exactly like a supplementary table, so ``run_accession`` → ``ncbi_accession``
and ``instrument_model`` → ``sequencing_platform`` map through the existing
column aliases (see :mod:`metaextractor.column_mapper`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from metaextractor.supplementary import Table

# ENA Portal API. Mirrors both ENA (PRJEB/ERR…) and SRA (PRJNA/SRR…) submissions,
# so one endpoint covers NCBI- and EBI-originated data.
ENA_FILEREPORT = "https://www.ebi.ac.uk/ena/portal/api/filereport"

# Fields requested from ENA read_run. Ordered so the sample-identifying and
# schema-relevant columns lead. host_sex/host_body_site frequently carry the
# curated sex/body_site; instrument_model is the specific sequencing_platform.
_MANIFEST_FIELDS = [
    "run_accession", "sample_accession", "experiment_accession", "study_accession",
    "instrument_platform", "instrument_model",
    "library_source", "library_strategy", "library_layout",
    "scientific_name", "tax_id",
    "sample_title", "sample_alias",
    "host", "host_sex", "host_body_site",
    "country", "collection_date", "first_public",
]
# Minimal fallback if ENA rejects the full field list (unknown field → HTTP 400).
_MANIFEST_FIELDS_MIN = [
    "run_accession", "sample_accession", "study_accession",
    "instrument_platform", "instrument_model",
    "library_source", "library_strategy", "scientific_name",
]

# INSDC accession shapes. BioProject is the primary project id; the (SED)RP /
# secondary study id, and run/experiment/sample ids resolve to a project via ENA.
_ACC_PATTERNS: dict[str, re.Pattern] = {
    "bioproject": re.compile(r"\bPRJ(?:NA|EB|DB)\d+\b"),
    "study": re.compile(r"\b(?:SR|ER|DR)P\d{5,}\b"),
    "run": re.compile(r"\b(?:SR|ER|DR)R\d{5,}\b"),
    "experiment": re.compile(r"\b(?:SR|ER|DR)X\d{5,}\b"),
    "sample": re.compile(r"\b(?:SR|ER|DR)S\d{5,}\b"),
    "biosample": re.compile(r"\bSAM(?:N|EA|D)[A-Z]?\d+\b"),
}
# Kinds that ENA can resolve to a study_accession (i.e. everything but a project).
_RESOLVABLE = ("run", "experiment", "sample", "biosample", "study")

# Data-availability language. A match near an accession marks it as the paper's
# own deposit rather than a dataset it merely references or compares against.
_CONTEXT_TERMS = (
    "availab", "accession", "deposit", "european nucleotide archive", " ena",
    "sequence read archive", " sra", "bioproject", "repositor", "raw read",
    "raw sequenc", "submitted to", "under accession", "archived", "data are",
    "have been made", "can be found", "are available", "was deposited",
)
_CONTEXT_WINDOW = 250  # chars either side of the accession to inspect

HttpGet = Callable[[str], bytes]


@dataclass
class Accession:
    value: str
    kind: str          # bioproject | study | run | experiment | sample | biosample
    context_score: int  # count of data-availability terms nearby (0 = none)
    count: int = 1      # times this accession appears in the text


@dataclass
class ManifestResult:
    """Outcome of an attempt to build a run manifest for a paper."""

    table: Table | None = None
    projects: list[str] = field(default_factory=list)  # projects fetched
    n_runs: int = 0
    warnings: list[str] = field(default_factory=list)
    source: str | None = None  # human-readable provenance, or None if nothing found


def _default_http_get(url: str) -> bytes:
    # Imported lazily to avoid a module-load cycle (fetcher imports this module
    # lazily inside fetch_paper).
    from metaextractor.fetcher import _http_get

    return _http_get(url)


def extract_dataset_accessions(text: str) -> list[Accession]:
    """Find INSDC accessions in ``text``, scored by data-availability proximity.

    Duplicate accessions are collapsed; ``count`` records how often each
    appears and ``context_score`` takes the strongest (max) nearby-term count
    across its occurrences.
    """
    lower = text.lower()
    by_value: dict[str, Accession] = {}
    for kind, pat in _ACC_PATTERNS.items():
        for m in pat.finditer(text):
            val = m.group(0)
            lo = max(0, m.start() - _CONTEXT_WINDOW)
            hi = min(len(text), m.end() + _CONTEXT_WINDOW)
            window = lower[lo:hi]
            score = sum(1 for t in _CONTEXT_TERMS if t in window)
            existing = by_value.get(val)
            if existing is None:
                by_value[val] = Accession(value=val, kind=kind, context_score=score)
            else:
                existing.count += 1
                existing.context_score = max(existing.context_score, score)
    return list(by_value.values())


def _resolve_to_project(acc: str, http_get: HttpGet) -> list[str]:
    """Resolve a run/sample/experiment/secondary accession to its project(s)."""
    url = (
        f"{ENA_FILEREPORT}?accession={acc}&result=read_run"
        f"&fields=study_accession&format=tsv"
    )
    try:
        raw = http_get(url).decode("utf-8", "replace")
    except Exception:
        return []
    projects: list[str] = []
    for line in raw.splitlines()[1:]:  # skip header
        cell = line.split("\t")[0].strip() if line.strip() else ""
        if cell and cell not in projects:
            projects.append(cell)
    return projects


def resolve_projects(
    accessions: list[Accession],
    http_get: HttpGet | None = None,
) -> tuple[list[str], list[str]]:
    """Pick the study's own project accession(s) from extracted accessions.

    Returns ``(projects, warnings)``. Resolution order, deliberately
    conservative — a missing manifest is safe, a wrong one is not:

    1. BioProject accessions sitting in a data-availability context.
    2. A single unambiguous BioProject anywhere in the text.
    3. Run/sample/experiment/secondary accessions in a data-availability
       context, resolved to their project via ENA.

    When several distinct projects compete with no data-availability signal to
    disambiguate, we return nothing and warn, rather than guess.
    """
    http_get = http_get or _default_http_get
    warnings: list[str] = []
    projects = [a for a in accessions if a.kind == "bioproject"]

    # 1. BioProjects in data-availability context.
    in_context = [a for a in projects if a.context_score > 0]
    if in_context:
        top = max(a.context_score for a in in_context)
        chosen = [a.value for a in in_context if a.context_score == top]
        return _dedup(chosen), warnings

    # 2. A single unambiguous BioProject (no context, but no competition either).
    if projects:
        distinct = _dedup([a.value for a in projects])
        if len(distinct) == 1:
            return distinct, warnings
        warnings.append(
            f"Multiple BioProjects with no data-availability context "
            f"({', '.join(distinct[:5])}); not guessing which is the study's own."
        )
        return [], warnings

    # 3. Resolve run/sample/experiment/secondary accessions (in context) to a project.
    resolvable = [
        a for a in accessions
        if a.kind in _RESOLVABLE and a.context_score > 0
    ]
    resolvable.sort(key=lambda a: (a.context_score, a.count), reverse=True)
    resolved: list[str] = []
    for a in resolvable[:8]:  # cap the resolution fan-out
        for proj in _resolve_to_project(a.value, http_get):
            if proj not in resolved:
                resolved.append(proj)
    if resolved:
        if len(resolved) > 1:
            warnings.append(
                f"Data-availability accessions resolved to multiple projects "
                f"({', '.join(resolved[:5])}); fetching all."
            )
        return resolved, warnings

    return [], warnings


def _parse_manifest_tsv(project: str, raw: str) -> Table | None:
    reader = raw.splitlines()
    rows = [line.split("\t") for line in reader if line != ""]
    if len(rows) < 2:
        return None
    header = [h.strip() for h in rows[0]]
    data = rows[1:]
    dict_rows = [
        {header[i]: (r[i] if i < len(r) else "") for i in range(len(header))}
        for r in data
    ]
    return Table(
        name=f"{project}_ena_manifest.tsv",
        source="ena",
        columns=list(header),
        rows=dict_rows,
        raw_rows=[list(header)] + [list(r) + [""] * (len(header) - len(r)) for r in data],
    )


def fetch_run_manifest(
    project: str,
    http_get: HttpGet | None = None,
    max_runs: int = 20000,
) -> Table | None:
    """Fetch ENA ``read_run`` metadata for a project accession → Table.

    Tries the full field list, falling back to a minimal set if ENA rejects an
    unknown field. Returns None on network failure or empty result.
    """
    http_get = http_get or _default_http_get
    for fields in (_MANIFEST_FIELDS, _MANIFEST_FIELDS_MIN):
        url = (
            f"{ENA_FILEREPORT}?accession={project}&result=read_run"
            f"&fields={','.join(fields)}&format=tsv&limit={max_runs}"
        )
        try:
            raw = http_get(url).decode("utf-8", "replace")
        except Exception:
            continue
        # ENA returns a plain-text error (not TSV with our header) on a bad field.
        if not raw.strip() or "run_accession" not in raw.splitlines()[0]:
            continue
        table = _parse_manifest_tsv(project, raw)
        if table is not None:
            return table
    return None


def manifest_for_paper(
    text: str,
    explicit_project: str | None = None,
    http_get: HttpGet | None = None,
) -> ManifestResult:
    """Resolve a paper's own SRA/ENA project and fetch its run manifest.

    ``explicit_project`` (e.g. from a ``--sra-project`` CLI override) bypasses
    resolution and is treated as authoritative.
    """
    http_get = http_get or _default_http_get
    result = ManifestResult()

    if explicit_project:
        projects = [explicit_project.strip()]
    else:
        accs = extract_dataset_accessions(text)
        projects, warns = resolve_projects(accs, http_get)
        result.warnings.extend(warns)
        if not projects:
            return result

    tables: list[Table] = []
    for proj in projects:
        t = fetch_run_manifest(proj, http_get)
        if t is None:
            result.warnings.append(f"ENA returned no run manifest for {proj}.")
            continue
        tables.append(t)
        result.projects.append(proj)

    if not tables:
        return result

    merged = _concat_tables(tables)
    result.table = merged
    result.n_runs = len(merged.rows)
    result.source = f"ena:{'+'.join(result.projects)} ({result.n_runs} runs)"
    return result


def _concat_tables(tables: list[Table]) -> Table:
    """Union multiple project manifests into one Table (columns unioned)."""
    if len(tables) == 1:
        return tables[0]
    # Union of columns, preserving first-seen order.
    cols: list[str] = []
    for t in tables:
        for c in t.columns:
            if c not in cols:
                cols.append(c)
    rows = [{c: r.get(c, "") for c in cols} for t in tables for r in t.rows]
    raw = [list(cols)] + [[r.get(c, "") for c in cols] for r in rows]
    return Table(
        name="+".join(t.name for t in tables),
        source="ena",
        columns=cols,
        rows=rows,
        raw_rows=raw,
    )


def _dedup(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out
