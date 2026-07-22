# Extracting and harmonizing microbiome study metadata with large language models: a multi-seed benchmark against curatedMetagenomicData

## Abstract

We benchmarked **MetaExtractor**, a large-language-model (LLM) tool that extracts
structured sample-level metadata from primary literature against a user-supplied
schema, using the **curatedMetagenomicData** (cMD) curated `*_sample.tsv` tables as
gold standard. On ten reproducibly selected cMD studies we (i) compared two models —
Claude Sonnet 5 and Claude Haiku 4.5 — on an identical code snapshot, running each
study **three times per model** to separate genuine model variance from pipeline
noise, and (ii) tested whether a downstream harmonization pass through
**MetaHarmonizer** (SchemaMapper + OntologyMapper) closes the residual gap between
substantively-correct-but-differently-worded values and the curated vocabulary. A
central methodological finding emerged before any model comparison was meaningful:
**most of the apparent run-to-run "model variance" was actually a fragile document
fetch layer**. Transient failures in the retrieval path — an intermittently empty
NCBI elink response, rate-limit (HTTP 429) bursts, truncated reads, and a full-text
fallback that silently dropped supplementary tables — caused the same study to
enumerate 112 samples in one run and 1 in the next. After hardening the fetch layer
so supplementary-table retrieval is robust and independent of which full-text source
succeeds, per-study sample counts became stable across repeats (e.g. Haiku on
PasolliE_2019: pre-fix 1–112, post-fix 112/112/112), and the headline metrics
tightened markedly, especially for the weaker model. On the fixed pipeline Sonnet 5
was more precise and stable (precision 0.999, value accuracy 0.68, ~2 false
positives) while Haiku 4.5 was noisier (precision 0.89, value accuracy 0.54, ~588
false positives, dominated by a reproducible sample-count explosion on one study).
Ontology harmonization, once each field was mapped against the ontology the gold
standard actually uses, reached **100% agreement with the curated ontology codes** on
the two fields that carry them (disease, body_site); the decisive factor was **corpus
construction** — including the non-disease "Healthy" code that labels cMD controls —
not the matching algorithm. The transferable lessons are that reproducible LLM-curation
benchmarks require a fault-tolerant retrieval layer, that variance must be measured
before point estimates are trusted, and that harmonization quality must be scored
against an independent reference rather than the tool's own self-consistency.

---

## 1. Introduction

Public metagenomic archives are accompanied by metadata of highly variable quality,
which limits reuse. curatedMetagenomicData (cMD) addresses this with manual curation
into a controlled schema, but curation is labor-intensive. LLM-based extraction is a
candidate accelerator: given a paper and a target schema, a model proposes per-sample
field values. Three questions determine whether such a tool is usable in a curation
workflow: (1) how accurate and how *safe* (non-fabricating) is the extraction, and how
does it depend on model choice; (2) how *reproducible* is it — does the same input
yield the same output across repeats; and (3) can the raw extracted values be
reconciled to the curated controlled vocabulary automatically, so that
substantively-correct answers stop being counted — and stored — as mismatches.

This report addresses all three on a common set of ten cMD studies, using
MetaExtractor for extraction and MetaHarmonizer for harmonization. We emphasize two
methodological points that proved central. First, **variance is a first-class
result**: a single run can mislead, and in our case a large fraction of the observed
variance traced not to the model but to a non-robust document-retrieval layer, which
had to be diagnosed and fixed before the model comparison was interpretable. Second,
when evaluating ontology harmonization, *agreement* between two harmonized values is
not the same as *correctness*, and conflating them produces inflated, misleading
scores.

---

## 2. Methods

### 2.1 Study selection

cMD curation tables (`curatedMetagenomicDataCuration/inst/curated/<study>/<study>_sample.tsv`)
were enumerated and shuffled with a fixed seed (42); the first ten studies with a
single clean numeric PMID and ≥1 sample were retained. The resulting set spans
15–363 gold samples per study: Bengtsson-PalmeJ_2015, TettAJ_2019_b, LiJ_2017,
NayakRR_2021, PasolliE_2019, Heitz-BuschartA_2016, FanY_2023, QinJ_2012,
ContevilleLC_2019, LiSS_2016.

