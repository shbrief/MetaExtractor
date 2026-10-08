# MetaExtractor

A schema-guided metadata extractor for scientific literature and sequencing archives.
Given a research paper and a target schema (JSON, YAML, or a supported subset of
LinkML), it returns structured metadata — study-level fields and, where samples can be
enumerated, one record per sample. Each study-level value carries the model's
evidence quote, section, extraction type, and confidence, and each sample cell records
its source (a table or run-manifest column, the model, or a deterministic rule).

Model calls read prose, propose field values, and infer table structure. Retrieval,
table execution, column mapping, joining, and propagation of study-level values are
deterministic. Output validation is **structural** (the result envelope): it does not
check values against the source text, the target schema's types, or its vocabularies,
so extracted values should be reviewed or harmonized downstream.

Ships with an evaluator that scores extractions against a gold-standard table.
curatedMetagenomicData (cMD) is bundled as a worked example and is the benchmark
domain (`benchmarks/cmd_sonnet5/`); the code contains some cMD-oriented pieces
(accession handling, column aliases, and an optional age-rule configuration).

## Install

```bash
pip install -e .
# PDF input:
pip install -e ".[pdf]"
# LinkML / YAML schemas:
pip install -e ".[linkml]"
# Supplementary tables (xlsx) when fetching by PMID:
pip install -e ".[supplementary]"
```

Requires `ANTHROPIC_API_KEY` in your environment (the web app also accepts a
key pasted into the browser).

### Developing

`uv.lock` pins the full development environment, which is what CI installs:

```bash
uv sync --dev          # exact locked versions
uv run pytest          # 228 tests, ~2 s, no network and no API key needed
uv run ruff check .
```

`pip install -e ".[dev]"` also works and resolves freely rather than from the
lock. Tests that reach a real network service are marked `network` and
deselected by default; run them with `pytest -m network`.

The lock constrains `anthropic` to the version both frozen benchmark trees were
produced with, so a benchmark re-run measures a code change and not an SDK
upgrade — see the comment on `[tool.uv]` in `pyproject.toml`.

## Web app

A Streamlit UI wraps the library around its three key inputs — **target study**,
**target schema**, and **API key**:

```bash
pip install -e ".[app]"
metaextract-app                 # opens http://localhost:8501
# extra args pass through to Streamlit, e.g. metaextract-app --server.port 8502
```

- **① API key** (sidebar) — paste your Anthropic key, or a reference:
  `file:~/path/to/keyfile` reads the first non-empty line of a file, and
  `env:VARNAME` reads an environment variable (same conventions as the CLI's
  `--api-key`). Whatever you provide is trimmed, so a trailing newline never
  causes a spurious `invalid x-api-key`. The value lives in the session only
  and is never written to disk; left blank, it falls back to
  `ANTHROPIC_API_KEY` / `CLAUDE_API_KEY`.
- **② Target study** — enter a PMID/PMCID to fetch from NCBI (with optional
  supplementary materials), or paste text / upload a `.txt`/`.md`/`.pdf`.
- **③ Target schema** — pick a schema **bundled with the package** (the cMD
  LinkML schema and a small study-level demo) or **upload** your own JSON /
  YAML / LinkML file. Fields preview inline before you run.

Results show granularity, per-field values with verbatim evidence, any
sample-level rows, token usage and estimated cost, plus JSON and CSV
downloads.

## CLI

```bash
# Local file:
metaextract --paper paper.txt --schema examples/schema.json --paper-id PMID:12345 --out result.json

# PMID only — fetches PMC full text (or falls back to PubMed abstract):
metaextract --paper-id 29795809 --schema examples/schema.json --out result.json

# Skip the Europe PMC supplementary fetch (default is to include xlsx/csv/tsv/pdf):
metaextract --paper-id 29795809 --schema examples/schema.json --no-supplementary

# Flat CSV alongside the JSON, with per-field provenance columns:
metaextract --paper paper.txt --schema examples/schema.json \
    --out result.json --csv result.csv --csv-provenance
```

