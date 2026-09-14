# MetaExtractor: schema-guided metadata extraction from scientific literature and sequencing archives, evaluated on curatedMetagenomicData

[AUTHORS AND AFFILIATIONS]

## Abstract

**Background.** Reusing public omics data depends on sample-level metadata that is usually reported in
free text, supplementary tables, and sequence-archive records rather than in a structured form.
We describe MetaExtractor, an open-source tool that combines large-language-model (LLM) extraction
with deterministic retrieval, table handling, and record assembly to populate a user-supplied schema,
and we evaluate it against manually curated metadata from curatedMetagenomicData (cMD).

**Methods.** Ten cMD studies (1,089 curated samples, 71-field schema) were each extracted three times
with Claude Sonnet 5 and Claude Haiku 4.5 from one tagged code snapshot (60 extractions), with every
attempt logged. Extracted sample records were aligned to curated rows by shared identifiers under a
one-to-one rule. We report value-aware precision and recall — in which only a correct value counts as
a hit — over all curated rows (end-to-end) and over identifier-matched rows (conditional), together with
presence metrics that ignore value correctness. Disease, body-site, and treatment values were mapped to
ontology codes with MetaHarmonizer and compared with the curators' identifiers by exact code-set match.

**Results.** Fifty-six of 60 extractions produced output; the four failures were Sonnet 5 responses
truncated in both attempts. Extracted records could be matched to curated rows for at most five studies
per run (102–284 of 1,089 rows for Sonnet 5; 214 for Haiku 4.5). End-to-end value F1 was 0.03
[range 0.03–0.15] for Sonnet 5 and 0.13 [0.13–0.14] for Haiku 4.5 (paired difference −0.06; 95%
study-cluster bootstrap interval −0.19 to 0.06). On matched rows, value precision was 0.48 and 0.62 and
value F1 0.26 and 0.42, whereas presence precision was ≥0.99 for both models. Two studies that had
yielded per-sample records in development runs two months earlier yielded none in five (one study) or
all six (the other) extractions, because the retrieval endpoints that had supplied their full text no
longer did. Harmonization reproduced the curators' ontology identifiers for all coded disease and body-site cells,
but these involved one disease term and two body-site synonyms; the single coded treatment term did not
match.

**Conclusions.** On this microbiome case study, the dominant limits were sample enumeration, identifier
resolution, and time-dependent retrieval rather than per-field value extraction; presence-based
metrics substantially overstate accuracy. Propagating cohort-level values into sample records must be
restricted, and every derived cell should carry its provenance. Broader claims require held-out studies,
baselines, and additional domains.

---

## 1. Introduction

Sample-level metadata — disease status, body site, age, treatment, sequencing platform — determines
whether public omics data can be reused, combined, and modelled. Such metadata is typically scattered
across a paper's methods, supplementary tables, and linked archive records, and it is curated manually
into controlled schemas at considerable cost [CITE: metadata curation burden in public omics repositories].
Resources such as curatedMetagenomicData (cMD) provide this curation for shotgun metagenomic studies
[CITE: Pasolli et al. 2017] and therefore also provide a reference against which automated extraction can
be measured.

LLMs have been applied to biomedical information extraction and to metadata curation specifically
[CITE: LLM-based biomedical information extraction; LLM metadata curation tools]. Two properties make
the per-sample setting harder than study-level extraction. First, the set of samples must itself be
enumerated and each extracted record must be linked to the right curated sample before any value can be
judged. Second, values stated for a cohort (a disease list, a mean age) must not be silently copied onto
individuals. Evaluations that score values positionally, or that count a reported-but-wrong value as a
hit, can report high accuracy without establishing either property.

MetaExtractor is a schema-guided extractor that confines model calls to reading prose and inferring table
structure, and handles retrieval, table execution, joining, and propagation deterministically, recording a
source for every sample cell. Here we (i) describe its design and its limits, including what its output
validation does and does not check; (ii) evaluate it on ten cMD studies with two models and three repeated
runs from a single logged snapshot, using identity-aligned, value-aware metrics; and (iii) assess ontology
harmonization of three fields against the curators' own identifiers. We treat the evaluation as a case
study of one domain and one reference resource.

[CITE: related extraction and harmonization systems; LinkML (schema framework); MetaHarmonizer]

---

## 2. Methods

### 2.1 Evaluation domain and study selection

curatedMetagenomicData (cMD) [CITE: Pasolli et al. 2017, curatedMetagenomicData] provides manually
curated, per-sample metadata tables for public shotgun metagenomic studies, expressed in a
controlled schema [CITE: cMD curation repository and schema release]. We used the curated
`inst/curated/<study>/<study>_sample.tsv` tables of `curatedMetagenomicDataCuration` at commit
`41271711` as the reference standard.

The `*_sample.tsv` tables were enumerated, shuffled with a fixed seed (42), and the first ten
studies with a single numeric PMID and at least one sample were retained
(`benchmarks/cmd_sonnet5/select_studies.py`; re-running it at the stated commit reproduces the
committed `manifest.json`). The set spans 15–363 gold samples per study (1,089 in total):
Bengtsson-PalmeJ_2015, TettAJ_2019_b, LiJ_2017, NayakRR_2021, PasolliE_2019,
Heitz-BuschartA_2016, FanY_2023, QinJ_2012, ContevilleLC_2019, LiSS_2016.