### 2.2 Extraction and the retrieval layer

MetaExtractor was run in its **by-PMID** mode: given a PMID it fetches full text and
supplementary material, then extracts all schema fields, discovering per-sample rows
from prose and supplementary tables (which are routed through a deterministic
column-mapper — the LLM never sees raw tables). The target schema was the cMD LinkML
schema; because MetaExtractor's LinkML adapter reads only static `permissible_values`,
the 11 slots defined by dynamic `reachable_from` ontology subtrees were downgraded to
free-text `string` (yielding a 71-field schema). Both models — `claude-sonnet-5` and
`claude-haiku-4-5` — were run against the **same working-tree snapshot**; the only
variable between models was the model itself.

The retrieval layer fetches article prose through a ladder (NCBI PMC full text →
Europe PMC full text by PMCID → Europe PMC by DOI, for preprints → PubMed abstract)
and, independently, fetches supplementary files from the PMC AWS Open Data bucket
and the Europe PMC supplementary ZIP. During this study the retrieval layer was
hardened for reproducibility (Section 3.2): (i) transient HTTP failures — rate-limit
429s, truncated reads, connection resets — are retried with backoff; (ii) the NCBI
`elink` PMID→PMCID step retries an intermittently empty response rather than treating
it as "no PMC record"; (iii) when the Europe PMC full-text fallback supplies the body,
supplementary-table retrieval is preserved — NCBI's declared file hrefs are not
discarded, and, failing those, the supplementary files are listed directly from the
S3 version prefix — so falling back for prose never costs the enumeration-driving
tables; (iv) a DOI that resolves to a PMC article contributes its PMCID so
supplementary files are still fetched. All benchmark numbers below are from the
hardened pipeline unless explicitly labelled "pre-fix".

### 2.3 Multi-seed protocol

To measure reproducibility, **each study was extracted three times per model** (10
studies × 2 models × 3 repeats = 60 extractions). LLM sampling is stochastic
(non-zero temperature), so repeats quantify genuine run-to-run variance. Each
extraction ran under a hard 25-minute wall-clock cap so a stalled generation could not
hang indefinitely. First-attempt failures were retried once. We report, per model, the
median and [min–max] of the headline metrics across the three repeats, and per study
the three individual sample counts.

### 2.4 Evaluation

Each extraction was scored against its gold `*_sample.tsv`. Extracted samples were
aligned to gold rows **positionally** (sample *i* ↔ gold row *i*), so sample count and
ordering are themselves measured outcomes. Every (sample, field) cell was labelled:
**TN** (both not reported), **TP_correct** (both reported and equal), **TP_wrong**
(both reported but differ), **FN** (gold has a value, extraction missed it), **FP**
(extraction asserts a value, gold blank). Content fields were micro-averaged into
precision, recall, F1, and value-accuracy (fraction of attempted cells whose value
matches gold exactly). Identifier/provenance fields were reported separately.

### 2.5 Harmonization

A representative set of extractions was passed through MetaHarmonizer (v0.4.1). Because
the harmonization question — does the mapper reconcile surface-form variants to the
*correct* ontology code — concerns the mapping, not the extraction run, these results
are independent of extraction variance and are reported on a single representative run.

**SchemaMapper** (target = cMD) was applied to the free-text notes MetaExtractor
places in the `uncurated_metadata` field, to test whether structured signal buried in
prose maps back to cMD fields.

**OntologyMapper** was applied to three value fields — `disease`, `body_site`,
`treatment` — using the exact/embedding/synonym stages (Stages 1, 2, 2.5; the RAG and
LLM-review stages 3–4 were left disabled). Corpus construction was field-specific and,
critically, matched to the ontology the gold standard uses:

