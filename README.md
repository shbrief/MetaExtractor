# MetaExtractor

LLM-backed biomedical metadata extractor. Given a research paper and a
schema, returns one structured JSON object per paper with verbatim evidence
quotes, section attributions, and explicit `not_reported` markers — no
fabrication, no outside knowledge. Ships with an evaluator that scores
extractions against a gold-standard table.

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

Requires `ANTHROPIC_API_KEY` in your environment.

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
- `samples[]` — one dict per sample for sample-level extractions; each
  sample inherits study-level fields and overrides per-sample ones

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

From those it derives precision, recall, F1, value-accuracy on attempted
cells, and total-cell accuracy — per field, aggregated, and stratified by
`extraction_type` and `confidence` band.

Equality is strict by design. Numeric values use a 5% relative tolerance
after optional unit normalization (e.g. month → year). String values are
compared after lowercasing, stripping, and sorting (for lists). There is
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
print(result.aggregate.f1)                              # 0.80
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

## Guarantees

- The system prompt forbids outside knowledge; missing fields become
  `"not_reported"` rather than guesses.
- Output is validated with Pydantic — malformed responses raise
  `ExtractionError` with the raw response attached for inspection.
- The system prompt is cached (Anthropic ephemeral prompt cache), so
  repeated extractions against new papers reuse the cached prefix.
- Schemas larger than `batch_size` fields are transparently split into
  batches; each batch reuses the cached prefix, so marginal cost scales
  with output tokens only.