Either `--paper` or `--paper-id` is required. When only `--paper-id` is
given, it must be a PMID or PMCID — the text is fetched via NCBI
E-utilities (PMC full text when available, otherwise the PubMed abstract).
Pass a `.pdf` to `--paper` directly if you installed the `pdf` extra.

### Useful flags

| flag | default | purpose |
|---|---|---|
| `--csv FILE`         | (off) | also write a flat CSV (row per record) |
| `--csv-provenance`   | off   | in the CSV, add per-field evidence/section/confidence columns |
| `--no-supplementary` | off   | skip the Europe PMC supplementary-materials fetch |
| `--no-sample-discovery` | off | skip the +1 discovery call that enumerates sample IDs before per-batch field extraction |
| `--model NAME`       | `claude-sonnet-4-6` | override the model |
| `--batch-size N`     | 30    | auto-batch schemas larger than N fields (each batch reuses the cached system prompt + paper) |
| `--max-tokens N`     | 16384 | per-batch response cap |

The CLI prints token usage and an estimated USD cost on stderr after each run.

## Python API

```python
from metaextractor import MetaExtractor

result = MetaExtractor().extract(
    paper_text=open("paper.txt").read(),
    schema={
        "fields": [
            {"name": "n_participants", "description": "Total enrolled.", "type": "number", "required": True},
            {"name": "study_design", "description": "Design.", "type": "enum",
             "allowed_values": ["rct", "cohort", "case_control"]},
        ]
    },
    paper_id="PMID:12345",
)

print(result.fields["n_participants"].value)
print(result.fields["n_participants"].evidence_quote)

# Sample-level extractions also populate result.samples:
for sample in result.samples:
    print(sample["sample_id"], sample["body_site"], sample["dna_extraction_kit"])
```

### Choosing or faking the model

Every model call goes through one seam, `metaextractor.model.Model`, so the
backend is a constructor argument:

```python
from metaextractor.model import AnthropicModel, MockModel

MetaExtractor(llm=AnthropicModel("claude-haiku-4-5", api_key=key))

# Offline, deterministic, no key: responses are keyed by stage, and a callable
# spec sees the request (which is how a reply can vary with the token budget).
llm = MockModel(responses={"fields": {"granularity": "study_level", "fields": {...}}})
MetaExtractor(llm=llm).extract(paper, schema)
llm.budgets()            # max_tokens per call — the retry sequence, as observed
llm.assert_not_called("table_plan")
```

`MetaExtractor(llm=...)` derives its model id from the backend, so the id used
for pricing can no longer disagree with the one actually called. Anthropic
remains the only real backend and the runtime dependencies are unchanged; the
seam exists for testability and for the cheap-judgment layer to share.

## Schema formats

The `--schema` argument accepts three formats; the loader auto-detects:

1. **Native JSON** — the canonical form documented below.
2. **Native YAML** — same shape as the JSON form, just YAML-encoded.
3. **LinkML YAML** — auto-detected when the file contains top-level
   `classes` / `slots` / `enums`. Slots of the (single) class become
   fields; `range:` resolves to `number` / `string` / `boolean`, and
   ranges that name an enum (`<name>_enum`) become `enum` fields with
   `allowed_values` populated from `permissible_values`. Use
   `--linkml-class NAME` if the schema declares multiple classes.

YAML/LinkML support requires the `linkml` extra (adds `PyYAML`).

## Schema fields

Each field accepts:

| key             | type           | notes                                              |
| --------------- | -------------- | -------------------------------------------------- |
| `name`          | str            | required                                           |
| `description`  | str            | required; the LLM reads this to disambiguate       |
| `type`          | enum           | `string` \| `number` \| `enum` \| `boolean` \| `list` |
| `allowed_values`| list[str]      | required when `type == "enum"`                     |
| `unit`          | str            | original unit string                               |
| `target_unit`   | str            | request normalization to this unit                 |
| `required`      | bool           | informational                                      |

## Output

See `metaextractor.output.ExtractionResult`. The result carries:

- `paper_id`, `granularity` (`study_level` | `subgroup_level` | `sample_level`),
  `subgroups[]`, `extraction_warnings[]`