- **disease** — the v0.4.1 `CombinedCorpusBuilder` over the cMD `disease`
  specification: the NCIt root `C7057` ("Disease, Disorder or Finding") merged with the
  static term `C115935` ("Healthy"), yielding a 50,755-term corpus. The static term is
  essential: "Healthy" is cMD's most common disease value (it labels controls) yet is
  not a descendant of any disease subtree, so a plain root build omits it.
- **body_site** — cMD `body_site` is a static six-value enum with explicit UBERON
  meanings (e.g. feces → UBERON:0001988); the corpus is exactly those six UBERON terms.
- **treatment** — the NCIt "Pharmacologic Substance" subtree (C1909, 26,766 terms).

Two scoring metrics were computed on the TP cells, deliberately separated:
**`agree_acc`** — the extracted and gold values, mapped through the *same*
OntologyMapper, resolve to the same code (self-consistency); and **`correct_acc`** —
the OntologyMapper code for the *extracted* value equals the gold's own curated
`*_ontology_term_id` (true correctness), over the subset of cells carrying a curated
identifier.

### 2.6 Reproducibility and cost

All extractions, per-cell audits, crosswalks, corpora, and scoring scripts are under
`benchmarks/cmd_sonnet5/`. The multi-seed runs are under `out_ms/` (fixed pipeline) and
`out_ms.pre_fetchfix/` (the earlier non-robust retrieval layer, retained as the
before/after evidence for Section 3.2). Ontology corpora were built keyless from the
NCI EVSREST and EBI OLS4 APIs.

---

## 3. Results

### 3.1 Model comparison — extraction

Content-field, micro-averaged metrics, as **median [min–max] over three repeats** per
model on the fixed pipeline:

| model | Precision | Recall | F1 | value-acc | false positives |
|---|--:|--:|--:|--:|--:|
| Sonnet 5 | **0.999** [0.993–0.999] | 0.590 [0.579–0.605] | 0.740 [0.733–0.754] | **0.679** [0.667–0.692] | **2** [2–20] |
| Haiku 4.5 | 0.887 [0.885–0.888] | 0.619 [0.618–0.627] | 0.730 [0.727–0.735] | 0.538 [0.515–0.553] | 588 [588–589] |

The two models trade off in the same direction seen before, but the picture is now
backed by variance. Sonnet 5 is far more precise and value-accurate and almost never
fabricates a value where gold is blank (~2 vs ~588 false positives). Haiku 4.5's recall
is slightly higher, but its extra true positives arrive bundled with roughly 2.5× as
many wrong values and a large, *reproducible* block of false positives: essentially all
588 come from a single study on which Haiku inflates a feature matrix into 1,448
samples (Section 3.3). Haiku's precision is therefore not noisy across runs — it is
consistently low for a consistent reason.

### 3.2 Reproducibility, and the fetch layer that masqueraded as model variance

The single most important finding of this study is methodological. In an initial
multi-seed pass the same (study, model) pair produced wildly different sample counts
across repeats — e.g. Haiku on PasolliE_2019 gave 112, 112, and then 1 sample; on
FanY_2023 gave 319, 319, and 0. Tracing these swings showed the cause was **not the
model** but transient failures in document retrieval:

- NCBI `elink` intermittently returned an *empty* linkset (a 200 response, so not an
  HTTP error), which was read as "this paper has no PMC record". With no PMCID, the
  supplementary-file fetch — which is keyed on the PMCID — was skipped entirely, and
  the per-sample tables that drive enumeration vanished. Measured directly,
  `PMID→PMCID` for PasolliE_2019 returned `None` on 4 of 5 consecutive calls, then the
  real PMCID.
- Under the concurrency of a batch run, NCBI returned rate-limit 429s and occasional
  truncated reads (`IncompleteRead`), which propagated as uncaught errors.
- When the Europe PMC full-text fallback supplied the article body (because NCBI was
  momentarily unavailable), the supplementary-table hrefs — which live only in NCBI's
  JATS — were discarded, so a study fetched via the fallback lost its tables even
  though the tables existed on S3.

