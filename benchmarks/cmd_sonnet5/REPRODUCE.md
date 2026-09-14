# Reproducing the cMD benchmark

Extraction retrieves papers live, so a re-run at a later date can retrieve different text
(see `MANUSCRIPT.md` §3.2). Scoring, harmonization, aggregation, and figures are
deterministic given the committed `out_v2/` outputs.

## 1. Environment

```bash
git checkout bench-v2            # extraction snapshot (commit be6a7c1); use for step 2
# steps 3–5 use the analysis commit that added out_v2/ (scoring of failed extractions,
# harmonization reporting, figures); check it out after extraction
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

## 2. Extraction (paid API calls; ≈ US$14 at 2026-06-24 list prices)

```bash
python run_frozen.py run --out out_v2_rerun --workers 4
python run_frozen.py verify --out out_v2_rerun
```

`run` refuses a working tree with modified tracked files and a non-empty output
directory. `--resume` continues an interrupted tree only from the same commit.

## 3. Scoring and tables (no API calls)

```bash
python run_frozen.py eval --out out_v2          # per-run summary.json, REPORT.md, cells.tsv
python run_frozen.py aggregate --out out_v2     # aggregate_v2.json, AGGREGATE.md
```

## 4. Ontology harmonization

Requires MetaHarmonizer v0.4.1 and the field corpora (`harmonize/disease_corpus_v041.csv`
is rebuilt by `harmonize/build_disease_v041.py`; the NCIt treatment corpus is located with
`METAHARMONIZER_ONTOLOGIES_DIR`).

```bash
export METAHARMONIZER_ONTOLOGIES_DIR=/path/to/MetaHarmonizer/data/corpus/retrieved_ontologies
python harmonize/regen_crosswalks.py --tree out_v2   # crosswalk_*.csv (committed)
python run_frozen.py harmonize --out out_v2          # harmonization.json, harmonization.md
```

## 5. Figures

```bash
cd ../.. && python figures/make_figures.py --tree benchmarks/cmd_sonnet5/out_v2
```
