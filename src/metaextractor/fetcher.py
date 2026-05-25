"""Fetch paper text from NCBI given a PMID or PMCID.

Strategy:
  1. If given a PMID, ask elink for an associated PMCID.
  2. If a PMCID exists, efetch the full-text XML from PMC and flatten to text.
  3. Otherwise, efetch the PubMed abstract (title + abstract + journal).

Uses stdlib urllib so we don't add a runtime dependency.
"""
from __future__ import annotations

import re
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
PMC_BIN = "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{bare}/bin/{name}"
USER_AGENT = "metaextractor/0.1 (+https://github.com/OmicsMLRepo)"
XLINK_HREF = "{http://www.w3.org/1999/xlink}href"


class FetchError(RuntimeError):
    pass


@dataclass
class FetchedPaper:
    text: str
    source: str  # "pmc_fulltext" | "pubmed_abstract"
    pmid: str | None
    pmcid: str | None
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


def _http_get(url: str, timeout: float = 30.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _pmid_to_pmcid(pmid: str) -> str | None:
    url = f"{EUTILS}/elink.fcgi?" + urllib.parse.urlencode(
        {"dbfrom": "pubmed", "db": "pmc", "id": pmid, "retmode": "xml"}
    )
    root = ET.fromstring(_http_get(url))
    link = root.find(".//LinkSetDb/Link/Id")
    return link.text if link is not None and link.text else None


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


def _fetch_pmc_fulltext(pmcid: str) -> _PmcFullText | None:
    url = f"{EUTILS}/efetch.fcgi?" + urllib.parse.urlencode(
        {"db": "pmc", "id": pmcid, "retmode": "xml"}
    )
    try:
        data = _http_get(url)
    except Exception:
        return None
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        return None
    article = root.find(".//article")
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
    if body is not None:
        sections.append("BODY: " + _flatten_xml(body))
    if not sections:
        return None
    return _PmcFullText(
        text="\n\n".join(sections),
        supplementary_hrefs=_extract_supplementary_hrefs(article, pmcid),
    )


def _fetch_pubmed_abstract(pmid: str) -> str:
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
    return (
        f"TITLE: {title.strip()}\n"
        f"JOURNAL: {journal.strip()} ({year})\n\n"
        f"ABSTRACT:\n{abstract}"
    )


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

    if kind == "pmcid":
        pmcid = bare
        pmc = _fetch_pmc_fulltext(bare)
        if pmc is None:
            raise FetchError(f"PMC returned no full text for PMC{bare}")
        text = pmc.text
        source = "pmc_fulltext"
    else:
        pmid_used = bare
        pmcid = _pmid_to_pmcid(bare)
        if pmcid:
            pmc = _fetch_pmc_fulltext(pmcid)
        if pmc is not None:
            text = pmc.text
            source = "pmc_fulltext"
        else:
            text = _fetch_pubmed_abstract(bare)
            source = "pubmed_abstract"

    paper = FetchedPaper(text=text, source=source, pmid=pmid_used, pmcid=pmcid)

    if include_supplementary and pmcid:
        from metaextractor.supplementary import fetch_supplementary
        jats_hrefs = pmc.supplementary_hrefs if pmc is not None else None
        supp = fetch_supplementary(pmcid, jats_hrefs=jats_hrefs)
        paper.supplementary_included = supp.included
        paper.supplementary_skipped = supp.skipped
        paper.supplementary_tables = list(supp.tables)
        if supp.text:
            paper.text = f"{paper.text}\n\n{supp.text}"
    return paper