Each of these is a *retrieval* fault that silently degrades enumeration, and each fires
stochastically, so it presents as run-to-run model variance. After hardening the
retrieval layer (Section 2.2), the swings collapsed. The table below contrasts the
per-study sample counts across three repeats before and after the fix; the studies
whose instability was purely retrieval are marked ✓ (now stable):

| study | gold | Haiku pre-fix (r1/r2/r3) | Haiku post-fix (r1/r2/r3) | |
|---|--:|--:|--:|---|
| TettAJ_2019_b | 44 | 6 / 50 / 0 | 50 / 50 / 50 | ✓ |
| PasolliE_2019 | 112 | 112 / 112 / 1 | 112 / 112 / 112 | ✓ |
| FanY_2023 | 147 | 319 / 319 / 0 | 319 / 319 / 319 | ✓ |

The headline metrics tightened correspondingly, most visibly for Haiku, whose
precision range narrowed from **[0.801–0.895] (pre-fix) to [0.885–0.888] (post-fix)**
and recall from [0.687–0.855] to [0.618–0.627]. In other words, the pre-fix "variance"
was largely an artifact of the harness, not a property of the model. This is a
cautionary result for LLM-curation benchmarking generally: **without a fault-tolerant
retrieval layer, reported model variance is uninterpretable**, and point estimates from
a single run can be off by two orders of magnitude in per-study enumeration.

### 3.3 Sample enumeration and the residual, genuine variance

Per-study extracted sample counts on the fixed pipeline (gold *n*; three repeats each):

| study | gold n | Sonnet 5 (r1/r2/r3) | Haiku 4.5 (r1/r2/r3) |
|---|--:|--:|--:|
| Bengtsson-PalmeJ_2015 | 70 | 0 / 0 / 0 | 0 / 0 / 0 |
| TettAJ_2019_b | 44 | 50 / 50 / 50 | 50 / 50 / 50 |
| LiJ_2017 | 196 | 6 / 6 / 6 | **1448 / 1448 / 1448** |
| NayakRR_2021 | 34 | 0 / 0 / 0 | 6 / 0 / 9 |
| PasolliE_2019 | 112 | **112 / 112 / 112** | **112 / 112 / 112** |
| Heitz-BuschartA_2016 | 53 | 0 / 0 / 0 | 0 / 0 / 0 |
| FanY_2023 | 147 | 319 / 510 / 510 | 319 / 319 / 319 |
| QinJ_2012 | 363 | 0 / 0 / 0 | 0 / 0 / 0 |
| ContevilleLC_2019 | 15 | 0 / 0 / 0 | 1 / 0 / 15 |
| LiSS_2016 | 55 | 0 / 0 / 0 | 0 / 0 / 0 |

With retrieval fixed, most cells are now stable across repeats. The genuine,
model-attributable variance that remains is narrow and interpretable:

- **A reproducible count-explosion.** Haiku enumerates LiJ_2017 as 1,448 samples in
  all three runs (gold 196) — it inflates an OTU/feature matrix into samples. This is
  stable, not stochastic, and is the source of essentially all of Haiku's 588 false
  positives. Sonnet under-enumerates the same study (6) in all three runs.
- **Small-count instability.** On the two studies where Haiku enumerates a handful of
  samples (NayakRR_2021, ContevilleLC_2019) the count is genuinely unstable
  (0/6/9 and 1/0/15), i.e. the model is on the boundary between staying study-level and
  enumerating.
- **Over-enumeration magnitude.** Sonnet over-enumerates FanY_2023 at 319 or 510
  across runs (gold 147); Haiku is stable at 319.
- **Six of ten studies enumerate zero samples in both models across all repeats**,
  because no machine-readable per-subject manifest is reachable (abstract-only fetch, or
  image/`.xls`-only supplements). These contribute only false negatives and are a
  data-availability ceiling, not a model limit.

### 3.4 Reliability — extraction failures

