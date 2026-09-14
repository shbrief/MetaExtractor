"""align_by_identity joins extracted records to gold rows one-to-one.

Pins the review's failure cases for the old first-wins join: duplicated keys,
pooled accessions, compound keys, key choice by match count, and diagnostics.
"""
from metaextractor.alignment import align_by_identity, key_tokens
from metaextractor.evaluation import evaluate


def _acc(*ids):
    return [{"ncbi_accession": i, "age": str(30 + n)} for n, i in enumerate(ids)]


def test_reorders_to_gold_order():
    ext = _acc("ERR3", "ERR1", "ERR2")
    gold = [{"ncbi_accession": "ERR1"}, {"ncbi_accession": "ERR2"}, {"ncbi_accession": "ERR3"}]
    al = align_by_identity(ext, gold, "ncbi_accession")
    assert al.key_used == "ncbi_accession"
    assert al.pairs == [(0, 1), (1, 2), (2, 0)]
    assert al.matched == 3 and not al.unmatched_gold


def test_duplicate_key_is_ambiguous_not_first_wins():
    # Review example: two extracted rows share subject_id=A (ages 10 / 20).
    ext = [{"subject_id": "A", "age": "10"}, {"subject_id": "A", "age": "20"}]
    gold = [{"subject_id": "A", "age": "10"}, {"subject_id": "A", "age": "20"}]
    al = align_by_identity(ext, gold, "subject_id")
    assert al.matched == 0
    assert al.ambiguous_gold == [0, 1]
    assert al.duplicate_ext_records == 2


def test_gold_rows_claiming_one_record_are_ambiguous():
    ext = [{"subject_id": "A"}]
    gold = [{"subject_id": "A"}, {"subject_id": "A"}]
    al = align_by_identity(ext, gold, "subject_id")
    assert al.matched == 0 and al.ambiguous_gold == [0, 1]
    assert al.ext_in_conflict == 1


def test_pooled_gold_accessions_are_reported_not_truncated():
    ext = _acc("SRR1", "SRR2", "SRR3")
    gold = [{"ncbi_accession": "SRR1;SRR2"}, {"ncbi_accession": "SRR3"}]
    al = align_by_identity(ext, gold, "ncbi_accession")
    assert al.pooled_gold == [0]
    assert al.pairs == [(1, 2)]
    assert al.ext_in_conflict == 2


def test_compound_key_separates_timepoints():
    ext = [{"subject_id": "A", "timepoint": "t1", "v": 1},
           {"subject_id": "A", "timepoint": "t2", "v": 2}]
    gold = [{"subject_id": "A", "timepoint": "t2"}, {"subject_id": "A", "timepoint": "t1"}]
    assert align_by_identity(ext, gold, "subject_id").matched == 0
    al = align_by_identity(ext, gold, "subject_id,subject_id+timepoint")
    assert al.key_used == "subject_id+timepoint"
    assert al.pairs == [(0, 1), (1, 0)]


def test_compound_key_requires_every_part():
    assert key_tokens({"subject_id": "A", "timepoint": "NA"}, "subject_id+timepoint") == set()


def test_candidate_with_most_matches_wins():
    ext = [{"ncbi_accession": "ERR1", "sample_id": "S1"},
           {"ncbi_accession": "", "sample_id": "S2"},
           {"ncbi_accession": "", "sample_id": "S3"}]
    gold = [{"ncbi_accession": "ERR1", "sample_id": "S1"},
            {"ncbi_accession": "ERR9", "sample_id": "S2"},
            {"ncbi_accession": "ERR8", "sample_id": "S3"}]
    al = align_by_identity(ext, gold, "ncbi_accession,sample_id")
    assert al.key_used == "sample_id"
    assert al.candidate_matches == {"ncbi_accession": 1, "sample_id": 3}


def test_extra_records_split_by_key_presence():
    ext = _acc("ERR1", "ERR7") + [{"ncbi_accession": "not_reported"}]
    gold = [{"ncbi_accession": "ERR1"}, {"ncbi_accession": "ERR2"}]
    al = align_by_identity(ext, gold, "ncbi_accession")
    assert al.unmatched_gold == [1]
    assert al.unmatched_ext_with_key == 1
    assert al.unmatched_ext_without_key == 1


def test_no_shared_id_leaves_all_gold_unmatched():
    ext = [{"sample_id": "X1"}]
    gold = [{"sample_id": "G1"}, {"sample_id": "G2"}]
    al = align_by_identity(ext, gold, "ncbi_accession,sample_id")
    assert al.key_used is None and al.unmatched_gold == [0, 1]
    assert al.unmatched_ext_with_key == 1


def test_end_to_end_scoring_counts_unmatched_gold_as_fn():
    ext = [{"ncbi_accession": "ERR2", "disease": "healthy"}]
    gold = [{"ncbi_accession": "ERR1", "disease": "T2D"},
            {"ncbi_accession": "ERR2", "disease": "healthy"}]
    al = align_by_identity(ext, gold, "ncbi_accession")
    g, e = al.end_to_end_lists(gold, ext)
    res = evaluate({"granularity": "sample_level", "fields": {}, "samples": e}, g,
                   {"disease": "disease"})
    fm = res.per_field["disease"]
    assert (fm.tp_correct, fm.fn) == (1, 1)
    gm, em = al.matched_lists(gold, ext)
    fm2 = evaluate({"granularity": "sample_level", "fields": {}, "samples": em}, gm,
                   {"disease": "disease"}).per_field["disease"]
    assert (fm2.tp_correct, fm2.fn) == (1, 0)
