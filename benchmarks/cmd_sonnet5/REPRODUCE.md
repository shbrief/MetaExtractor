# Reproducing the cMD benchmark

Extraction retrieves papers live, so a re-run at a later date can retrieve different text
(see `MANUSCRIPT.md` §3.2); from `out_v3` on, each study's retrieval is frozen once and
reused by every extraction. Scoring, harmonization, aggregation, and figures are
deterministic given a committed run tree (outputs and `crosswalks/`).

## 1. Environment

```bash
git checkout bench-v3            # extraction snapshot for out_v3 (bench-v2 = out_v2)
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev,supplementary,linkml]"
# exact versions used: benchmarks/cmd_sonnet5/requirements-lock.txt (Python 3.14.0)

git clone https://github.com/waldronlab/curatedMetagenomicDataCuration
git -C curatedMetagenomicDataCuration checkout 41271711178d3b46cc5c8d93e9664be8531973ce
export CMD_CURATION_DIR=$PWD/curatedMetagenomicDataCuration
export ANTHROPIC_API_KEY=...     # or pass --api-key file:PATH
cd benchmarks/cmd_sonnet5
```

Optional checks that the inputs match the run (values are recorded in `out_v2/ledger.jsonl`):

```bash
python select_studies.py /tmp/manifest.json && diff <(python -m json.tool manifest.json) <(python -m json.tool /tmp/manifest.json)
shasum -a 256 cmd.clean.linkml.yaml manifest.json age_rules_cmd.json
# cmd.clean.linkml.yaml is regenerated from the cMD LinkML schema with:
#   python make_clean_schema.py --src /path/to/cmd.linkml.yaml
```

## 2. Frozen retrieval, then extraction (paid API calls)

```bash
python run_frozen.py fetch --out out_v3        # each study retrieved once -> out_v3/_fetch/
python run_frozen.py run   --out out_v3 --workers 4
python run_frozen.py verify --out out_v3
```

`fetch` retries a retrieval that has no article body and records every attempt in
`fetch_ledger.jsonl`. `run` refuses a working tree with modified tracked files, a tree
without a frozen retrieval for every study, and a tree that already holds extraction
outputs; every extraction reads the frozen retrieval (`--fetch-cache ... --require-fetch-cache`),
so no model sees a different text than another. `--resume` continues an interrupted tree
only from the same commit. A response that stops at the output cap is re-requested with a
doubled cap (up to 64,000 tokens); each call's stop reason is in `<study>.meta.json`.

The frozen retrieval of `out_v2` was not saved (that run fetched live per extraction).

## 3. Harmonization crosswalks

Requires MetaHarmonizer v0.4.1 and the field corpora (`harmonize/disease_corpus_v041.csv`
is rebuilt by `harmonize/build_disease_v041.py`; the NCIt treatment corpus is located with
`METAHARMONIZER_ONTOLOGIES_DIR`).

```bash
export METAHARMONIZER_ONTOLOGIES_DIR=/path/to/MetaHarmonizer/data/corpus/retrieved_ontologies
python run_frozen.py harmonize --out out_v3    # out_v3/crosswalks/crosswalk_*.csv (committed)
```

## 4. Scoring and tables (no API calls)

```bash
python run_frozen.py eval --out out_v3          # per-run summary.json, REPORT.md, cells.tsv
python run_frozen.py aggregate --out out_v3     # aggregate_v2.json, AGGREGATE.md
```

Scores are post-harmonization only (see `README.md`, "Scoring in brief"); `eval` warns when
an extracted term is missing from the crosswalks.

## 5. Figures

```bash
cd ../.. && python figures/make_figures.py --tree benchmarks/cmd_sonnet5/out_v3
```
