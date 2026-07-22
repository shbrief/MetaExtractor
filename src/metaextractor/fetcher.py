"""Fetch paper text from NCBI given a PMID or PMCID.

Strategy (each rung is tried only if the previous yields no article *body*, so
the LLM is never left with an abstract when full text is reachable):
  1. If given a PMID, ask elink for an associated PMCID.
  2. If a PMCID exists, efetch the full-text XML from PMC and flatten to text.
  3. If that has no <body> (PMC often holds only an abstract-level record),
     fall back to the Europe PMC ``fullTextXML`` endpoint, which frequently
     carries the body when NCBI does not — including bioRxiv/medRxiv and other
     preprints indexed by Europe PMC (resolved by DOI when there is no PMCID).
  4. Otherwise, efetch the PubMed abstract (title + abstract + journal). The CLI
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
    source: str  # "pmc_fulltext" | "europepmc_fulltext" | "pubmed_abstract"
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


def fetch_paper(identifier: str, include_supplementary: bool = True) -> FetchedPaper:
    """Fetch full text (PMC) or abstract (PubMed) for a PMID/PMCID.

    When ``include_supplementary`` is True and a PMCID is available, also
    download supplementary files (xlsx/csv/tsv/pdf/txt) from Europe PMC
    and append them to the paper text under ``--- SUPPLEMENTARY FILE: ---``
    headers.
    """
    kind, bare = _normalize_id(identifier)
    pmcid: str | None = None
    pmid_used: str | None = None
    pmc: _PmcFullText | None = None
    text: str | None = None
    source = "pubmed_abstract"
    # Supplementary hrefs come from NCBI's JATS <supplementary-material> elements.
    # The Europe PMC full-text fallback (below) can replace ``pmc`` for the *body*,
    # but its JATS does not expose the PMC bin/S3 hrefs — so we capture NCBI's hrefs
    # here and never let the body fallback discard them (they drive per-sample
    # enumeration). If NCBI returned nothing at all, an empty list lets
    # fetch_supplementary recover the files by listing the S3 prefix directly.
    ncbi_supp_hrefs: list[tuple[str, str]] = []

    def _europepmc_body(pmc_id: str) -> _PmcFullText | None:
        """Europe PMC fallback, used only when it actually yields a body."""
        epmc = _fetch_europepmc_fulltext(pmc_id)
        return epmc if epmc is not None and epmc.has_body else None

    if kind == "pmcid":
        pmcid = bare
        pmc = _fetch_pmc_fulltext(bare)
        source = "pmc_fulltext"
        if pmc is not None:
            ncbi_supp_hrefs = pmc.supplementary_hrefs
        if pmc is None or not pmc.has_body:
            epmc = _europepmc_body(bare)
            if epmc is not None:
                pmc, source = epmc, "europepmc_fulltext"
        if pmc is None:
            raise FetchError(f"PMC returned no full text for PMC{bare}")
        text = pmc.text
    else:
        pmid_used = bare
        pmcid = _pmid_to_pmcid(bare)
        if pmcid:
            pmc = _fetch_pmc_fulltext(pmcid)
            source = "pmc_fulltext"
            if pmc is not None:
                ncbi_supp_hrefs = pmc.supplementary_hrefs
            if pmc is None or not pmc.has_body:
                epmc = _europepmc_body(pmcid)
                if epmc is not None:
                    pmc, source = epmc, "europepmc_fulltext"
        # No PMCID, or PMC/Europe-PMC gave only an abstract: get the PubMed
        # abstract (and its DOI) and try a DOI-based Europe PMC full-text lookup,
        # which reaches bioRxiv/medRxiv and other preprints with no PMCID.
        if pmc is None or not pmc.has_body:
            abstract_text, doi = _fetch_pubmed_abstract(bare)
            epmc, epmc_pmcid = _fetch_europepmc_by_doi(doi) if doi else (None, None)
            if epmc is not None and epmc.has_body:
                pmc, source = epmc, "europepmc_fulltext"
                # A DOI that resolves to a PMC article gives us a PMCID even when
                # elink didn't — capture it so supplementary tables are still fetched.
                if epmc_pmcid and not pmcid:
                    pmcid = epmc_pmcid
                text = pmc.text
            else:
                text = pmc.text if pmc is not None else abstract_text
                source = "pmc_fulltext" if (pmc is not None and pmcid) else "pubmed_abstract"
        else:
            text = pmc.text

    has_body = pmc is not None and pmc.has_body
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
    return paper
