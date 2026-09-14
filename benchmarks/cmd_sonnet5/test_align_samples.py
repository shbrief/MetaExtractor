"""align_samples matches extracted samples to gold rows by a shared unique id.

The key may be a single column or an ordered fallback chain
(``ncbi_accession → sample_id → subject_id``); each study aligns on the first
candidate it can match on, so a study keyed on accession and one keyed only on
sample_id are each handled. These tests pin that precedence and the returned
``used_key``.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench import align_samples  # noqa: E402


def _ext(*ids, key="ncbi_accession"):
    return [{key: i, "age": str(30 + n)} for n, i in enumerate(ids)]


def test_single_key_reorders_to_gold_order():
    ext = _ext("ERR3", "ERR1", "ERR2")
    gold = [{"ncbi_accession": "ERR1"}, {"ncbi_accession": "ERR2"}, {"ncbi_accession": "ERR3"}]
    a_ext, a_gold, nmatch, ngold, next_, used = align_samples(ext, gold, "ncbi_accession")
    assert used == "ncbi_accession"
    assert nmatch == 3 and ngold == 3 and next_ == 3
    assert [s["ncbi_accession"] for s in a_ext] == ["ERR1", "ERR2", "ERR3"]


def test_fallback_chain_skips_key_with_no_overlap():
    # Extraction carries no ncbi_accession overlap but matches on sample_id
    # (the PasolliE case: gold SRR run vs extracted SRS sample, sample_id equal).
    ext = [{"ncbi_accession": "SRS9", "sample_id": "A01"},
           {"ncbi_accession": "SRS8", "sample_id": "A02"}]
    gold = [{"ncbi_accession": "SRR1", "sample_id": "A02"},
            {"ncbi_accession": "SRR2", "sample_id": "A01"}]
    a_ext, a_gold, nmatch, ngold, next_, used = align_samples(
        ext, gold, ["ncbi_accession", "sample_id", "subject_id"])
    assert used == "sample_id"          # first candidate with any overlap wins
    assert nmatch == 2
    assert [s["sample_id"] for s in a_ext] == ["A02", "A01"]  # reordered to gold


def test_first_matching_key_wins_over_later_candidates():
    # Both accession and sample_id could match; accession is tried first.
    ext = [{"ncbi_accession": "ERR1", "sample_id": "S1"}]
    gold = [{"ncbi_accession": "ERR1", "sample_id": "S1"}]
    *_, used = align_samples(ext, gold, ["ncbi_accession", "sample_id"])
    assert used == "ncbi_accession"


def test_comma_string_is_parsed_as_chain():
    ext = [{"ncbi_accession": "na", "sample_id": "S1"}]
    gold = [{"ncbi_accession": "NA", "sample_id": "S1"}]
    *_, used = align_samples(ext, gold, "ncbi_accession,sample_id")
    assert used == "sample_id"          # "na"/"NA" are treated as empty by _acc_key


def test_no_shared_id_yields_no_match():
    ext = [{"ncbi_accession": "ERR9", "sample_id": "X"}]
    gold = [{"ncbi_accession": "ERR1", "sample_id": "Y"}]
    a_ext, a_gold, nmatch, ngold, next_, used = align_samples(
        ext, gold, ["ncbi_accession", "sample_id", "subject_id"])
    assert used is None
    assert nmatch == 0 and a_ext == [] and a_gold == []
    assert ngold == 1 and next_ == 1


def test_first_run_token_matches_semicolon_pooled_gold():
    # LiSS: gold pools runs under ';'; _acc_key joins on the first token.
    ext = [{"ncbi_accession": "ERR100"}]
    gold = [{"ncbi_accession": "ERR100;ERR101;ERR102"}]
    *_, nmatch, _ng, _ne, used = align_samples(ext, gold, "ncbi_accession")
    assert used == "ncbi_accession" and nmatch == 1
