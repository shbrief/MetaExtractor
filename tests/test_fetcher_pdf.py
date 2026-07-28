"""Europe PMC free rendered-PDF fallback for non-Open-Access articles.

A non-OA PMC record returns abstract-only from every structured XML endpoint,
but Europe PMC serves a free rendered PDF that carries the body. The fetcher
must fall back to it (offline here — network calls are monkeypatched)."""
from __future__ import annotations

from metaextractor import fetcher


def test_europepmc_pdf_used_when_xml_is_abstract_only(monkeypatch):
    # NCBI PMC returns a body-less (abstract-only) record; EPMC fullTextXML fails.
    monkeypatch.setattr(
        fetcher, "_fetch_pmc_fulltext",
        lambda pmcid: fetcher._PmcFullText(
            text="TITLE: x\n\nABSTRACT: short", supplementary_hrefs=[], has_body=False),
    )
    monkeypatch.setattr(fetcher, "_fetch_europepmc_fulltext", lambda pmcid: None)
    body = "FULL TEXT BODY with accession PRJEB7369. " * 100
    monkeypatch.setattr(fetcher, "_fetch_europepmc_pdf", lambda pmcid: body)

    paper = fetcher.fetch_paper(
        "PMC4576037", include_supplementary=False, include_sra_manifest=False)
    assert paper.source == "europepmc_pdf"
    assert paper.has_body is True
    assert paper.text == body


def test_europepmc_pdf_not_used_when_shorter_than_abstract(monkeypatch):
    # A tiny PDF (or extraction failure yielding little text) must not replace a
    # real abstract — the length guard protects against that.
    monkeypatch.setattr(
        fetcher, "_fetch_pmc_fulltext",
        lambda pmcid: fetcher._PmcFullText(
            text="TITLE: x\n\nABSTRACT: " + "a" * 2000,
            supplementary_hrefs=[], has_body=False),
    )
    monkeypatch.setattr(fetcher, "_fetch_europepmc_fulltext", lambda pmcid: None)
    monkeypatch.setattr(fetcher, "_fetch_europepmc_pdf", lambda pmcid: "tiny")

    paper = fetcher.fetch_paper(
        "PMC4576037", include_supplementary=False, include_sra_manifest=False)
    assert paper.source == "pmc_fulltext"
    assert paper.has_body is False


def test_europepmc_pdf_rejects_non_pdf_response(monkeypatch):
    # The render URL can return an HTML paywall/landing page; only real %PDF bytes
    # are accepted.
    monkeypatch.setattr(
        fetcher, "_http_get",
        lambda url, timeout=90: b"<!DOCTYPE html><html>subscription required</html>")
    assert fetcher._fetch_europepmc_pdf("PMC4576037") is None


def test_europepmc_pdf_none_without_pmcid():
    assert fetcher._fetch_europepmc_pdf(None) is None


# --- Unpaywall rung (publisher / repository OA, no PMC record) ---------------

def test_unpaywall_fetches_publisher_oa_pdf(monkeypatch):
    import json

    def fake_get(url, timeout=30):
        if "unpaywall" in url:
            return json.dumps({
                "best_oa_location": {"url_for_pdf": "https://nature.com/x.pdf"},
                "oa_locations": [],
            }).encode()
        return b"%PDF-1.5 ..."

    monkeypatch.setattr(fetcher, "_http_get", fake_get)
    monkeypatch.setattr(fetcher, "_pdf_bytes_to_text", lambda data: "BODY with PRJNA289586")
    assert fetcher._fetch_oa_pdf_via_unpaywall("10.1038/x") == "BODY with PRJNA289586"


def test_unpaywall_none_without_doi():
    assert fetcher._fetch_oa_pdf_via_unpaywall(None) is None


def test_unpaywall_skips_landing_page_without_pdf(monkeypatch):
    import json
    monkeypatch.setattr(
        fetcher, "_http_get",
        lambda url, timeout=30: json.dumps(
            {"best_oa_location": {"url_for_pdf": None, "url": "https://zenodo.org/record/1"},
             "oa_locations": []}).encode())
    assert fetcher._fetch_oa_pdf_via_unpaywall("10.1/x") is None


def test_ladder_falls_through_epmc_pdf_to_unpaywall(monkeypatch):
    # No PMCID (publisher-only OA): abstract fetched, EPMC PDF unavailable, then
    # Unpaywall supplies the body -> source is unpaywall_pdf.
    monkeypatch.setattr(fetcher, "_pmid_to_pmcid", lambda pmid: None)
    monkeypatch.setattr(
        fetcher, "_fetch_pubmed_abstract",
        lambda pmid: ("TITLE: x\n\nABSTRACT: short", "10.1038/nmicrobiol.2016.180"))
    monkeypatch.setattr(fetcher, "_fetch_europepmc_by_doi", lambda doi: (None, None))
    monkeypatch.setattr(fetcher, "_fetch_europepmc_pdf", lambda pmcid: None)
    body = "FULL TEXT BODY with PRJNA289586. " * 100
    monkeypatch.setattr(fetcher, "_fetch_oa_pdf_via_unpaywall", lambda doi: body)

    paper = fetcher.fetch_paper(
        "27723761", include_supplementary=False, include_sra_manifest=False)
    assert paper.source == "unpaywall_pdf"
    assert paper.has_body is True
    assert paper.text == body
