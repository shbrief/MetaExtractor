"""fetcher full-text fallback ladder — offline, with _http_get mocked by URL.

Verifies that when NCBI PMC has no <body>, the fetcher falls back to Europe PMC
fullTextXML (by PMCID, then by DOI for preprints) so the LLM gets article prose
rather than an abstract; and that it degrades to the PubMed abstract only when no
full text is reachable anywhere.
"""
from __future__ import annotations

import urllib.error

import pytest

from metaextractor import fetcher


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Retry/backoff paths call time.sleep; keep the suite instant."""
    monkeypatch.setattr(fetcher.time, "sleep", lambda s: None)


def test_http_get_retries_on_rate_limit(monkeypatch):
    """A 429 burst (NCBI eutils >3 req/s) is retried, not raised, so concurrent
    fetches don't die with an uncaught HTTPError."""
    calls = {"n": 0}

    class _Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"OK"

    def fake_urlopen(req, timeout=30.0):
        calls["n"] += 1
        if calls["n"] < 3:  # fail twice, then succeed
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many", {}, None)
        return _Resp()

    monkeypatch.setattr(fetcher.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(fetcher.time, "sleep", lambda s: None)
    assert fetcher._http_get("https://example/x") == b"OK"
    assert calls["n"] == 3


def test_http_get_raises_on_non_retryable(monkeypatch):
    """A 404 is not retried — it raises immediately."""
    def fake_urlopen(req, timeout=30.0):
        raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(fetcher.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(fetcher.time, "sleep", lambda s: None)
    with pytest.raises(urllib.error.HTTPError):
        fetcher._http_get("https://example/x")

PMC_WITH_BODY = (
    b"<pmc-articleset><article><front><article-meta><title-group>"
    b"<article-title>The Title</article-title></title-group>"
    b"<abstract><p>the abstract</p></abstract></article-meta></front>"
    b"<body><sec><p>NCBI full body sentence.</p></sec></body></article></pmc-articleset>"
)
PMC_ABSTRACT_ONLY = (
    b"<pmc-articleset><article><front><article-meta><title-group>"
    b"<article-title>The Title</article-title></title-group>"
    b"<abstract><p>the abstract</p></abstract></article-meta></front></article></pmc-articleset>"
)
EPMC_WITH_BODY = (  # Europe PMC returns <article> as the root, not wrapped
    b"<article><front><article-meta><title-group>"
    b"<article-title>The Title</article-title></title-group>"
    b"<abstract><p>the abstract</p></abstract></article-meta></front>"
    b"<body><sec><p>Europe PMC body sentence.</p></sec></body></article>"
)
ELINK_PMC = (
    b"<eLinkResult><LinkSet><LinkSetDb><LinkName>pubmed_pmc</LinkName>"
    b"<Link><Id>777</Id></Link></LinkSetDb></LinkSet></eLinkResult>"
)
ELINK_NONE = b"<eLinkResult><LinkSet></LinkSet></eLinkResult>"
PUBMED_ABS = (
    b"<PubmedArticleSet><PubmedArticle><MedlineCitation><Article>"
    b"<ArticleTitle>The Title</ArticleTitle><Journal><Title>J</Title></Journal>"
    b"<Abstract><AbstractText>the abstract</AbstractText></Abstract></Article>"
    b"</MedlineCitation><PubmedData><ArticleIdList>"
    b'<ArticleId IdType="doi">10.1101/2020.01.01.123</ArticleId>'
    b"</ArticleIdList></PubmedData></PubmedArticle></PubmedArticleSet>"
)
EPMC_SEARCH_PPR = (
    b'{"resultList":{"result":[{"source":"PPR","id":"PPR55","inEPMC":"Y"}]}}'
)


def _router(routes: dict[str, bytes]):
    """Build a fake _http_get that returns the first route whose key is in the URL."""
    def fake(url: str, timeout: float = 30.0) -> bytes:
        for needle, body in routes.items():
            if needle in url:
                return body
        raise AssertionError(f"unexpected URL: {url}")
    return fake


def test_pmid_to_pmcid_retries_empty_linkset(monkeypatch):
    """elink returns an empty linkset transiently under load; _pmid_to_pmcid must
    retry rather than mistake it for 'no PMC record' (which would drop the tables)."""
    seq = [ELINK_NONE, ELINK_NONE, ELINK_PMC]  # empty twice, then the real link
    calls = {"n": 0}

    def fake(url, timeout=30.0):
        i = min(calls["n"], len(seq) - 1)
        calls["n"] += 1
        return seq[i]

    monkeypatch.setattr(fetcher, "_http_get", fake)
    assert fetcher._pmid_to_pmcid("123") == "777"
    assert calls["n"] == 3


def test_pmid_to_pmcid_no_retry_when_linkset_present(monkeypatch):
    """A linkset that exists but lacks pubmed_pmc is a genuine 'no own mirror' —
    return None immediately, without burning retries."""
    other = (
        b"<eLinkResult><LinkSet><LinkSetDb><LinkName>pubmed_pmc_refs</LinkName>"
        b"<Link><Id>999</Id></Link></LinkSetDb></LinkSet></eLinkResult>"
    )
    calls = {"n": 0}

    def fake(url, timeout=30.0):
        calls["n"] += 1
        return other

    monkeypatch.setattr(fetcher, "_http_get", fake)
    assert fetcher._pmid_to_pmcid("123") is None
    assert calls["n"] == 1  # no retry: the linkset was present


def test_pmc_body_used_directly(monkeypatch):
    monkeypatch.setattr(fetcher, "_http_get", _router({
        "elink.fcgi": ELINK_PMC,
        "db=pmc": PMC_WITH_BODY,
    }))
    p = fetcher.fetch_paper("123", include_supplementary=False)
    assert p.source == "pmc_fulltext"
    assert p.has_body is True
    assert "NCBI full body sentence." in p.text


def test_falls_back_to_europepmc_when_pmc_abstract_only(monkeypatch):
    monkeypatch.setattr(fetcher, "_http_get", _router({
        "elink.fcgi": ELINK_PMC,
        "db=pmc": PMC_ABSTRACT_ONLY,
        "fullTextXML": EPMC_WITH_BODY,
    }))
    p = fetcher.fetch_paper("123", include_supplementary=False)
    assert p.source == "europepmc_fulltext"
    assert p.has_body is True
    assert "Europe PMC body sentence." in p.text


def test_preprint_resolved_by_doi_when_no_pmcid(monkeypatch):
    monkeypatch.setattr(fetcher, "_http_get", _router({
        "elink.fcgi": ELINK_NONE,          # no PMCID
        "db=pubmed": PUBMED_ABS,           # abstract + bioRxiv DOI
        "search": EPMC_SEARCH_PPR,         # DOI -> preprint id
        "PPR55/fullTextXML": EPMC_WITH_BODY,
    }))
    p = fetcher.fetch_paper("123", include_supplementary=False)
    assert p.source == "europepmc_fulltext"
    assert p.has_body is True
    assert "Europe PMC body sentence." in p.text


def test_degrades_to_abstract_when_no_fulltext(monkeypatch):
    monkeypatch.setattr(fetcher, "_http_get", _router({
        "elink.fcgi": ELINK_NONE,
        "db=pubmed": PUBMED_ABS,
        "search": b'{"resultList":{"result":[]}}',  # DOI has no EPMC full text
    }))
    p = fetcher.fetch_paper("123", include_supplementary=False)
    assert p.source == "pubmed_abstract"
    assert p.has_body is False
    assert "the abstract" in p.text
