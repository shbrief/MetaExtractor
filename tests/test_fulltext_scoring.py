"""Best-of full-text scoring: `_score_fulltext` must rank by article-narrative
quality, not raw length, so a long reference list or taxonomy/abundance table
cannot beat a real (possibly shorter) article body."""
from metaextractor.fetcher import _score_fulltext, _strip_references

_PROSE_BODY = (
    "Introduction\nWe studied the gut microbiome. " + "Prose sentence here. " * 60
    + "\nMethods\nWe sequenced samples. " + "Prose sentence here. " * 60
    + "\nResults\nWe found associations. " + "Prose sentence here. " * 60
    + "\nDiscussion\nThese findings suggest. " + "Prose sentence here. " * 60
    + "\nData availability\nData are in the ENA."
)


def test_prose_body_beats_longer_taxonomy_table():
    # A taxonomy/abundance dump that is *longer* than the prose body.
    taxa = "\n".join(
        f"k__Bacteria|p__Firmicutes|c__Clostridia|o__o|f__f|g__g{i}|s__s{i}\t{0.1*i}\t{0.2*i}"
        for i in range(1200)
    )
    assert len(taxa) > len(_PROSE_BODY)                       # longer by bulk
    assert _score_fulltext(_PROSE_BODY, "unpaywall_pdf") > _score_fulltext(taxa, "unpaywall_pdf")


def test_prose_body_beats_longer_reference_list():
    refs = "References\n" + "\n".join(
        f"{i}. Author A, Author B. A study of things. Journal {i}; {i}:1-10." for i in range(400))
    assert len(refs) > len(_PROSE_BODY)
    assert _score_fulltext(_PROSE_BODY, "pmc_fulltext") > _score_fulltext(refs, "pmc_fulltext")


def test_reference_stripping_only_affects_tail():
    body = "Introduction\nReal narrative body. " * 50
    tail = "\nReferences\n" + "1. Cite. " * 500
    # Stripping removes the citation tail (back half), keeping the narrative.
    stripped = _strip_references(body + tail)
    assert "Real narrative body." in stripped
    assert "1. Cite." not in stripped


def test_substantive_structured_body_clears_good_threshold():
    from metaextractor.fetcher import _GOOD_FULLTEXT_SCORE
    assert _score_fulltext(_PROSE_BODY, "pmc_fulltext") >= _GOOD_FULLTEXT_SCORE


def test_abstract_stub_below_good_threshold():
    from metaextractor.fetcher import _GOOD_FULLTEXT_SCORE
    stub = "TITLE: X\n\nABSTRACT: A short abstract with no sections."
    assert _score_fulltext(stub, "pubmed_abstract") < _GOOD_FULLTEXT_SCORE