These ten studies were also used while the retrieval layer, table path, and harmonization
corpora were being developed. They are therefore not a held-out test set (Section 4.4).

### 2.2 MetaExtractor

MetaExtractor takes a paper (retrieved by identifier or supplied as text/PDF) and a target schema,
and returns a JSON result with study-level field values, optional per-sample records, provenance,
and a table-selection log; a flat CSV is also written (Figure 1).

![MetaExtractor architecture](figures/fig1_pipeline.png)

**Figure 1. MetaExtractor architecture.** Blue boxes are deterministic steps, orange boxes are LLM
calls, and grey boxes are inputs and outputs. The model proposes study-level values with provenance,
optional sample identifiers, and a structural plan for each selected supplementary table. Retrieval,
table execution, column mapping, joining, fan-out, and age rules are deterministic, and each sample cell
records its source. The Pydantic check validates the structure of each model response, not its
content.

**Schema input.** Schemas are read from JSON, YAML, or LinkML YAML (LinkML is detected by the
presence of `classes`/`slots`/`enums`). The LinkML adapter supports a subset of LinkML: the slots
and attributes of one class; `description`; numeric, boolean, and string ranges; enums with
static `permissible_values` (keys, descriptions, and `meaning` CURIEs); `multivalued` (mapped to a
list); `required`; `unit`/`ucum_unit`; and a `scope` annotation (`study` or `sample`). Other LinkML
semantics — `reachable_from` dynamic enums, `pattern`, numeric bounds, `is_a`/mixins,
`slot_usage`, class-valued ranges, and identifiers — are not interpreted. For cMD, 11 slots whose
range is a `reachable_from` enum were downgraded to free-text strings before loading, giving a
71-field schema (`make_clean_schema.py`); 54 slots were annotated `sample`, 10 `study`, and 7 left
unannotated. The scope annotation is used only by the deterministic fan-out rule below and is not
sent to the model.

**Retrieval.** For a PMID, the retrieval layer collects candidate texts from NCBI PMC full text,
Europe PMC full text (by PMCID, and by DOI), Europe PMC's rendered PDF for non-Open-Access PMC
records, and an Open Access PDF located through Unpaywall [CITE: Europe PMC; Unpaywall], with the
PubMed abstract as a floor. It scores each candidate for article-narrative quality and keeps the
best body; costlier rungs are attempted only while no body scores as clearly substantive.
Transient HTTP failures are retried. Supplementary files are listed from the PMC Open Data S3
bucket and the Europe PMC supplementary archive. Separately, the layer resolves the study's own
sequencing project from accessions in data-availability language (refusing ambiguous cases) and
fetches its per-run manifest from the ENA `read_run` endpoint [CITE: ENA]. Every attempted
retrieval rung and its outcome is recorded in the run metadata.

**Model calls.** The model is reached through the Anthropic Messages API in three roles:
(i) *field extraction*, one call per batch of at most 30 schema fields; (ii) optional *sample
discovery*, which asks the model to construct a stable identifier for each sample described in
supplementary prose (identifiers encode attributes such as subject, body site, and timepoint and
are therefore model-generated); and (iii) a *table plan* per selected supplementary table, which
sees a truncated preview and returns header rows, identifier columns, and an optional melt recipe.
A fixed system prompt instructs the model to extract only what the supplied text supports, to
return `not_reported` for absent fields, not to create per-sample rows from aggregates, to return
enum values in the surface form used by the paper, and to attach an extraction type, confidence,
a ≤25-word evidence quote, and a section to each study-level value. The response is parsed as JSON
and validated with Pydantic against a fixed result model.

That validation is **structural**: it checks the result envelope (granularity, field records,
provenance slots). It does not check that field names belong to the target schema, that required
fields are present, that values have the declared type or belong to an enum, or that an evidence
quote occurs in the source. Field values are model-generated text; the prompt contract, not code,
is what asks the model to stay faithful to the source.

**Deterministic table path.** Parsed supplementary tables (xlsx/csv/tsv, PDF table regions) are
scored for schema relevance (header-name and enum-value overlap, an identifier-column signal, and
shape); tables scoring below 0.15, and feature × sample measurement matrices, are skipped. For a
selected table the plan is applied by a Python executor that copies cell values by index; category
labels in melted output come from the plan. Columns are mapped to schema fields by an exact →
normalized → alias → fuzzy cascade, and tables are left-joined on the highest-priority shared key
(`sample_id` > `subject_id` > `ncbi_accession` > `study_name`) when key overlap is at least 0.9.
The ENA run manifest enters this path only when the article's own tables yield no sample rows.
Whenever at least one structured table was parsed (including the manifest), sample records come
only from this path: sample discovery is not run, and per-sample rows the model may emit are
replaced by the table rows — even when the tables yield none. Sample discovery and model-emitted
sample rows therefore apply only to papers with no parsed table.

**Sample records and provenance.** Each sample cell carries a recorded source: a table or manifest
column, a per-sample value emitted by the model, or one of the deterministic rules below.

**Fan-out of study- and subgroup-level values.** Study-level values are propagated into sample
records only under the following rules (`metaextractor.sample_rules`). A value already present in a
sample is never overwritten. A sample receives a subgroup's value only if its string values match
exactly one of the model's subgroup labels. Otherwise a study-level value is propagated when the
field is `study`-scoped; for `sample`-scoped or unannotated fields it is propagated only when it is
a single value (not a list or a `;`-delimited cohort list) and not an aggregate statistic (mean,
median, SD, IQR, range, ±, n =), and, for `sample`-scoped fields, only when the model reported no
subgroups. Blocked propagations are counted in the result warnings.