- `fields[name]` — per-field result with `value`, optional `by_subgroup`,
  `unit` / `normalized_value` / `normalized_unit`, `extraction_type`
  (`directly_stated` | `derived` | `inferred`), `confidence` band,
  `evidence_quote` (≤25 words, verbatim), `section`, and `notes`
- `samples[]` — one dict per sample for sample-level extractions. Study- and
  subgroup-level values are copied into a sample only when they are known to apply to
  it: `study`-scoped fields always; otherwise only single, non-aggregate values (never
  cohort lists such as `"Healthy; Hypertension"` or summaries such as `"45 ± 10"`),
  and for `sample`-scoped fields only when the model reported no subgroups. Scope comes
  from the schema (`scope: study|sample`, or a LinkML slot annotation).
- `sample_provenance[]` — parallel to `samples`; for each cell, its source:
  `table:<table>:<column>`, `manifest:<table>:<column>`, `llm_sample`,
  `study_fanout`, `subgroup_fanout:<label>`, or `age_rule:<rule>`
- Optional age-bound rules (`--age-rules rules.json`, see
  `metaextractor.sample_rules.AgeBoundRules`) fill `age_min`/`age_max` from a
  per-sample age or an age-group definition; they are off unless configured and only
  touch fields the schema declares.

## Evaluation

`metaextractor.evaluation` scores an `ExtractionResult` against a
gold-standard table (one row per sample, columns = field names). For
every `(sample, field)` cell it returns one of:

| decision      | meaning                                              |
| ------------- | ---------------------------------------------------- |
| `TN`          | both NR — correct abstention                         |
| `TP_correct` | both reported; values match                          |
| `TP_wrong`   | both reported; values differ (surface form or content)|
| `FN`          | gold reported, extracted NR — omission               |
| `FP`          | gold NR, extracted reported — over-claim             |

From those it derives, per field, aggregated, and stratified by
`extraction_type` and `confidence` band:

| metric | definition |
| --- | --- |
| `value_precision` / `value_recall` / `value_f1` | TPc / (TPc+TPw+FP), TPc / (TPc+TPw+FN) — only a correct value is a hit |
| `presence_precision` / `presence_recall` / `presence_f1` | (TPc+TPw) / (TPc+TPw+FP), (TPc+TPw) / (TPc+TPw+FN) — reporting status only |
| `value_accuracy` | TPc / (TPc+TPw), conditional on both sides reporting |
| `total_accuracy` | (TPc+TN) / all cells |

`precision`, `recall`, and `f1` remain as aliases of the **presence** metrics for
backward compatibility; prefer the explicit names. Samples are compared positionally
(`samples[i]` ↔ `gold_rows[i]`); to compare by identity, align first with
`metaextractor.alignment.align_by_identity`, which matches records one-to-one on
identifier token sets (optionally compound keys such as `subject_id+timepoint`) and
reports unmatched, pooled, ambiguous, and duplicate records. A `None` entry in
`samples` is scored as a record that reports nothing. The scorer does not copy
study-level values into samples unless `inherit_study_fields=True`.

Equality is normalized, not byte-exact. Numeric values use a 5% relative tolerance
after optional unit normalization (e.g. month → year). String values are
compared after lowercasing and stripping; Python lists are sorted first
(delimited strings are not split). There is
no synonym table; surface-form mismatches surface as `TP_wrong` so they
can be resolved upstream with an ontology crosswalk rather than masked.

### Python API

```python
from metaextractor.evaluation import evaluate, load_extraction, load_gold_tsv

result = evaluate(
    extraction=load_extraction("results_28144631_2pass.json"),
    gold_rows=load_gold_tsv("AsnicarF_2017_sample.tsv"),
    field_map={
        "age_group": "age_group",
        "body_site": "body_site",
        "dna_extraction_kit": "dna_extraction_kit",
        # ... extractor field name -> gold column name
    },
    unit_fields={"age_min": "age_unit", "age_max": "age_unit"},
    paper_text=open("paper.txt").read(),  # optional; enables verbatim quote check
)

print(result.summary())                                 # formatted text report
print(result.aggregate.value_f1, result.aggregate.presence_f1)
print(result.per_field["dna_extraction_kit"].value_accuracy)
result.to_cells_tsv("cells.tsv")                        # per-cell audit table

for c in result.per_cell:
    if c.decision == "TP_wrong":
        print(c.field, c.extracted, "vs gold:", c.gold)
```

