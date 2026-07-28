"""Fetch paper text from NCBI given a PMID or PMCID.

Strategy (each rung is tried only if the previous yields no article *body*, so
the LLM is never left with an abstract when full text is reachable):
  1. If given a PMID, ask elink for an associated PMCID.
  2. If a PMCID exists, efetch the full-text XML from PMC and flatten to text.
  3. If that has no <body> (PMC often holds only an abstract-level record),
     fall back to the Europe PMC ``fullTextXML`` endpoint, which frequently
     carries the body when NCBI does not — including bioRxiv/medRxiv and other
     preprints indexed by Europe PMC (resolved by DOI when there is no PMCID).
  4. If the article is a non-Open-Access PMC record (abstract-only XML) but
     Europe PMC serves a free rendered PDF, fetch and text-extract that PDF —
     it carries the body the XML endpoints withhold.
  5. Otherwise, ask Unpaywall for any OA location (publisher free PDF, or an
     institutional/subject repository like Zenodo) and text-extract that PDF —
     this reaches OA articles with no PMC record at all.
  6. Otherwise, efetch the PubMed abstract (title + abstract + journal). The CLI
     then advises passing a locally-downloaded publisher PDF via ``--paper``.

Supplementary tables are always carried separately and never inlined into the
prose the LLM sees; only the article prose is affected by the ladder above.

Uses stdlib urllib so we don't add a runtime dependency.
"""
from __future__ import annotations

import http.client
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

# HTTP status codes worth retrying: NCBI eutils rate-limits (429) at ~3 req/s
# without an API key, and the public services occasionally 5xx under load.
_RETRY_STATUS = {429, 500, 502, 503, 504}

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
EUROPEPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
PMC_BIN = "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{bare}/bin/{name}"
USER_AGENT = "metaextractor/0.1 (+https://github.com/OmicsMLRepo)"
XLINK_HREF = "{http://www.w3.org/1999/xlink}href"


class FetchError(RuntimeError):
    pass


@dataclass
class FetchedPaper:
    text: str
    # "pmc_fulltext" | "europepmc_fulltext" | "europepmc_pdf" | "unpaywall_pdf" | "pubmed_abstract"
    source: str
    pmid: str | None
    pmcid: str | None
    # False when only an abstract could be retrieved (no article <body>). The CLI
    # uses this to advise passing a locally-downloaded PDF via --paper.
    has_body: bool = False
    supplementary_included: list[str] | None = None
    supplementary_skipped: list[tuple[str, str]] | None = None
    # Structured tables (xlsx sheets / csv / tsv / PDF table regions) parsed
    # from supplementary files. Carried separately so the deterministic
    # table path can consume them without re-parsing, and so the LLM
    # prompt only sees prose.
    supplementary_tables: list = field(default_factory=list)
    # Provenance for an auto-fetched SRA/ENA run manifest (see sra_manifest):
    # a short "ena:<project> (N runs)" string when one was resolved and fetched,
    # else None. Warnings record ambiguous/failed resolution.
    sra_manifest_source: str | None = None
    sra_manifest_warnings: list[str] = field(default_factory=list)


@dataclass
class _PmcFullText:
    text: str
    supplementary_hrefs: list[tuple[str, str]]  # (filename, absolute_url)
    has_body: bool = False  # True when the article carried a non-empty <body>


def _normalize_id(raw: str) -> tuple[str, str]:
    """Return (kind, bare_id) where kind ∈ {'pmid', 'pmcid'}."""
    s = raw.strip()
    upper = s.upper()
    if upper.startswith("PMID:"):
        return "pmid", s[5:].strip()
    if upper.startswith("PMCID:"):
        return "pmcid", s[6:].strip().lstrip("PMCpmc")
    if upper.startswith("PMC"):
        return "pmcid", s[3:].strip()
    if s.isdigit():
        return "pmid", s
    raise FetchError(f"Cannot interpret '{raw}' as a PMID or PMCID")