**Age bounds.** An optional, configurable rule fills the cMD `age_min`/`age_max` slots. It runs only
when configured and only when the schema declares both fields. A numeric per-sample age that was
not itself propagated from a study-level value, and whose unit converts to years, sets both bounds
to that age, as the cMD slot definition states; a row with an unrecognized unit is left unchanged.
Otherwise, when neither bound is numeric, the bounds of the record's `age_group` are used. The cMD
configuration (`age_rules_cmd.json`) takes the lower bounds and the Infant/Child/Adolescent/Adult
upper bounds from the `age_group` slot definition; the schema gives Elderly no upper bound, and we
use 130, the value encoded in 743 group-only Elderly rows of the curated tables. Study-level ages
are never converted into bounds.

**Output and cost.** Token usage across all calls is converted to a cost estimate from a price
table dated 2026-06-24 (`PRICING_AS_OF`), including cache-read and cache-write rates.

### 2.3 Extraction runs

The benchmark was run from the tagged commit `bench-v2` with `run_frozen.py`: 10 studies × 2 models
(`claude-sonnet-5`, `claude-haiku-4-5`) × 3 repeated API runs = 60 extractions, by PMID, with sample
discovery enabled, the 0.15 table-relevance threshold, the cMD age rules, `max_tokens` 16,384, and
field batches of 30. No `temperature`, `top_p`, `top_k`, `thinking`, or `effort` parameters were
sent, so each model ran at its API defaults; for Sonnet 5 the default is adaptive thinking
[CITE: Anthropic model documentation]. The run refused a working tree with uncommitted changes and
an output directory that was not empty, so no output was carried over from earlier pipeline
versions. Each extraction had a 25-minute wall-clock cap and one retry after a failed attempt.
Every attempt — including failures — was appended to `out_v2/ledger.jsonl` with UTC start and end
times, status, its stderr log, the git commit, SHA-256 checksums of the schema, manifest, and age
rules, and checksums of every output file. The model identifiers returned by the API, token usage,
and retrieval attempts were written per extraction to `<study>.meta.json`, and the exact text sent
to the model to `<study>.text.txt` (checksummed; not redistributed). Retrieval was live, so a re-run
at a later date may retrieve different text.

### 2.4 Scoring

**Cell decisions.** For each gold row and content field (identifier and provenance fields —
`study_name`, `sample_id`, `subject_id`, `pmid`, `curator`, `ncbi_accession`, `host_species`,
`uncurated_metadata` — are scored separately), a cell is TN (neither side reports a value), FN (gold
reports, extraction does not), FP (extraction reports, gold is blank), TPc (both report and the
values match), or TPw (both report, values differ). Values match when both parse as numbers within
5% relative tolerance (after converting ages to years using the unit fields), or when their
strings are equal after trimming and lowercasing (Python lists are sorted first). There is no
synonym table. A sample record is scored only on the cells it contains; study-level values reach
a sample only through the fan-out rule above.

**Metrics.** From pooled counts over content fields:

- value precision = TPc / (TPc + TPw + FP); value recall = TPc / (TPc + TPw + FN); value F1 is their
  harmonic mean;
- presence precision = (TPc + TPw) / (TPc + TPw + FP); presence recall = (TPc + TPw) / (TPc + TPw + FN);
- value accuracy = TPc / (TPc + TPw), conditional on both sides reporting a value.

Presence metrics describe reporting status only: a wrong value counts as a hit. FP means the
extraction asserted a value where the curated table has none; this may reflect over-assertion or
an incomplete gold row, and the scorer cannot tell them apart (Section 3.5 reports a partial source
check).

**Identity alignment.** Extracted records are aligned to gold rows by identifier
(`metaextractor.alignment.align_by_identity`) using the candidate keys `ncbi_accession`, `sample_id`,
and `subject_id`. Identifier cells are split into token sets, so a gold row listing several run
accessions is represented explicitly. A gold row is matched only when its tokens identify exactly
one extracted record and that record is claimed by no other gold row; a gold row whose tokens
identify several distinct records is *pooled*, and one involving duplicated keys is *ambiguous*.
Neither is resolved by position or first occurrence. Per study, the candidate key yielding the most
one-to-one matches is used.

**Joins.** The primary **end-to-end** score covers every gold row: unmatched, pooled, and ambiguous
gold rows contribute their populated cells as FN. Extracted records with no matching gold row are
reported separately — split into those carrying an identifier (for example deposited runs outside
the curated subset) and those without one — and are not scored as cells. The **conditional** score
restricts to matched gold rows. A **positional** score (sample *i* ↔ gold row *i* over
min(n extracted, n gold)), used in an earlier version of this analysis, is reported only as a
supplementary comparison.

**Repeats and uncertainty.** We report the median and range across the three repeats. Because the
repeats measure run-to-run variation on the same ten studies, we also report a paired
study-cluster bootstrap (2,000 resamples of studies with replacement, repeats pooled within study,
seed 0) for the difference in end-to-end value F1 between models. Neither quantity estimates
performance on other studies.

### 2.5 Ontology harmonization

