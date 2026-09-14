# MetaExtractor × curatedMetagenomicData benchmark

Evaluates MetaExtractor against the curated `*_sample.tsv` tables of
[curatedMetagenomicDataCuration](https://github.com/waldronlab/curatedMetagenomicDataCuration)
on ten studies (1,089 curated samples), with two models (`claude-sonnet-5`,
`claude-haiku-4-5`) and three repeated runs each. The analysis reported in
`MANUSCRIPT.md` is the frozen run in [`out_v2/`](out_v2/), extracted at tag `bench-v2`.
Exact commands are in [`REPRODUCE.md`](REPRODUCE.md).

## Contents

| path | purpose |
| --- | --- |
| `select_studies.py` | seed-42 draw of ten studies → `manifest.json` (gold paths relative to `$CMD_CURATION_DIR`) |
| `make_clean_schema.py` | cMD LinkML → `cmd.clean.linkml.yaml` (dynamic enums → string; `scope` annotations) |
| `age_rules_cmd.json` | age-bound rule configuration and the source of each bound |
| `run_frozen.py` | fresh extractions into an empty tree, append-only `ledger.jsonl`, eval/harmonize/aggregate/verify |
| `bench.py` | `eval` (end-to-end, conditional, positional joins) and `harmonize` (ontology scoring) |
| `aggregate.py` | repeat-level tables, per-study × repeat errors, bootstrap interval, ledger summary |
| `harmonize/` | crosswalk helpers (`crosswalk.py`), crosswalk regeneration, corpora and their build scripts |
| `bench_paths.py` | portable paths, checksums, git state |
| `requirements-lock.txt` | environment at the frozen run |

## Scoring in brief

- **Cells**: TN / FN / FP / TPc (values match) / TPw (values differ); content fields and
  identifier fields are pooled separately.
- **Value-aware** precision/recall count only TPc as a hit; **presence** precision/recall
  count TPc + TPw. Presence metrics describe reporting status, not correctness.
- **End-to-end** (primary): extracted records are aligned one-to-one to curated rows on
  `ncbi_accession`, `sample_id`, or `subject_id` (`metaextractor.alignment`); every curated
  row is scored, so unmatched rows count as false negatives and a failed extraction counts
  as producing no records. **Conditional**: matched rows only. **Positional**: legacy
  comparison only.
- **Harmonization**: identity-matched cells where both sides report a value and the curated
  row has an ontology id; raw string accuracy and exact code-set correctness on the same
  cells, concept-level precision/recall, and any-shared-code as a supplementary figure.

## Output layout (`out_v2/`)

```
ledger.jsonl                    one line per attempt (status, UTC times, checksums, git)
runs.jsonl                      run-level settings
<model>_r<k>/<study>.json       extraction result (incl. sample_provenance)
<model>_r<k>/<study>.csv        flat CSV with per-cell sources
<model>_r<k>/<study>.meta.json  request settings, returned model ids, usage, cost, retrieval attempts
<model>_r<k>/<study>.attemptN.log  stderr of each attempt
<model>_r<k>/<study>.text.txt   text sent to the model (checksummed; not committed)
<model>_r<k>/<study>.cells.tsv  per-cell decisions (end-to-end join)
<model>_r<k>/summary.json, REPORT.md
aggregate_v2.json, AGGREGATE.md, harmonization.json, harmonization.md
```

Earlier trees (`out_ms_refined/`, and the git-ignored `out_ms/`, `out/`, `out_haiku/`) were
produced by superseded drivers and scoring rules; see git history before tag `bench-v2`.
The disease corpus (`harmonize/disease_corpus_v041.csv`, 82 MB) is git-ignored and is
rebuilt by `harmonize/build_disease_v041.py`.