def _http_get(url: str, timeout: float = 30.0, *, retries: int = 4) -> bytes:
    """GET a URL with bounded exponential backoff on rate-limit/5xx/transport
    errors. NCBI eutils returns 429 above ~3 req/s (no API key), which is easy to
    trip when several papers are fetched concurrently; retrying keeps a burst from
    turning into an uncaught error. Non-retryable HTTP errors (e.g. 404) raise at
    once."""
    delay = 1.0
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code in _RETRY_STATUS and attempt < retries:
                time.sleep(delay)
                delay = min(delay * 2, 16.0)
                continue
            raise
        except (urllib.error.URLError, http.client.HTTPException,
                ConnectionError, TimeoutError):
            # URLError (DNS/refused/reset), IncompleteRead / other HTTPException
            # (truncated mid-read), and connection resets are all transient under
            # concurrent load — retry with backoff.
            if attempt < retries:
                time.sleep(delay)
                delay = min(delay * 2, 16.0)
                continue
            raise
    raise RuntimeError("unreachable")  # pragma: no cover


def _pmid_to_pmcid(pmid: str, retries: int = 4) -> str | None:
    """Resolve a PMID to its own PMC mirror id via elink, or None if the article
    has no PMC record.

    elink intermittently returns a 200 with an *empty* linkset under load (no HTTP
    error, so ``_http_get``'s retry doesn't fire) — which would otherwise be read as
    "no PMC record", silently dropping the article's full text and, worse, its
    supplementary tables (which are gated on a PMCID). We therefore retry when *no*
    linkset at all is present, distinguishing that transient empty from a genuine
    "PMC record exists but isn't the article's own mirror"."""
    url = f"{EUTILS}/elink.fcgi?" + urllib.parse.urlencode(
        {"dbfrom": "pubmed", "db": "pmc", "id": pmid, "retmode": "xml"}
    )
    delay = 0.5
    for attempt in range(retries + 1):
        root = ET.fromstring(_http_get(url))
        linksets = root.findall(".//LinkSetDb")
        # Only the ``pubmed_pmc`` link names the article's own PMC mirror. Other
        # link names (e.g. ``pubmed_pmc_refs``) point to articles the paper cites
        # — picking the first one would silently fetch the wrong paper.
        for lsd in linksets:
            if (lsd.findtext("LinkName") or "").strip() != "pubmed_pmc":
                continue
            link = lsd.find("Link/Id")
            if link is not None and link.text:
                return link.text
        # A completely empty linkset is the transient failure — retry it. A linkset
        # that exists but lacks ``pubmed_pmc`` is a real "no own PMC mirror".
        if linksets or attempt >= retries:
            return None
        time.sleep(delay)
        delay = min(delay * 2, 8.0)
    return None


def _flatten_xml(elem: ET.Element) -> str:
    parts: list[str] = []
    for node in elem.iter():
        if node.tag in {"table-wrap", "fig"}:
            continue
        if node.text:
            parts.append(node.text)
        if node.tail:
            parts.append(node.tail)
    text = " ".join(p.strip() for p in parts if p and p.strip())
    return re.sub(r"\s+", " ", text)


def _extract_supplementary_hrefs(article: ET.Element, pmcid: str) -> list[tuple[str, str]]:
    """Find supplementary-material elements and return (filename, absolute_url) tuples.

    Looks at <supplementary-material> and <inline-supplementary-material>. The
    file href is on the element itself or on a nested <media> child. Relative
    hrefs are resolved against the PMC bin/ directory for the article.
    """
    bare = pmcid.upper().removeprefix("PMC")
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for tag in ("supplementary-material", "inline-supplementary-material"):
        for elem in article.iter(tag):
            href = elem.get(XLINK_HREF)
            if not href:
                media = elem.find("media")
                if media is not None:
                    href = media.get(XLINK_HREF)
            if not href:
                continue
            if href.startswith(("http://", "https://")):
                url = href
                name = href.rsplit("/", 1)[-1] or href
            else:
                name = href.split("/")[-1]
                if "." not in name:
                    # JATS sometimes drops the extension; PMC bin/ resolution
                    # needs one, so just append .pdf as a best guess only when
                    # the element type hints at it. Otherwise skip.
                    continue
                url = PMC_BIN.format(bare=bare, name=name)
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append((name, url))
    return out