Extracted and gold values for `disease`, `body_site`, and `treatment` were mapped with
MetaHarmonizer's OntologyMapper (v0.4.1) [CITE: MetaHarmonizer] using its exact, embedding, and
synonym stages (the retrieval-augmented and LLM-review stages were disabled). Corpora were field
specific: for `disease`, the NCIt subtree C7057 ("Disease, Disorder or Finding") combined with the
static term C115935 ("Healthy") [CITE: NCI Thesaurus]; for `body_site`, the six UBERON terms of the
cMD `body_site` enum [CITE: UBERON]; for `treatment`, the NCIt "Pharmacologic Substance" subtree
(C1909). These corpus choices were made after inspecting mismatches on these ten studies (for
example, adding "Healthy"); they are not an independent test of corpus design.

Each value maps to the set of codes of its `;`/`,`/`/`-separated terms. Scoring uses identity-matched
rows only. On cells where both sides report a value and the gold row carries a curated
`*_ontology_term_id` ("coded cells"), we report, on the same cells: raw accuracy (the string
comparison above); **exact correctness**, the fraction whose extracted code set equals the curated
identifier set; concept-level precision and recall (Σ|E∩G| / Σ|E| and Σ|E∩G| / Σ|G|); and, as a
supplementary quantity only, the fraction sharing at least one code. Agreement — whether the
extracted and gold *values* map to the identical code set — is reported over all both-reported
cells; it measures consistency of the mapper, not correctness.

### 2.6 Reproducibility

Code, schema, manifest, age rules, crosswalks, scoring outputs, and the attempt ledger are in the
repository at tag `bench-v2` (extraction) and the subsequent analysis commit; `REPRODUCE.md` lists the
commands. Extraction JSON/CSV and per-attempt logs are included; retrieved article text is not
redistributed but is identified by checksum. Dependencies are listed in
`benchmarks/cmd_sonnet5/requirements-lock.txt`.

---

## 3. Results

All numbers below are generated by `aggregate.py` and `bench.py harmonize` from the `out_v2` run tree
(`out_v2/AGGREGATE.md`, `out_v2/aggregate_v2.json`, `out_v2/harmonization.md`). Ranges are
median [min–max] across the three repeats.

### 3.1 Run completion, failures, and cost

The 60 extractions ran on 14 September 2026 between 15:15 and 17:22 UTC from commit `be6a7c1`
(tag `bench-v2`), with no uncommitted changes. They required 68 attempts. Eight tasks failed on the
first attempt and four of these failed again on the retry, so 56 of 60 extractions produced output
(12 of 68 attempts failed).

| outcome | attempts | tasks |
|---|--:|---|
| response not parseable as JSON (truncated mid-object) | 9 | Sonnet 5: FanY_2023 r1 ×2, r3 ×2; PasolliE_2019 r2 ×2, r3 ×2; TettAJ_2019_b r2 ×1 |
| response failed result-model validation | 1 | Haiku 4.5: LiJ_2017 r3 (succeeded on retry) |
| API read timeout (Anthropic SDK) | 2 | both models: Heitz-BuschartA_2016 r3 (succeeded on retry) |
| **no output after retry** | — | **Sonnet 5: FanY_2023 r1, r3; PasolliE_2019 r2, r3** |

In each of the nine unparseable responses, the JSON parse error fell at the end of the returned text,
between characters 7,600 and 18,300, inside an unfinished object: the responses were cut off rather
than malformed. The requests set
`max_tokens` to 16,384 and left Sonnet 5 at its default adaptive thinking, so thinking tokens may have
consumed the output budget; the stop reason was not logged, so this remains a hypothesis. Failed
extractions are scored end-to-end as producing no records (all curated cells of that study become false
negatives); Table 2 also reports end-to-end metrics over successful extractions only. Some recorded
attempt durations (maximum 3,452 s) exceeded the 25-minute cap; we did not determine why the cap did
not bound wall-clock time.

The API returned the model identifiers `claude-sonnet-5` and `claude-haiku-4-5-20251001`. The 56
successful extractions made 253 (Sonnet 5) and 402 (Haiku 4.5) model calls, with an estimated cost of
US$9.67 and US$3.93 at list prices dated 2026-06-24. Failed attempts are not included, because usage
was recorded only for completed extractions.

### 3.2 Retrieval and sample enumeration

Table 1 lists, per study, the text source selected, the ENA manifest resolved, and the number of sample
records extracted.

**Table 1. Retrieval and sample enumeration.** Counts are records per repeat (r1/r2/r3); "—" marks a
failed extraction. "Matched" is the number of curated rows aligned one-to-one (Section 3.3).

