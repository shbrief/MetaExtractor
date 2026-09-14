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
| `run_frozen.py` | `fetch` (one frozen retrieval per study), `run` (fresh extractions, append-only `ledger.jsonl`), `harmonize`, `eval`, `aggregate`, `verify` |
| `bench.py` | `eval`: post-harmonization scores, all curated and matched |
| `aggregate.py` | repeat-level tables, harmonized-field scores, per-study × repeat errors, bootstrap interval, ledger summary |
| `harmonize/` | `crosswalk.py` (post-harmonization comparison), crosswalk regeneration, corpora and their build scripts |
| `bench_paths.py` | portable paths, checksums, git state |
| `requirements-lock.txt` | environment at the frozen run |

## Scoring in brief

Values are scored **after harmonization**. All normalization is MetaHarmonizer's; the
scorer adds none.

- **Harmonized fields** are those with a crosswalk in `TREE/crosswalks/` (currently
  disease, body_site, treatment). A cell is correct when every extracted term maps and the
  extracted code set equals the curated `<field>_ontology_term_id` set; where the curated
  row has no id, both values are mapped through the same crosswalk and compared as code
  sets. Adding a corpus and regenerating crosswalks brings another field into scoring.
- **Other fields** are compared as extracted (case and surrounding whitespace ignored, 5%
  numeric tolerance).
- **Cells**: TN / FN / FP / TPc (harmonized values match) / TPw (they differ). Precision =
  TPc/(TPc+TPw+FP), recall = TPc/(TPc+TPw+FN); content and identifier fields are pooled
  separately.
- **Score all curated**: extracted records are aligned one-to-one to curated rows on
  `ncbi_accession`, `sample_id`, or `subject_id` (`metaextractor.alignment`); every curated
  row is scored, so unmatched rows count as false negatives and a failed extraction counts
  as producing no records. **Score matched**: the identifier-matched rows only.

## Output layout (`out_v2/`, `out_v3/`)

```
_fetch/<study>/fetched.json     frozen retrieval: provenance, rungs, checksums (out_v3 onward)
_fetch/<study>/text.txt, tables.json   the retrieval itself (checksummed; not committed)
fetch_ledger.jsonl              one line per fetch attempt
crosswalks/crosswalk_*.csv      MetaHarmonizer crosswalks for this tree's terms
ledger.jsonl                    one line per attempt (status, UTC times, checksums, git)
runs.jsonl                      run-level settings
<model>_r<k>/<study>.json       extraction result (incl. sample_provenance)
<model>_r<k>/<study>.csv        flat CSV with per-cell sources
<model>_r<k>/<study>.meta.json  request settings, per-call stop reasons, usage (failed runs too), cost, retrieval
<model>_r<k>/<study>.attemptN.log  stderr of each attempt
<model>_r<k>/<study>.text.txt   text sent to the model (checksummed; not committed)
<model>_r<k>/<study>.cells.tsv  per-cell decisions (all curated), with the harmonized values compared
<model>_r<k>/summary.json, REPORT.md
aggregate_v2.json, AGGREGATE.md
```

Earlier trees (`out_ms_refined/`, and the git-ignored `out_ms/`, `out/`, `out_haiku/`) were
produced by superseded drivers and scoring rules; see git history before tag `bench-v2`.
The disease corpus (`harmonize/disease_corpus_v041.csv`, 82 MB) is git-ignored and is
rebuilt by `harmonize/build_disease_v041.py`.