def _parse_jats_article(data: bytes, pmcid: str) -> _PmcFullText | None:
    """Parse a JATS document (NCBI efetch or Europe PMC fullTextXML) into title +
    abstract + body prose. Sets ``has_body`` when a non-empty ``<body>`` was found,
    which the fetch ladder uses to decide whether to try the next full-text source."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None
    # NCBI wraps the article in <pmc-articleset>; Europe PMC returns <article> as
    # the root, where ``.//article`` (descendants only) would miss it.
    article = root if root.tag == "article" else root.find(".//article")
    if article is None:
        return None
    sections: list[str] = []
    title = article.findtext(".//article-title")
    if title:
        sections.append(f"TITLE: {title.strip()}")
    abstract = article.find(".//abstract")
    if abstract is not None:
        sections.append("ABSTRACT: " + _flatten_xml(abstract))
    body = article.find(".//body")
    body_text = _flatten_xml(body) if body is not None else ""
    has_body = bool(body_text.strip())
    if has_body:
        sections.append("BODY: " + body_text)
    if not sections:
        return None
    return _PmcFullText(
        text="\n\n".join(sections),
        supplementary_hrefs=_extract_supplementary_hrefs(article, pmcid),
        has_body=has_body,
    )


def _fetch_pmc_fulltext(pmcid: str) -> _PmcFullText | None:
    url = f"{EUTILS}/efetch.fcgi?" + urllib.parse.urlencode(
        {"db": "pmc", "id": pmcid, "retmode": "xml"}
    )
    try:
        data = _http_get(url)
    except Exception:
        return None
    return _parse_jats_article(data, pmcid)


def _fetch_europepmc_fulltext(pmcid: str) -> _PmcFullText | None:
    """Europe PMC ``fullTextXML`` for a PMCID. Often carries the article body when
    the NCBI PMC record is abstract-only. Returns None if unavailable."""
    bare = pmcid.upper().removeprefix("PMC")
    url = f"{EUROPEPMC}/PMC{bare}/fullTextXML"
    try:
        data = _http_get(url)
    except Exception:
        return None
    return _parse_jats_article(data, f"PMC{bare}")


def _europepmc_id_for_doi(doi: str) -> str | None:
    """Resolve a DOI to a Europe PMC full-text id (e.g. ``PMC…`` or a ``PPR…``
    preprint id such as a bioRxiv/medRxiv record) that has full text available."""
    query = urllib.parse.urlencode(
        {"query": f'DOI:"{doi}"', "format": "json", "pageSize": "1",
         "resultType": "core"}
    )
    try:
        import json
        data = _http_get(f"{EUROPEPMC}/search?{query}")
        results = json.loads(data).get("resultList", {}).get("result", [])
    except Exception:
        return None
    for r in results:
        if r.get("hasTextMinedTerms") == "Y" or r.get("inEPMC") == "Y" or r.get("hasPDF") == "Y":
            pmcid = r.get("pmcid")
            if pmcid:
                return pmcid
            src, ext = r.get("source"), r.get("id")
            if src and ext:
                return f"{src}/{ext}"  # e.g. "PPR/PPR123456" for a preprint
    return None


def _fetch_europepmc_by_doi(doi: str) -> tuple[_PmcFullText | None, str | None]:
    """Full text from Europe PMC resolved by DOI — covers bioRxiv/medRxiv and
    other preprints that have no PMCID. Returns ``(fulltext, pmcid)`` where ``pmcid``
    is the resolved PMC id when the DOI maps to a PMC article (so the caller can then
    fetch its supplementary), or None for a preprint / no match."""
    epmc_id = _europepmc_id_for_doi(doi)
    if not epmc_id:
        return None, None
    if epmc_id.upper().startswith("PMC"):
        return _fetch_europepmc_fulltext(epmc_id), epmc_id.upper()
    # Preprint / non-PMC record: <SOURCE>/<ID>/fullTextXML
    try:
        data = _http_get(f"{EUROPEPMC}/{epmc_id}/fullTextXML")
    except Exception:
        return None, None
    return _parse_jats_article(data, epmc_id.split("/")[-1]), None


def _fetch_europepmc_pdf(pmcid: str | None) -> str | None:
    """Full text from Europe PMC's free *rendered PDF*, for non-Open-Access PMC
    articles whose machine-readable XML (NCBI efetch, EPMC ``fullTextXML``) is
    abstract-only.

    Many PMC articles are indexed but **not** in the Open Access subset: their
    JATS body is withheld, so both XML endpoints return only title+abstract,
    yet Europe PMC still serves a free human-readable PDF at
    ``europepmc.org/articles/PMC<id>?pdf=render``. That PDF carries the full
    body — including the data-availability accession that drives the SRA/ENA
    manifest fetch. Returns extracted text, or None when there is no PMCID, no
    free PDF (the URL returns HTML, not ``%PDF``), or pypdf is unavailable.
    """
    if not pmcid:
        return None
    bare = pmcid.upper().removeprefix("PMC")
    url = f"https://europepmc.org/articles/PMC{bare}?pdf=render"
    try:
        data = _http_get(url, timeout=90)
    except Exception:
        return None
    return _pdf_bytes_to_text(data)  # None if an HTML landing page / no pypdf


UNPAYWALL = "https://api.unpaywall.org/v2/{doi}?email={email}"
UNPAYWALL_EMAIL = "metaextractor@users.noreply.github.com"


def _pdf_bytes_to_text(data: bytes) -> str | None:
    """Extract text from PDF bytes with pypdf, or None if not a PDF / no pypdf."""
    if data[:4] != b"%PDF":
        return None
    try:
        import io

        from pypdf import PdfReader

        text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(data)).pages)
    except Exception:
        return None
    text = text.strip()
    return text or None


def _fetch_oa_pdf_via_unpaywall(doi: str | None) -> str | None:
    """Full text from any Open Access location Unpaywall knows for ``doi``.

    NCBI PMC and Europe PMC only cover PMC-deposited articles; many papers are
    OA at the **publisher** (e.g. a free Nature Microbiology PDF) or in an
    **institutional/subject repository** (Zenodo, university archives) with no
    PMC record at all. Unpaywall aggregates those locations; we fetch the first
    that yields a real PDF and text-extract it. Returns None when there is no
    DOI, no OA PDF location, or pypdf is unavailable.
    """
    if not doi:
        return None
    try:
        import json

        url = UNPAYWALL.format(doi=urllib.parse.quote(doi), email=UNPAYWALL_EMAIL)
        rec = json.loads(_http_get(url, timeout=30))
    except Exception:
        return None
    locations: list[dict] = []
    best = rec.get("best_oa_location")
    if best:
        locations.append(best)
    locations += rec.get("oa_locations") or []
    seen: set[str] = set()
    for loc in locations:
        pdf_url = loc.get("url_for_pdf")
        if not pdf_url:
            u = loc.get("url") or ""
            pdf_url = u if u.lower().endswith(".pdf") else None
        if not pdf_url or pdf_url in seen:
            continue
        seen.add(pdf_url)
        try:
            data = _http_get(pdf_url, timeout=90)
        except Exception:
            continue
        text = _pdf_bytes_to_text(data)
        if text:
            return text
    return None


def _fetch_pubmed_abstract(pmid: str) -> tuple[str, str | None]:
    """Return ``(abstract_text, doi)``. The DOI (when present) lets the fetch
    ladder try a Europe PMC full-text lookup for preprints with no PMCID."""
    url = f"{EUTILS}/efetch.fcgi?" + urllib.parse.urlencode(
        {"db": "pubmed", "id": pmid, "retmode": "xml"}
    )
    root = ET.fromstring(_http_get(url))
    article = root.find(".//PubmedArticle")
    if article is None:
        raise FetchError(f"PubMed returned no record for PMID {pmid}")
    title = article.findtext(".//ArticleTitle") or ""
    journal = article.findtext(".//Journal/Title") or ""
    year = article.findtext(".//PubDate/Year") or ""
    abstract_parts = []
    for ab in article.findall(".//Abstract/AbstractText"):
        label = ab.get("Label")
        text = "".join(ab.itertext()).strip()
        abstract_parts.append(f"{label}: {text}" if label else text)
    abstract = "\n".join(abstract_parts)
    doi = None
    for aid in article.findall(".//ArticleId"):
        if (aid.get("IdType") or "").lower() == "doi" and aid.text:
            doi = aid.text.strip()
            break
    text = (
        f"TITLE: {title.strip()}\n"
        f"JOURNAL: {journal.strip()} ({year})\n\n"
        f"ABSTRACT:\n{abstract}"
    )
    return text, doi


# Canonical article section headings. Their presence signals real narrative
# structure; a stub body or an extracted reference-list/abundance-table hits few.
_SECTION_HEADINGS = (
    "introduction", "background", "materials and methods", "methods",
    "results", "discussion", "conclusion", "data availability",
    "availability of data", "acknowledg", "references",
)
# Lines that look like a taxonomy lineage or a genome-accession matrix row — the
# bulk of a phylogeny/abundance table dumped into extracted text (the junk that
# would otherwise win a naive length contest).
_JUNK_LINE_RE = re.compile(r"[kpcofgs]__[A-Za-z0-9_]+|\b(?:GC[AF]_|NZ_|NC_)\d")
_REFERENCES_RE = re.compile(
    r"\n\s*(?:references|bibliography|literature cited)\s*\n", re.IGNORECASE)

# Score at/above which a candidate *body* is "clearly good" — stop escalating to
# costlier rungs (EPMC XML/PDF, Unpaywall) once one clears this. A well-structured
# real article body clears it easily; an abstract-only stub does not.
_GOOD_FULLTEXT_SCORE = 1.5


def _strip_references(text: str) -> str:
    """Drop the reference/bibliography tail, for *scoring* only.

    A long citation list inflates the length signal without adding narrative.
    Cuts at the *last* standalone references/bibliography heading, provided it is
    past the first 20% of the document (so a pathological early match can't gut
    the paper). The regex only matches the word alone on its own line, so an
    in-body phrase like "references the ENA" won't trigger it."""
    starts = [m.start() for m in _REFERENCES_RE.finditer(text)]
    if starts and starts[-1] > len(text) * 0.2:
        return text[:starts[-1]]
    return text