| study | gold n | text source (runs) | ENA manifest | Sonnet 5 records | Haiku 4.5 records | key | matched rows (S / H) |
|---|--:|---|---|---|---|---|---|
| Bengtsson-PalmeJ_2015 | 70 | PMC abstract-only body (5); Europe PMC PDF (1) | PRJEB7369, 70 runs (1 run) | 70 / 0 / 0 | 0 / 0 / 0 | ncbi_accession | 70, 0, 0 / 0 |
| TettAJ_2019_b | 44 | PMC full text | 4 projects, 171 runs (unused) | 50 / 50 / 50 | 50 / 50 / 50 | none | 0 / 0 |
| LiJ_2017 | 196 | PMC full text | none | 12 / 6 / 6 | 1,448 ×3 | none | 0 / 0 |
| NayakRR_2021 | 34 | PMC full text | PRJNA656577, 434 runs | 434 ×3 | 434 ×3 | ncbi_accession | 34 / 34 |
| PasolliE_2019 | 112 | PMC full text | 2 projects, 164 runs (unused) | 112 / — / — | 112 ×3 | sample_id | 112, 0, 0 / 112 |
| Heitz-BuschartA_2016 | 53 | Unpaywall PDF | PRJNA289586, 221 runs | 221 ×3 | 221 ×3 | ncbi_accession | 53 / 53 |
| FanY_2023 | 147 | PMC full text | none | — / 510 / — | 319 ×3 | none | 0 / 0 |
| QinJ_2012 | 363 | PubMed abstract | none | 0 ×3 | 0 ×3 | none | 0 / 0 |
| ContevilleLC_2019 | 15 | PMC full text | PRJNA527208, 15 runs | 15 ×3 | 15 ×3 | ncbi_accession | 15 / 15 |
| LiSS_2016 | 55 | PubMed abstract | none | 0 ×3 | 0 ×3 | none | 0 / 0 |

*Manifest "unused": resolved and fetched, but the article's own tables produced rows, so the manifest
was not used (Section 2.2).*

Where a run manifest was used (NayakRR, Heitz-BuschartA, ContevilleLC, and Bengtsson-PalmeJ in one run),
record counts were identical across repeats and models, and every curated accession was present among
the extracted records. For NayakRR and Heitz-BuschartA the manifest also contained 400 and 168 runs
outside the curated subset; these are reported as extra records carrying an identifier.

Enumeration from supplementary tables was less reliable. For LiJ_2017, Haiku 4.5 emitted 1,448 records
(1,015 distinct identifiers) from a table of co-abundance gene groups — feature rows, not samples — in all
three runs, whereas Sonnet 5 emitted 6–12 records (six with identifiers, e.g. "NLF006", "SZEY-103A") from a
supplementary sample table whose identifiers do not correspond to the curated samples. For FanY_2023, Haiku 4.5
emitted 319 records per run from a figure source-data table of metagenomic species (identifiers such as
"msp_0015"), and the one successful Sonnet 5 extraction
emitted 510 records carrying six distinct identifiers from a melted donor table. For TettAJ_2019_b both
models emitted 50 records from a table describing another cohort (Ethiopia) rather than the curated
subset. In these three studies no record could be matched to a curated row, and the extracted
identifiers were not merely written in a different format.

Two studies depended on retrieval rungs that changed. For Bengtsson-PalmeJ_2015, the PMC record exposes
only an abstract-length body. The Europe PMC rendered PDF supplied the full text, data-availability
accession, and manifest in the first extraction (15:15 UTC) and returned nothing in the other five;
a request after the run received HTTP 403. For LiSS_2016, which has no PMC record, earlier development
runs (July 2026) obtained a PDF through Unpaywall; during the benchmark and in a check afterwards,
Unpaywall listed only repository landing pages without a PDF link, and extraction fell back to the
abstract. For QinJ_2012 the configured sources — NCBI and Europe PMC by PMID and DOI, Europe PMC PDF,
and Unpaywall — returned only the abstract at the time of the benchmark. We did not test other routes,
such as BioProject links from the archive side.

### 3.3 Identity alignment

The one-to-one alignment matched curated rows in five studies at most (Table 1): 284 rows in Sonnet 5
run 1 and 102 in runs 2 and 3, and 214 rows in each Haiku 4.5 run (19.7% of 1,089). No curated row was
classified as pooled or ambiguous in the studies that matched, because each matched study used a key that
was unique on both sides (single run accessions for the manifest-fed studies; `sample_id` for PasolliE).
FanY_2023 curated rows list up to four run accessions each; they would be reported as pooled, but no
extracted record carried an accession. The remaining curated rows are unmatched because the study yielded
no records, the records came from the wrong table, or the extraction failed.

### 3.4 Extraction accuracy

**Table 2. Content-field metrics** (median [min–max] over three repeats).

| join | model | value P | value R | value F1 | presence P | presence R | value accuracy |
|---|---|--:|--:|--:|--:|--:|--:|
| end-to-end (primary) | Sonnet 5 | 0.481 [0.383–0.582] | 0.017 [0.014–0.089] | 0.032 [0.027–0.154] | 1.000 [1.000–1.000] | 0.037 [0.035–0.153] | 0.481 [0.383–0.582] |
| end-to-end (primary) | Haiku 4.5 | 0.621 [0.616–0.654] | 0.073 [0.072–0.076] | 0.131 [0.129–0.136] | 1.000 [0.989–1.000] | 0.117 [0.116–0.117] | 0.628 [0.616–0.654] |
| end-to-end, successful extractions | Sonnet 5 | 0.481 [0.383–0.582] | 0.019 [0.018–0.098] | 0.037 [0.035–0.168] | 1.000 [1.000–1.000] | 0.048 [0.040–0.169] | 0.481 [0.383–0.582] |
| conditional (matched rows) | Sonnet 5 | 0.481 [0.383–0.582] | 0.174 [0.149–0.298] | 0.256 [0.215–0.394] | 1.000 [1.000–1.000] | 0.390 [0.362–0.511] | 0.481 [0.383–0.582] |
| conditional (matched rows) | Haiku 4.5 | 0.621 [0.616–0.654] | 0.321 [0.315–0.333] | 0.423 [0.417–0.441] | 1.000 [0.989–1.000] | 0.511 [0.508–0.511] | 0.628 [0.616–0.654] |
| positional (supplementary) | Sonnet 5 | 0.428 [0.357–0.523] | 0.172 [0.149–0.281] | 0.232 [0.221–0.366] | 0.999 [0.998–0.999] | 0.482 [0.349–0.538] | 0.428 [0.357–0.523] |
| positional (supplementary) | Haiku 4.5 | 0.679 [0.677–0.711] | 0.346 [0.336–0.384] | 0.458 [0.457–0.490] | 1.000 [0.995–1.000] | 0.510 [0.473–0.562] | 0.682 [0.677–0.711] |