### CLI

A thin wrapper for the cMD-style sample-table format ships at
[`tools/eval_one_paper.py`](tools/eval_one_paper.py); the cMD field
crosswalk lives in that script, not the library.

```bash
python tools/eval_one_paper.py \
    results_28144631_2pass.json \
    AsnicarF_2017_sample.tsv \
    --paper paper.txt \
    --rows-out cells.tsv
```

### Faithfulness checks (no gold required)

Beyond gold-comparison, `evaluate()` runs Tier-D checks against the
extractor's own contract:

- **Contract violations** — flags non-NR values that ship without an
  `evidence_quote`.
- **Verbatim-quote rate** — when `paper_text` is supplied, each non-empty
  `evidence_quote` is substring-matched against the paper. Anything below
  ~95% indicates a system bug, not an extraction error.

## Human review

Gold is imperfect, and an extraction from a study with no gold has no automatic
score at all. `metaextract-review` turns one extraction into a single
self-contained HTML file a reviewer can open offline, work through, and export a
verdict from:

```bash
# build a packet (--paper enables the verbatim check on every evidence quote)
metaextract-review packet result.json --paper paper.txt -o packet.html

# validate what came back; refuses verdicts pinned to a different draft
metaextract-review ingest verdict-*.json --draft result.json

# support rate, per-field breakdown, and Cohen's kappa across reviewers
metaextract-review report verdict-*.json --draft result.json
```

The packet has no external reference except the PubMed/PMC/DOI link a reviewer
follows to read the source; CSS and JS are inline, and progress autosaves to
`localStorage` keyed by the draft's digest. Two modes share one renderer:

- **draft** — every reported value is a unit. No gold involved, so this is what
  applies to studies outside a benchmark.
- **adjudication** — `--cells cells.json` makes the units sampled scored cells
  (`{sample_idx, field, extracted, gold, decision}`), shown against the source,
  and adds a `gold_wrong` verdict for cells where the curated value is the wrong
  one. This is the design in [`evaluation/extensions/PLAN.md`](evaluation/extensions/PLAN.md).

Verdict files are validated against
[`src/metaextractor/schemas/review_verdict.schema.json`](src/metaextractor/schemas/review_verdict.schema.json)
and pinned to the draft by SHA-256 of its canonical JSON — a verdict is only
evidence about the extraction it was formed on, so `ingest` refuses a mismatch
rather than carrying verdicts across a re-extraction. Reviewer verdicts are never
mixed with the gold.

Two things the report does deliberately. `cannot_determine` is kept out of both
the numerator and the denominator of the support rate and reported on its own
line: it is the honest verdict when a value lives in a supplement that retrieval
never fetched, and folding it either way would turn a retrieval limit into an
accuracy claim. And κ is withheld, with a stated reason, when reviewers share too
few units or both used a single category — that makes κ undefined, not perfect.

Two asymmetries the packet shows rather than hides: sample cells carry no
evidence quote, because that slot is study-level; and their source descriptor
names the **column** a value came from, not the row, because provenance is
recorded per field per run.

## Design properties and limits

- The system prompt instructs the model not to use outside knowledge and to
  return `"not_reported"` for absent fields. This is an instruction, not an
  enforced check; use `evaluate(..., paper_text=...)` to test evidence quotes.
- Responses are parsed as JSON and validated with Pydantic against the result
  envelope. Malformed or truncated responses raise `ExtractionError` with the raw
  response attached. Validation does not check field names, types, or enum
  membership against the target schema.
- `metaextract --run-meta meta.json --save-text text.txt` records request settings,
  returned model ids, token usage, cost, and every retrieval attempt, plus the exact
  text sent to the model.
- The system prompt is cached (Anthropic ephemeral prompt cache), so
  repeated extractions against new papers reuse the cached prefix.
- Schemas larger than `batch_size` fields are transparently split into
  batches; each batch reuses the cached prefix, so marginal cost scales
  with output tokens only.