def _score_fulltext(text: str, source: str) -> float:
    """Heuristic article-narrative quality, for choosing among candidate texts.

    Combines section **structure** (#4), a taxonomy/matrix **junk penalty**
    (#5), and a **source prior** with a *saturating* length term (#6), on the
    reference-stripped narrative. Deliberately not a length contest: a long
    reference list or abundance table scores low on structure and high on junk,
    so it can't win on bulk alone."""
    if not text or not text.strip():
        return 0.0
    narrative = _strip_references(text)
    low = narrative.lower()
    hits = sum(1 for h in _SECTION_HEADINGS if h in low)          # #4
    structure = min(hits, 6) / 6.0
    lines = [ln for ln in narrative.splitlines() if ln.strip()]
    junk = (sum(1 for ln in lines if _JUNK_LINE_RE.search(ln)) / len(lines)  # #5
            ) if lines else 0.0
    length = min(len(narrative), 20000) / 20000.0                 # #6 (saturating)
    prior = 0.3 if source in ("pmc_fulltext", "europepmc_fulltext") else 0.0
    return 2.0 * structure + 1.5 * length + prior - 2.0 * junk


def fetch_paper(
    identifier: str,
    include_supplementary: bool = True,
    include_sra_manifest: bool = True,
    sra_project: str | None = None,
) -> FetchedPaper:
    """Fetch full text (PMC) or abstract (PubMed) for a PMID/PMCID.

    When ``include_supplementary`` is True and a PMCID is available, also
    download supplementary files (xlsx/csv/tsv/pdf/txt) from Europe PMC
    and append them to the paper text under ``--- SUPPLEMENTARY FILE: ---``
    headers.

    When ``include_sra_manifest`` is True, resolve the study's own SRA/ENA
    project from its data-availability accessions (or use ``sra_project`` when
    given) and fetch its per-sample run manifest as an additional table. This
    supplies a per-sample manifest for studies whose article body/supplements
    carry none — the dominant recall limiter — without a manual download.
    """
    kind, bare = _normalize_id(identifier)
    pmcid: str | None = None
    pmid_used: str | None = None
    pmc: _PmcFullText | None = None
    doi: str | None = None
    # Supplementary hrefs come from NCBI's JATS <supplementary-material> elements.
    # A body fallback can replace the chosen text, but its JATS does not expose
    # the PMC bin/S3 hrefs — so we capture NCBI's here and never let a fallback
    # discard them (they drive per-sample enumeration).
    ncbi_supp_hrefs: list[tuple[str, str]] = []

    # Best-of, not first-of: each rung contributes a (source, text, is_body)
    # candidate and we keep the highest-scoring narrative (see _score_fulltext),
    # so a thin/tabular body from an early rung no longer terminates the search
    # before a richer source is reached. Costlier rungs are attempted only while
    # no candidate is yet "clearly good", preserving the single-fetch common case.
    candidates: list[tuple[str, str, bool]] = []

    def _add(src: str, txt: str | None, is_body: bool) -> None:
        if txt and txt.strip():
            candidates.append((src, txt, is_body))

    def _best_body_score() -> float:
        # Only *body* candidates gate escalation — an abstract, however clean,
        # must never stop the search or outrank a real body.
        return max((_score_fulltext(c[1], c[0]) for c in candidates if c[2]),
                   default=-1.0)

    if kind == "pmcid":
        pmcid = bare
        pmc = _fetch_pmc_fulltext(bare)
        if pmc is not None:
            ncbi_supp_hrefs = pmc.supplementary_hrefs
            _add("pmc_fulltext", pmc.text, pmc.has_body)
    else:
        pmid_used = bare
        pmcid = _pmid_to_pmcid(bare)
        if pmcid:
            pmc = _fetch_pmc_fulltext(pmcid)
            if pmc is not None:
                ncbi_supp_hrefs = pmc.supplementary_hrefs
                _add("pmc_fulltext", pmc.text, pmc.has_body)
        # Fetch the abstract (+DOI) as an identity/floor candidate whenever NCBI
        # didn't already give a clearly-good body.
        if _best_body_score() < _GOOD_FULLTEXT_SCORE:
            abstract_text, doi = _fetch_pubmed_abstract(bare)
            _add("pubmed_abstract", abstract_text, False)

    # Escalate through richer/costlier rungs only while no *body* is clearly good.
    if _best_body_score() < _GOOD_FULLTEXT_SCORE and pmcid:
        epmc = _fetch_europepmc_fulltext(pmcid)
        if epmc is not None and epmc.has_body:
            _add("europepmc_fulltext", epmc.text, True)
    if _best_body_score() < _GOOD_FULLTEXT_SCORE and doi:
        epmc2, epmc_pmcid = _fetch_europepmc_by_doi(doi)
        if epmc2 is not None and epmc2.has_body:
            _add("europepmc_fulltext", epmc2.text, True)
            # A DOI that resolves to a PMC article gives us a PMCID even when
            # elink didn't — capture it so supplementary tables are still fetched.
            if epmc_pmcid and not pmcid:
                pmcid = epmc_pmcid
    if _best_body_score() < _GOOD_FULLTEXT_SCORE:
        pdf_text = _fetch_europepmc_pdf(pmcid)  # non-OA PMC free rendered PDF
        if pdf_text and len(pdf_text) > 1000:
            _add("europepmc_pdf", pdf_text, True)
    if _best_body_score() < _GOOD_FULLTEXT_SCORE and doi:
        up_text = _fetch_oa_pdf_via_unpaywall(doi)  # publisher/repository OA
        if up_text and len(up_text) > 1000:
            _add("unpaywall_pdf", up_text, True)

    if not candidates:
        raise FetchError(
            f"No text could be retrieved for {identifier}"
            + (f" (PMC{pmcid})" if pmcid else "")
        )
    # Prefer the best-scoring real body; fall back to the abstract only when no
    # body was found anywhere.
    bodies = [c for c in candidates if c[2]]
    source, text, has_body = max(
        bodies or candidates, key=lambda c: _score_fulltext(c[1], c[0])
    )

    paper = FetchedPaper(
        text=text, source=source, pmid=pmid_used, pmcid=pmcid, has_body=has_body
    )

    if include_supplementary and pmcid:
        from metaextractor.supplementary import fetch_supplementary
        # Prefer NCBI's declared hrefs; fall back to whatever the body source
        # exposed; if neither (NCBI unreachable), pass None so fetch_supplementary
        # recovers the tables by listing the S3 version prefix directly.
        jats_hrefs = ncbi_supp_hrefs or (pmc.supplementary_hrefs if pmc is not None else [])
        supp = fetch_supplementary(pmcid, jats_hrefs=jats_hrefs or None)
        paper.supplementary_included = supp.included
        paper.supplementary_skipped = supp.skipped
        paper.supplementary_tables = list(supp.tables)
        if supp.text:
            paper.text = f"{paper.text}\n\n{supp.text}"

    if include_sra_manifest or sra_project:
        from metaextractor.sra_manifest import manifest_for_paper

        # Resolve from the full paper text (body + any appended supplementary
        # prose), where the data-availability accession usually lives.
        mres = manifest_for_paper(paper.text, explicit_project=sra_project)
        paper.sra_manifest_warnings = list(mres.warnings)
        if mres.table is not None:
            paper.supplementary_tables.append(mres.table)
            paper.sra_manifest_source = mres.source
    return paper