*Haiku 4.5 had no failed extractions, so its successful-only row equals its end-to-end row.*

End-to-end recall was low for both models because most curated rows were never matched (Section 3.3).
Presence precision was close to 1 on every join, but between 35% and 62% of the cells both sides
reported had the wrong value (value accuracy 0.38–0.65). Value precision is therefore the more informative figure: it was 0.48 for
Sonnet 5 and 0.62 for Haiku 4.5. These values reflect exact string comparison after lowercasing, so they
include surface-form differences that harmonization may resolve (Section 3.7).

Sonnet 5's end-to-end metrics varied far more across repeats than Haiku 4.5's. Its best run (run 1) was
the only run in which Bengtsson-PalmeJ was retrieved in full and PasolliE did not fail. Across the ten
studies, the paired difference in end-to-end value F1 (Sonnet 5 − Haiku 4.5) was −0.058 (95%
study-cluster bootstrap interval −0.187 to 0.061). With ten studies and so much of the difference driven
by retrieval and failures, the data do not establish that either model is more accurate. Per-study
results are shown in Figure 2c.

![Model comparison](figures/fig2_model_compare.png)

**Figure 2. Extraction accuracy on the ten-study benchmark.** (a) End-to-end content-field metrics:
value-aware precision, recall, and F1 (only value-correct cells count as hits) and presence precision and
recall (any reported value counts). Bars show the median of three repeats; whiskers show the range.
(b) False-positive cells, end-to-end. (c) End-to-end value F1 per study; dots are medians and lines ranges
across repeats. A study with no matched rows has a value F1 of 0.

### 3.5 False positives, propagation, and source checks

End-to-end false-positive cells were 0 in all Sonnet 5 runs and 0, 0, and 22 in the Haiku 4.5 runs; the
22 were `treatment` values on Heitz-BuschartA rows whose curated treatment cell is empty. In all 22 cells
the asserted value string occurs verbatim in the retrieved text. That check shows the value was not
invented from outside the text; it does not show that the value applies to those samples, nor that the
curated cell should have been filled.

The positional join, which ignores identity, found 2 false-positive cells per Sonnet 5 run and 1–23 per
Haiku 4.5 run, all in TettAJ_2019_b and Heitz-BuschartA_2016.

The fan-out rule propagated 30,230 (Sonnet 5) and 88,690 (Haiku 4.5) study-level cells into sample
records across all repeats — counted over every extracted record, including the extra and unmatched
records above — plus 27 subgroup-level cells for Sonnet 5. It blocked 3,069 and 54,412 propagations of
multi-valued cohort values, 580 and 0 of aggregate statistics, and 5,514 and 22,252 propagations of
sample-scoped values in cohorts with subgroups. In LiJ_2017, for example, Haiku 4.5 reported disease at study level as the three-item list
Hypertension, Pre-hypertension, Healthy; it was not copied to any record.

The rule is not complete. In the Sonnet 5 run that retrieved Bengtsson-PalmeJ, the paper states
"Subjects were 23 to 34 years old"; the model placed 23 and 34 in the study-level `age_min` and `age_max`
fields, and because each is a single number the rule propagated them to all 70 records. The resulting
cells were mostly wrong against the curated per-subject bounds (Section 3.6).

### 3.6 Age bounds

Age bounds derived by the configured age rule were correct in every scored cell: 112 `age_min` and 112
`age_max` cells in the one successful Sonnet 5 PasolliE extraction and 336 of each across the three Haiku
4.5 PasolliE extractions, all set from per-sample ages in the supplementary table. The only other scored
age bounds were the propagated Bengtsson-PalmeJ cohort range above: 26 of 70 `age_min` and 2 of 70
`age_max` cells matched. The age rule was evaluated on one study only.

### 3.7 Ontology harmonization

Identity-matched cells carrying a curated ontology identifier were few and involved few distinct terms
(Table 3, `out_v2/harmonization.md`).

**Table 3. Ontology harmonization on identity-matched coded cells.** Accuracy columns are medians over the
runs that had coded cells.

| field | model | runs with coded cells | coded cells (total) | extracted terms → curated codes | raw accuracy | exact code-set correct | agreement on both-reported cells |
|---|---|--:|--:|---|--:|--:|--:|
| disease | Sonnet 5 | 1/3 | 112 | Healthy → NCIT:C115935 | 1.00 | 1.00 | 1.00 |
| disease | Haiku 4.5 | 3/3 | 336 | Healthy → NCIT:C115935 | 1.00 | 1.00 | 1.00 |
| body_site | Sonnet 5 | 1/3 | 182 | Stool, feces → UBERON:0001988 | 0.38 | 1.00 | 1.00 [0.31–1.00] |
| body_site | Haiku 4.5 | 3/3 | 495 | Stool, feces → UBERON:0001988 | 0.32 | 1.00 | 0.92 [0.84–1.00] |
| treatment | Sonnet 5 | 0/3 | 0 | — | — | — | 0.50 |
| treatment | Haiku 4.5 | 1/3 | 31 | Insulin replacement therapy → NCIT:C29711, SCDO:0000067 | 0.00 | 0.00 | 0.00 |