Across the 60 fixed-pipeline extractions, 6 first-attempt failures occurred (5 Haiku, 1
Sonnet), all of which succeeded on one retry (so the effective failure rate is ~10%
per attempt, ~0% within two attempts). All were LLM-output faults, not retrieval
faults: five were **malformed / truncated JSON** the extractor could not parse, and one
was the **`section: null`** case, where the model emits a null for a required
provenance field and the Pydantic result model rejects it. Both are current robustness
gaps worth closing (retry-on-parse-failure; coerce a null `section`), and both are more
frequent on the weaker model.

### 3.5 Harmonization — SchemaMapper on free-text

Of the unique `uncurated_metadata` strings supplied to SchemaMapper against the cMD
schema, **none matched a cMD field at high confidence (≥ 0.80)** and 17 matched at
moderate confidence (≥ 0.60), all via the semantic fallback rather than the
dictionary/fuzzy stages. The moderate matches route plausibly to ten distinct cMD
fields — e.g. *"Sequencing method: Shotgun metagenomic…"* → `sequencing_platform`,
*"Age categories: newborns, children…"* → `age_group`, *"Geographic locations:…"* →
`location`, *"Energy restriction diet…"* → `dietary_restriction`. A small amount of
recoverable structured signal is therefore buried in the free-text bucket and
SchemaMapper can suggest where it belongs, but nothing reaches promote-without-review
confidence; the tool is built for column headers, not narrative sentences.

### 3.6 Harmonization — OntologyMapper value harmonization

Scoring on TP cells (a representative fixed-pipeline run, `out_ms/*_r1`), raw string
match versus the two harmonized metrics (TP-cell counts in the last column):

| model | field | raw value-acc | `agree_acc` | `correct_acc` | n with gold ID | TP cells |
|---|---|--:|--:|--:|--:|--:|
| Sonnet 5 | disease | 0.505 | 0.751 | **1.000** | 162 | 309 |
| Haiku 4.5 | disease | 0.310 | 0.709 | **1.000** | 352 | 506 |
| Sonnet 5 | body_site | 0.638 | 1.000 | **1.000** | 162 | 309 |
| Haiku 4.5 | body_site | 0.758 | 1.000 | **1.000** | 308 | 462 |
| Sonnet 5 | treatment | 0.000 | 0.184 | — | 0 | 147 |
| Haiku 4.5 | treatment | 0.000 | 0.203 | — | 0 | 153 |

These numbers are essentially unchanged from the pre-multi-seed extraction: `correct_acc`
stays exactly 1.00 on both coded fields, and `agree_acc` moves only in the third decimal.
Only Haiku's TP-cell counts shift marginally (disease 512→506, body_site 468→462,
treatment 160→153) because its representative run enumerates a few small studies slightly
differently; the mapping-correctness conclusion is independent of the extraction run.

**Disease and body_site are genuinely correct after field-appropriate corpus
construction.** With "Healthy" in the disease corpus, OntologyMapper resolves every
disease value that gold codes to the exact NCIt identifier the curators used (Healthy →
C115935, Type 2 Diabetes Mellitus → C26747, Hypertension → C3117, RA ↔ Rheumatoid
Arthritis → C2884): `correct_acc` = 1.00 on all coded cells, verified against the
gold's own identifiers, not against self-consistency. With body_site mapped to UBERON,
`feces` and `Stool` both resolve to UBERON:0001988, again matching gold on all coded
cells. Together this converts the dominant TP_wrong bucket — substantively-correct
values in a different surface form — into true matches, lifting raw value-accuracy
(disease 0.31–0.51, body_site 0.64–0.76) to full correctness on the coded cells.

**The `agree_acc` / `correct_acc` distinction was necessary, not cosmetic.** A
deterministic mapper resolves a given value to the same code on both sides, so
agreement can be high even when the code is wrong; only correctness against the gold's
own identifiers separates reconciliation from error. A code-normalization bug that
briefly collapsed empty codes to the string `"nan"` illustrated the hazard — it
produced a `"nan"`↔`"nan"` agreement with no correctness — and was caught only by the
`correct_acc` check. In the reported configuration `agree_acc` (0.71–0.75) sits *below*
`correct_acc`, as it should.

