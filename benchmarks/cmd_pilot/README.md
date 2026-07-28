# MetaExtractor pilot benchmark — curatedMetagenomicData gold

Evaluation of MetaExtractor against the `curatedMetagenomicData` (cMD) sample
tables as ground truth, scored with the `curatedmetagenomicdata` LinkML target
schema. Two extraction paths were tested on the same 5 pilot studies:

- **Experiment A — by-PMID** (`bench.py run`): fetch PMC full text + Europe PMC
  supplementary; the LLM discovers samples from prose/supplementary text.
- **Experiment B — `tables=` path** (`bench.py run-tables`): feed the study's raw
  SRA metadata table (`*_sra_meta.tsv`) as a local supplementary file; per-sample
  rows come from MetaExtractor's deterministic column-map + join, the LLM only
  extracts prose study-level fields. Scored with **accession alignment**.

Common setup:

- **Model:** `claude-haiku-4-5`
- **Target schema:** `MetaHarmonizerSchemaRegistry/schema/curatedmetagenomicdata/cmd.linkml.yaml`
- **Gold:** `curatedMetagenomicDataCuration/inst/curated/<study>/<study>_sample.tsv`
- **Studies:** 20 selected reproducibly (`select_studies.py`, seed=42); pilot = first 5.
- **Cost:** Experiment A ≈ **$0.74**; Experiment B ≈ **$0.33** (4 studies w/ sra_meta).

## Headline

| path | Precision | Recall | F1 | value-acc | notes |
|---|--:|--:|--:|--:|---|
| A · by-PMID | 0.85 | 0.59 | 0.70 | 0.53 | only 1/5 studies sample-aligned; numbers inflated by study-constant fan-out |
| **B · tables= (accession-aligned)** | **0.88** | **0.73** | **0.80** | 0.45 | 3/4 studies matched 100 % of gold samples |