For disease, every coded cell was a PasolliE_2019 control labelled "Healthy", and the extracted value
already matched the curated label. For body site, harmonization resolved the surface forms "Stool" and
"feces" to the curated UBERON code, so exact code-set correctness was 1.00 where raw string accuracy against the curated label was
0.32–0.38. That is a real but narrow result: one concept and two surface forms. For
treatment, the 31 coded cells came from one Haiku 4.5 run on Heitz-BuschartA_2016. The study-level value
"Insulin replacement therapy" had been propagated to every matched sample and mapped to "Therapeutic
Insulin" (NCIT:C581), whereas the curated codes were an anti-diabetic agent class (NCIT:C29711, 27 cells)
and SCDO:0000067 (10 cells), varying by sample. No coded cell matched. Any-shared-code scoring gave the
same values as exact matching on every row, because no coded cell had a multi-code value.

Agreement — whether the extracted and curated *values* map to the same code set — is not correctness.
Sonnet 5's treatment agreement of 0.50 came from NayakRR_2021, where the study-level value "Methotrexate"
was propagated to all 34 matched samples. It agreed with the 17 samples curated "MTX" (both NCIT:C642) and
disagreed with the 17 curated "no". The mapper also assigned the curated values "no" and "Not applicable"
to Nicotinamide Riboside (NCIT:C158078), so agreement between two such values would count as a match
without either being correct. These cases do not arise in the correctness column, which compares with
the curators' identifiers.

![Ontology harmonization](figures/fig3_harmonization.png)

**Figure 3. Ontology harmonization on identity-matched coded cells.** For each field and model, open
circles show raw string accuracy and filled circles show exact agreement between the extracted value's
OntologyMapper code set and the curated ontology identifier, on the same cells. Diamonds (hidden where
equal) show the supplementary any-shared-code measure. Values are medians over runs with coded cells;
the annotation gives the number of coded cells and contributing runs. Rows without any coded cell
(Sonnet 5 treatment) are omitted. The coded cells contain one disease term, two body-site terms, and one
treatment term.

### 3.8 Comparison with the earlier analysis

An earlier version of this analysis reported presence precision of 0.99 (Sonnet 5) and 0.90 (Haiku 4.5)
under positional scoring, 784 false positives for Haiku 4.5, and 100% ontology correctness. That analysis
combined outputs from two pipeline versions and scored them with the rules this revision replaces. Three
differences account for most of the change:

1. **Metric semantics.** Presence metrics count a wrong value as a hit. On the earlier outputs and their
   six-study identity-aligned subset, presence precision was 0.99 (Sonnet 5) and 0.95 (Haiku 4.5), but
   value-aware precision was 0.62 and 0.41.
2. **Propagation.** The 588 LiJ_2017 false positives attributed to per-sample biomarker over-assertion
   were a 16-item list of cohort-level biomarker findings that the model had reported as a study-level
   value and that fan-out then copied onto all 196 records (196 × 3 biomarker fields). Under the scoped
   rule, the same kind of study-level list is not propagated.
3. **Ontology scoring.** The earlier "100% correct" required only one shared code between the extracted
   and curated code sets. Cohort-wide values such as "Healthy; Hypertension; Pre-hypertension" passed
   for every individual; exact code-set matching on the same earlier cells gave 156 of 162 (Sonnet 5)
   and 156 of 352 (Haiku 4.5) for disease.

Retrieval also changed between the two analyses (Section 3.2), so the present per-study enumeration is
not directly comparable to the earlier runs.

---

## 4. Discussion

### 4.1 What the benchmark supports

On ten cMD studies, most curated samples were never represented by an extracted record that could be
linked to them. Failures to enumerate, identify, or retrieve samples therefore dominated the end-to-end
result, and they did so more than errors in the values of matched records. Where a machine-readable run
manifest was retrieved, enumeration was complete for the curated accessions and identical across repeats
and models. Where samples had to be inferred from supplementary tables, both models selected wrong tables
— feature tables, figure source data, or another cohort — in three studies. Among matched records, value
precision was 0.48–0.62: a large share of reported values differed from the curated value, and some of
those differences are surface forms that harmonization addresses (Section 3.7).

Presence metrics would have described the same outputs as near-perfectly precise. We therefore report
value-aware metrics as primary and recommend that evaluations of metadata extraction state which of the
two they use. Likewise, a gold-blank cell with an extracted value is not by itself evidence of fabrication:
in the 22 such cells here, the asserted value occurred in the source text, and deciding whether it applies
to the sample requires reading the source.

The two models differed in failure pattern more than in accuracy. All four failed extractions were Sonnet
5 responses truncated at the configured output limit, and Haiku 4.5 produced the largest spurious
enumeration (1,448 feature rows). The study-cluster interval for the difference in end-to-end value F1
included zero, and with ten studies used during development these data do not support recommending one
model over the other.

### 4.2 Retrieval is a time-dependent input