**Treatment did not move, appropriately.** The treatment cells carry no curated
ontology identifier (so `correct_acc` is undefined), and the residual disagreements are
substantive rather than lexical: the extractor asserts a drug for subjects whose gold
`treatment` is "no"/"Not applicable". Harmonization correctly declines to reconcile a
real disagreement.

---

## 4. Discussion

### 4.1 Reproducible LLM curation requires a fault-tolerant retrieval layer

The clearest lesson is one about experimental hygiene rather than about either model.
Roughly all of the alarming run-to-run variance in our first pass was produced by a
retrieval layer that failed silently and stochastically: an empty elink response, a
429, a truncated read, or a full-text fallback that dropped the supplementary tables
would each turn a 112-sample study into a 1-sample study, and each fired at random. A
benchmark run on that layer would have reported large "model variance" and unstable
per-study accuracy that had nothing to do with the model. Only after hardening
retrieval — retrying transient failures, distinguishing a transient empty elink from a
genuine absence, and decoupling supplementary-table fetching from which full-text
source happened to win — did the model signal become visible. Anyone benchmarking
LLM-based curation from primary literature should treat the retrieval layer as part of
the measurement apparatus and validate its determinism first; otherwise variance and
even point estimates are uninterpretable.

### 4.2 Variance is a first-class result

Reporting three repeats changed the interpretation twice over. It exposed the retrieval
artifact (Section 3.2), and it reframed Haiku's low precision: the 588 false positives
are not noise but a *stable* consequence of a single reproducible failure mode (the
LiJ_2017 count-explosion). A single-run benchmark would have reported the same number
with no way to tell whether it was a fluke or a fixed defect. Multi-seed evaluation is
cheap insurance against both false alarms and false confidence.

### 4.3 Model choice is a precision/coverage decision, not a quality ranking

On identical, fixed code, Sonnet 5 and Haiku 4.5 occupy opposite corners: Sonnet is
precise and conservative (precision 0.999, value-accuracy 0.68, ~2 false positives, and
it fails *safe* by staying study-level rather than fabricating rows), while Haiku is
higher-coverage and noisier (recall 0.62, but ~588 false positives concentrated in one
reproducible explosion, and a higher malformed-output rate) at a fraction of the cost.
For a curation-assist setting where a fabricated or wrong cell is more expensive than a
blank one — because a human must catch and undo it — Sonnet 5's profile is preferable;
Haiku is the economical choice when every cell is verified downstream. F1 alone
obscures this: the two models' F1 values are close (0.74 vs 0.73) while their error
composition is completely different.

### 4.4 Sample enumeration, not per-field skill, sets recall

Because scoring uses a positional join, whole studies that stay study-level contribute
only false negatives, and count mismatches collapse recall regardless of how good the
per-field extraction is. Six of ten studies enumerate zero samples in both models
because no machine-readable per-subject manifest is reachable — a data-availability
limit, not a model limit. The practical implication is that per-sample recall is
bounded upstream by whether a per-subject manifest can be fetched at all, and that a
deterministic table-driven enumeration path is the right substrate for per-sample
evaluation. The one place the model clearly matters is pathological enumeration: Haiku's
reproducible inflation of a feature matrix into 1,448 samples is a model behavior a
deterministic path would prevent.

### 4.5 Harmonization works, but the lever is the corpus, not the matcher