Content fields, micro-averaged. `value-acc` = fraction of *attempted* cells whose
value matches gold exactly; it is depressed in both paths by raw-vs-harmonized
surface forms (see Finding #4).

## Per-study sample alignment

**Experiment A (by-PMID)** — LLM sample discovery, positional join:

| study | gold n | extracted n | aligned? |
|---|--:|--:|---|
| Bengtsson-PalmeJ_2015 | 70 | 0 (stayed study-level) | no |
| TettAJ_2019_b | 44 | 1023 | no |
| LiJ_2017 | 196 | 196 | yes (coincidental) |
| NayakRR_2021 | 34 | 6 | no |
| PasolliE_2019 | 112 | 9316 | no |

**Experiment B (`tables=`)** — deterministic rows, aligned on `ncbi_accession`:

| study | gold n | extracted n | gold rows matched |
|---|--:|--:|---|
| Bengtsson-PalmeJ_2015 | 70 | 28 | **0/70** (accession format mismatch — Finding #5) |
| TettAJ_2019_b | 44 | 171 | **44/44** |
| LiJ_2017 | 196 | 196 | **196/196** |
| PasolliE_2019 | 112 | 164 | **112/112** |
| NayakRR_2021 | 34 | — | no `sra_meta` table available |

## Findings

**1. The target schema does not load unmodified.** 11 slots (`disease`,
`country`, `target_condition`, `ancestry`, `treatment`, `host_species`,
`body_site_details`, `disease_details`, `ancestry_details`, `hla`,
`obgyn_menopause`) use LinkML `reachable_from` ontology enums. MetaExtractor's
`adapters/linkml.py` only reads static `permissible_values`; a single-valued
dynamic enum yields `allowed_values=[]` and raises Pydantic `value_error`.
`make_clean_schema.py` downgrades them to `string`. *Fix candidate:* the adapter
should treat `reachable_from`-only enums as free-text automatically.

**2. Sample enumeration is the deciding factor.** In Experiment A the by-PMID
path derives samples from whatever tabular rows appear in fetched supplementary
files — often OTU/feature matrices or per-read stats, not the sample manifest —
so counts explode (PasolliE 9316, TettAJ 1023) or the run stays study-level
(Bengtsson 0). Because `evaluate()` joins **positionally**, any count mismatch
collapses recall. The `tables=` path fixes this: one deterministic row per
archive sample.

**3. By-PMID "successes" are largely study-level fan-out.** Even where counts
matched (LiJ 196=196), extracted `sample_id`s never matched gold IDs — the
positional join was only *coincidentally* right for study-constant fields
(body_site, country, kit, platform), while per-sample fields failed (`age_group`
all FN; `disease` one study list fanned to every row). This is why Experiment A's
F1 0.70 overstates true per-sample performance.

**4. Raw-vs-harmonized surface forms cap value-accuracy.** Gold mixes raw and
harmonized cMD vocab; the extractor emits verbatim/harmonized values, so
substantively-correct cells score `TP_wrong` (value-acc 0): `smoker`,
`target_condition`, `sample_id`, `age_min`/`age_max`, `ancestry_details`, and
partly `disease`/`body_site`. Resolve with an ontology crosswalk before scoring
value accuracy — this is expected per the extractor's own design.

**5. The `tables=` column-mapper has two real defects (Experiment B).**
   - *Nested column layout not handled.* `Bengtsson-PalmeJ_2015_sra_meta.tsv`
     stores fields under a `full_metadata.*` prefix; `ncbi_accession` mapped to
     `NA` (and picked up a `SAMN…` BioSample instead of the `ERR…` run gold
     uses), so accession alignment matched **0/70**.
   - *Lexical mis-map.* In `LiJ_2017`, per-sample `body_site` was filled from an
     sra_meta column holding a truncated center name (`'BEIJING CHAOYANG
     HOSPITA'`) for all 196 rows, overriding the correct prose value `feces`
     (body_site value-acc fell to 0.18). Column mapping needs value-type / enum
     validation, not just lexical header matching.

**6. Per-sample clinical metadata is not recoverable from archives.** `sex`,
`age`, `bmi`, `family` are absent from SRA metadata and not machine-readable
per-sample in prose, so they stay FN in both paths. This is a data-availability
limit, not an extractor bug.

### What MetaExtractor does well

With the `tables=` path + accession alignment, archive/technical and
study-constant fields are recovered essentially perfectly (P=1.00, value-acc
1.00): `sequencing_platform`, `ncbi_accession`, `pmid`, `host_species`,
`location`, `westernized`, `age_unit`; and F1≈0.93–1.00 for `country`,
`dna_extraction_kit`, `control`, `antibiotics_current_use`, `disease`. No
fabrication of identifiers was observed (accessions come from the table, not the
model).

## Reproduce

```bash
cd benchmarks/cmd_pilot
python select_studies.py manifest.json
python make_clean_schema.py cmd.clean.linkml.yaml
export ANTHROPIC_API_KEY=sk-ant-...

# Experiment A — by-PMID
python bench.py run        manifest.json out        --limit 5 --model claude-haiku-4-5
python bench.py eval       manifest.json out        --limit 5

# Experiment B — tables= path (uses <study>_sra_meta.tsv), accession-aligned
python bench.py run-tables manifest.json out_tables --limit 5 --model claude-haiku-4-5
python bench.py eval       manifest.json out_tables --limit 5 --align-key ncbi_accession
```

Outputs: `out/` and `out_tables/` each hold `<study>.json` (raw extraction),
`<study>.cells.tsv` (per-cell audit), `summary.json`, and `REPORT.md` (full
per-field tables).

## Recommendation

The `tables=` path is the right substrate for per-sample evaluation and should be
used for any scale-up to the full 20 studies. Before that, two upstream fixes
would materially raise value-accuracy: (a) teach the column-mapper nested-header
and value-type/enum validation (Finding #5), and (b) add a raw→harmonized
ontology crosswalk in the evaluator so surface-form matches stop scoring as
`TP_wrong` (Finding #4). Per-sample clinical fields (sex/age/bmi) will remain
unrecoverable without a machine-readable per-subject supplementary table.