The same code retrieved full text for two studies in July 2026 and not in September 2026. For one of them,
the endpoint changed within the benchmark: it answered the first request and refused later ones. Extraction
benchmarks that retrieve documents live are therefore not reproducible from code alone. They should record
every retrieval attempt, archive — or at least checksum — the text supplied to the model, and report
retrieval outcomes alongside accuracy. The attempt ledger and per-extraction retrieval records introduced
here made the two changes diagnosable; they do not make the runs repeatable. A study whose full text the
configured sources did not return at one date may be reachable by other routes or at another date; we did
not test, for example, whether archive-side BioProject links would have identified the QinJ_2012 cohort.

### 4.3 Propagation must respect field scope

Copying a study-level value into every sample record is convenient when the value genuinely describes every
sample (sequencing platform, extraction kit) and wrong when it describes the cohort (a disease list, a range
of ages, a set of biomarker findings). In the earlier analysis, unrestricted propagation turned a
study-level list of biomarker findings into 588 per-sample assertions and let cohort disease lists pass an
any-overlap ontology check. The scoped rule, together with a per-cell source record, blocked those cases
and made the remaining propagated cells auditable. It did not catch a cohort age range that the model had
already split into separate minimum and maximum fields, nor a single study-level treatment
("Methotrexate") that the model reported without subgroups although half of the curated NayakRR_2021
samples were untreated. Propagation rules therefore need information about
field semantics — which fields describe individuals and which values are cohort summaries. A schema
annotation supplies part of that information; the model's own output structure does not supply the rest.

### 4.4 Limitations

- **One domain, no held-out set.** All ten studies come from one resource and were used while the retrieval
  layer, table path, propagation rules, and harmonization corpora were developed. The results are a case
  study; they do not estimate performance on other cMD studies, other schemas, or other domains.
- **No baselines or ablations.** We did not compare against a deterministic manifest-only pipeline, direct
  extraction by an LLM without the deterministic components, or versions without individual components.
  The contribution of each component is therefore not established.
- **Small, unstable matched set.** End-to-end metrics depend on 102–284 matched curated rows from at most
  five studies, and the conditional metrics describe only those rows.
- **Scoring rules.** Value matching is exact after lowercasing, with a 5% numeric tolerance and no synonym
  handling, so value precision includes differences that curators would accept. Identity alignment uses
  three identifier columns and did not need compound keys here; subjects with multiple samples would
  require them.
- **Gold incompleteness.** Curated cells may be blank where the paper reports a value; the scorer counts
  such cells as false positives, and our source check is partial.
- **Repeats.** Three repeats describe run-to-run variation on these studies, not sampling uncertainty for a
  population of studies. Requests used API defaults, including adaptive thinking for Sonnet 5; other
  settings may change failure rates and accuracy.
- **Harmonization.** Corpora were chosen after inspecting these studies; the curated identifiers cover few
  distinct terms (Section 3.7); and the retrieval-augmented and LLM-review stages of OntologyMapper were
  not used.
- **Validation.** Output validation is structural. The system does not verify that values appear in or
  follow from the source, that field names and types conform to the target schema, or that enum values
  belong to the vocabulary.

### 4.5 Engineering follow-ups

The runs exposed defects that we did not fix during the benchmark, to keep the tagged snapshot fixed:
(i) the stop reason of each model response should be logged and truncated responses retried with a larger
output budget or a smaller field batch; (ii) usage for failed attempts should be recorded; (iii) when parsed
tables yield no sample rows, the extractor currently discards any per-sample rows emitted by the model and
does not run sample discovery; (iv) the wall-clock cap did not bound some attempts; and (v) the table path
should reject feature and figure-source tables more reliably, since spurious enumeration accounted for three
of the ten studies.

---

## 5. Conclusion

MetaExtractor populates a target schema from papers, supplementary tables, and sequence-archive manifests,
and records the source of every sample cell. On a ten-study curatedMetagenomicData case study evaluated with
identity-aligned, value-aware metrics, it recovered complete, stable sample sets where a run manifest was
available, but most curated samples were not linked to any extracted record because of enumeration errors,
missing identifiers, retrieval that changed over time, and truncated responses. Among linked records, value
precision was 0.48–0.62. Ontology mapping reproduced the curated codes for the one disease term and two body-site terms that
could be scored, which does not test harmonization beyond those terms. These results argue for reporting value-aware and end-to-end
metrics, logging retrieval as part of the experiment, and restricting propagation of cohort-level values;
they do not by themselves establish performance beyond the studies evaluated.

---

## Declarations

**Author contributions.** [AUTHOR CONTRIBUTIONS — CRediT roles]

**Funding.** [FUNDING]

**Competing interests.** [COMPETING INTERESTS]

**Data and code availability.** Source code, the target schema, study manifest, age-rule configuration,
ontology crosswalks, extraction outputs (JSON/CSV), per-attempt logs, the attempt ledger, and all scoring
outputs are available in the MetaExtractor repository [REPOSITORY URL AND ARCHIVAL DOI] at tag `bench-v2`
(extraction snapshot) and the subsequent analysis commit. `benchmarks/cmd_sonnet5/REPRODUCE.md` gives the
commands. The text retrieved for each extraction is identified by SHA-256 checksum in the ledger and is not
redistributed. Curated reference tables are from curatedMetagenomicDataCuration commit `41271711`
[CITE: curatedMetagenomicDataCuration repository].

## References

[REFERENCES — to be compiled from the [CITE: …] markers]