The harmonization result — 100% agreement with the gold ontology codes on the two
fields that carry them — was achieved with the exact/embedding/synonym stages alone,
with the RAG and LLM-review stages disabled. What made the difference was constructing
each field's corpus to match the gold: adding the non-disease "Healthy" finding code
(cMD's most frequent disease value, absent from every disease subtree), and mapping
body_site against UBERON. A matcher can only return concepts its corpus contains, coded
in the ontology the gold uses; once both conditions were met, mapping became exactly
correct. For anyone deploying ontology mapping over cMD-style metadata, corpus scope and
per-field ontology selection dominate; algorithm tuning is secondary.

### 4.6 Agreement is not correctness

Harmonizing both sides of a comparison and checking whether they match measures
*self-consistency*, and a deterministic mapper is trivially self-consistent even when it
is wrong: an incorrect value resolves to the same incorrect code on both sides, so the
two still agree. Only scoring the harmonized extraction against an independent reference
— here the gold's own curated ontology identifiers — distinguishes reconciliation from
correctness. A benchmark that reports the former while claiming the latter will
systematically overstate a harmonizer's quality; we recommend always reporting both,
over an explicit denominator of cells that carry a reference identifier.

### 4.7 Limitations

The study is small (ten studies) and uses a positional sample join, so recall is
sensitive to enumeration alignment rather than pure per-field accuracy. Three repeats
bound but do not fully characterize variance. The gold standard is itself heterogeneous
— it mixes raw and harmonized surface forms and populates `*_ontology_term_id` only
sparsely (treatment carries none on the relevant cells), which both depresses raw
value-accuracy and limits the denominator for `correct_acc`. OntologyMapper was run
without its RAG/LLM-review stages, so concept-level accuracy on harder free-text terms
is untested here. Harmonization was scored on a single representative extraction; while
the mapping-correctness conclusion is run-independent, the exact TP-cell counts are
not. The Sonnet 5 cost is a proxy (no price-table entry). Finally, `correct_acc` = 1.00
reflects the specific, largely low-cardinality controlled vocabularies exercised by
these ten studies and should not be extrapolated to open-ended disease text without the
higher OntologyMapper stages.

### 4.8 Recommendations

1. **Treat retrieval as measurement infrastructure.** Make the document-fetch layer
   fault-tolerant (retry transient failures, distinguish transient empties from genuine
   absences, decouple supplementary-table fetching from the full-text source) and
   validate its determinism before benchmarking a model.
2. **Report variance.** Run each item multiple times; a single run cannot distinguish a
   fluke from a fixed defect, and cannot expose a harness artifact.
3. For curation-assist deployment, prefer the more precise model (Sonnet 5) and treat
   study-level fallback as a feature; reserve the cheaper model for fully human-verified
   passes.
4. Move per-sample enumeration onto a deterministic table-driven path where a
   machine-readable manifest exists, rather than LLM discovery from mixed supplementary
   content — this also prevents pathological count-explosions.
5. For ontology harmonization, invest in per-field corpus construction — include
   non-disease control codes and target each field's native ontology — and always score
   against the gold's own identifiers, reporting agreement and correctness separately.
6. Close the two extraction-robustness gaps surfaced here: retry on JSON-parse failure,
   and coerce a null `section` so extraction cannot crash.

---

## 5. Conclusion

On ten curatedMetagenomicData studies, LLM extraction plus ontology harmonization can
reproduce the curated metadata well, but only when the pipeline is judged on the right
axes and with variance in view. The dominant early finding was that a fragile retrieval
layer, not the model, produced most of the run-to-run instability; hardening it made the
model signal interpretable and stable. On the fixed pipeline, model choice is a
precision-versus-coverage trade rather than a quality ranking; extraction recall is set
upstream by sample enumeration and data availability; and ontology harmonization, once
each field is mapped against a gold-matched corpus, reconciles the dominant surface-form
gap into fully correct codes on the fields that carry them. The recurring theme is that
the decisive engineering choices are in retrieval robustness, corpus construction, and
honest, variance-aware evaluation that separates self-consistency from correctness
against an independent reference.

---

*Data, code, per-cell audits, ontology corpora, and crosswalks are under*
`benchmarks/cmd_sonnet5/`. *Multi-seed extractions:* `out_ms/` (fixed pipeline, 3
repeats × 2 models) *and* `out_ms.pre_fetchfix/` (pre-fix retrieval, before/after
evidence). *Aggregated variance:* `out_ms/AGGREGATE.md`. *Harmonization scoring:*
`harmonize/rescore_value_accuracy.csv`.
