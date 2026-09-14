**Assessment: substantial methodological revision is needed before journal submission.** The repository contains a useful extraction system and enough saved evidence to support a focused software paper. The current manuscript overstates what the evaluation establishes, and several central explanations contradict the saved results. Copyediting alone will not resolve these problems.

Reviewed 2026-09-14: the current working-tree `MANUSCRIPT.md`, extraction and evaluation code, benchmark drivers, local gold tables, saved extractions and summaries, harmonization crosswalks, and all three figures. Existing uncommitted changes were treated as the review target. The manuscript and implementation were not edited. No paid extractions or ontology builds were run.

**1. Publication blocker: the headline precision and recall measure field presence, including wrong values.**

Manuscript: lines 31–42, 328–338, 429–437, 682–704. Implementation: `src/metaextractor/evaluation.py:99` and `benchmarks/cmd_sonnet5/bench.py:391`.

The numerator is `TP_correct + TP_wrong`. Consequently, reporting a wrong disease, age, or treatment receives full credit in precision, recall, and F1 whenever the gold cell is populated. These are valid *reporting-status* metrics, but “precision 0.99,” “fails safe,” and recommendations based on avoiding wrong cells invite a different interpretation. Value accuracy also excludes assertions where gold is blank: its denominator is cells reported by both sides, not all attempted cells.

I recomputed the six-study identity-aligned results from saved extractions using the existing comparator, counting only value-correct cells in the numerator:

| Metric, median [min–max] across three repeats | Sonnet | Haiku |
|---|---:|---:|
| Value-correct precision | 0.619 [0.561–0.630] | 0.409 [0.366–0.412] |
| Value-correct recall on matched gold rows | 0.373 [0.339–0.385] | 0.287 [0.265–0.288] |
| Corresponding F1 | 0.466 [0.423–0.478] | 0.338 [0.307–0.338] |

Here precision is `TP_correct / (TP_correct + TP_wrong + FP)` and recall is `TP_correct / (TP_correct + TP_wrong + FN)`. These are diagnostic recalculations, not replacement whole-benchmark estimates: unmatched samples remain excluded, and the existing comparator permits numeric tolerance. Some raw mismatches may be legitimate lexical variants, so corrected harmonized scores should accompany raw scores.

**Required revision:** explicitly label presence metrics, report value-aware metrics with equations, and make identity-aware end-to-end results primary. Do not equate a gold-blank cell with demonstrated fabrication without checking the source: gold incompleteness and extraction over-assertion are different possibilities.

**2. Publication blocker: “100% correctness” accepts partially correct, overinclusive predictions.**

Manuscript: lines 44–48, 385–389, 598–655, 744–753. Implementation: `benchmarks/cmd_sonnet5/bench.py:335`, especially line 343; `harmonize/rescore.py` uses the same nonempty-intersection criterion.

The scorer tests `predicted_codes & gold_codes`, not exact equality. A prediction containing a correct code plus several incorrect codes passes. This is material in the saved data: both models assign the full disease list “Healthy; Hypertension; Pre-hypertension” to LiJ_2017 rows. Every gold group can overlap that list, even though it does not identify the individual subject's condition. Haiku's old PasolliE output similarly assigns multiple body sites to fecal samples.

Using the current crosswalks and the same old representative-run positional cells, I obtained:

| Field/model | Gold-coded cells | Any-overlap successes | Exact code-set successes |
|---|---:|---:|---:|
| Disease/Sonnet | 162 | 162 (100%) | 156 (96.3%) |
| Disease/Haiku | 352 | 352 (100%) | 156 (44.3%) |
| Body site/Sonnet | 162 | 162 (100%) | 162 (100%) |
| Body site/Haiku | 308 | 308 (100%) | 196 (63.6%) |

These figures expose the scoring weakness; they still inherit the old positional alignment and conditional denominator. Moreover, every coded body-site reference in this evaluation subset is feces. Hundreds of repeated cells do not demonstrate broad ontology-mapping capability.

**Required revision:** use exact set match and concept-level precision/recall for multivalued fields, retain an explicitly named any-hit metric only as supplementary information, and publish distinct terms, studies, and code frequencies. Separate mapping a correct input phrase from extracting the correct phrase for a particular sample. Remove the unconditional 100% claim.

**3. Publication blocker: the false-positive causal explanation is contradicted by the results.**

Manuscript: lines 459–464, 477–479, 535–548, 690–701. Evidence: `out_ms_refined/*_r*/summary.json` and identity-aligned rescoring.

Extra rows beyond `min(n_extracted, n_gold)` are discarded by the positional evaluator. They do not directly count as false positives. Misalignment can affect the leading rows, but that requires a within-study comparison to demonstrate.

For Haiku r1, the positional FP decomposition is LiJ_2017 = 588, Heitz-BuschartA_2016 = 31, LiSS_2016 = 165, and every other study = 0. Identity alignment retains 196 FPs from the latter two studies and excludes LiJ_2017 entirely. Thus the drop from 784 to 196 does not demonstrate removal of extra manifest-run errors; it removes the study containing the largest error block.

For Sonnet, positional FP totals are 192, 33, and 51 in r1/r2/r3. FanY contributes **zero FPs in every run**. The 192-FP run contains 165 from LiSS, 25 from Heitz, and 2 from Tett. FanY's sample counts are 319/510/510: two runs have 510, while the largest FP total occurs in the 319-row run. The attribution of FP variance to one FanY over-enumeration is false.

**Required revision:** rewrite the abstract and Sections 3.1–3.3/4.3 from per-study, per-run error tables. Compare positional and aligned scoring on the same studies before attributing a difference to alignment.

**4. Publication blocker: the harmonization table and figure cannot be interpreted as the stated before/after experiment.**

Manuscript: lines 366–370, 589–655. Implementation: `bench.py:303`, `bench.py:329`, and `figures/make_figures.py:206`.

First, raw accuracy and `correct_acc` use different denominators. For example, Sonnet disease compares raw accuracy over 309 TP cells with correctness over 162 coded cells. Figure 3 connects these as if it measures improvement on the same observations. On those 162 coded cells, raw correctness is already 156/162, rather than 156/309. There is also no mathematical rule that agreement “should” be below correctness when populations and criteria differ.

Second, harmonization still uses positional alignment, despite Section 3.1 correctly explaining why sample identity is necessary for value correctness. Third, results from `out_ms` omit the newly recovered populations; mapping determinism does not make accuracy independent of extraction inputs. For example, current refined Sonnet r1 has only 260/270 any-hit disease successes under the same diagnostic scorer, and refined runs introduce treatment cells with curated identifiers.

Finally, the advertised replacement of `rescore.py` by `bench.py harmonize` changes agreement from code-set intersection to equality. A read-only recomputation through the current shared evaluator gives disease agreement 0.505/0.310 for Sonnet/Haiku, rather than 0.751/0.709, and Haiku body-site agreement 0.758 rather than 1.000. `crosswalk_treatment.csv` is absent locally; the available inputs also do not reproduce the treatment agreement table.

**Required revision:** freeze the crosswalks and scoring semantics, regenerate the full table from the intended run set, and compare raw/harmonized accuracy on exactly the same identity-aligned cells. Disclose corpus selection informed by evaluation results; use held-out studies or terms to support generalization claims.

**5. Major code/claim mismatch: validation does not enforce faithfulness or target-schema conformance.**

Manuscript: lines 5–11, 125–145, 149–171, 225–233. Implementation: `src/metaextractor/output.py:13`, `extractor.py:201`, `extractor.py:248`.

`FieldResult.value` is `Any`; `fields` is an unconstrained name-to-result dictionary; sample rows are `dict[str, Any]`. Validation checks the result envelope, not supplied-schema field membership, required slots, value types, vocabulary membership, or evidence support. Sample discovery explicitly asks the model to construct identifiers encoding sample attributes. Model-generated prose values are parsed directly into the result; Python does not copy every such value from a verified source location. Even the table executor writes model-proposed melt category labels (`table_plan.py:347`).

The limited adapter does not implement arbitrary JSON Schema or all LinkML semantics. Static enums deliberately remain verbatim text, so raw output need not satisfy the target vocabulary. These are reasonable design choices if described as schema-guided extraction with downstream normalization, rather than guaranteed schema conformance and an inability to fabricate.

**Required revision:** narrow the title and safety claims, document supported schema features, and distinguish structural validation from source verification. If schema conformance is essential to the paper, implement and evaluate target-schema validation separately.

**6. Major code defect: propagation can turn cohort-level information into individual assertions.**

Manuscript: lines 228–233, 271–286, 517–524. Implementation: `extractor.py:613` and `extractor.py:710`.

Fan-out attempts subgroup matching against any string in a sample and otherwise copies the study-level value. This is unsafe for mixed-cohort diseases, treatments, biomarker summaries, and aggregate ages. The LiJ disease lists above are a concrete example. Calling downstream biomarker errors exclusively a model or prompt defect overlooks deterministic propagation as a potential causal contributor.

Age normalization is hard-coded to cMD field names and age categories, runs without consulting the target schema, and can add `age_min`/`age_max` sample fields that were not requested. It treats any numeric age as an individual age and does not perform unit checks. It preserves existing numeric bounds even when a specific age is present, contrary to the manuscript's claim that both bounds are set to that age. The fixed Elderly maximum of 130 also needs an explicit semantic justification.

**Required revision:** preserve field scope and propagate only information known to apply to the target sample or confirmed subgroup. Make age rules configurable, schema-gated, unit-aware, and separately evaluated.

**7. Major evaluation defect: identity alignment does not guarantee unique physical samples.**

Manuscript: lines 334–338, 415–428. Implementation: `bench.py:121` and `bench.py:130`.

The join keeps the first extracted row for a duplicate key, can reuse that row for multiple gold rows, takes only the first accession in a compound cell, and chooses the first candidate key with any overlap for the entire study. It does not validate uniqueness. A two-row example with repeated `subject_id=A` and ages 10/20 maps both gold rows to the age-10 extracted row. Subject identity also does not establish sample identity when subjects have multiple timepoints or body sites.

The reported aligned subset contains 339 of 1,089 gold rows (31.1%). Its metrics are useful conditional results but cannot establish accuracy over all samples. Different identifier namespaces are an entity-resolution gap, not proof that ingestion was impossible.

**Required revision:** validate key cardinality, represent pooled run accessions explicitly, use compound sample keys where necessary, and report matched, unmatched, ambiguous, and duplicate records. Count unmatched gold records in end-to-end recall. Evaluate extra records separately, distinguishing true out-of-scope runs from invalid sample enumeration.

**8. Major reproducibility gap: the refined results are a composite and the experimental snapshot is not recoverable from the methods.**

Manuscript: lines 300–318, 391–405, 558–565, 843–847. Implementation: `rerun_sra.py:1`, `multiseed.py`, `select_studies.py`, `.gitignore`.

`rerun_sra.py` copies the old output tree, then selectively reruns studies. Byte comparisons confirm reused outputs, including all three Haiku LiJ runs and all three Sonnet FanY runs. This does not invalidate reuse if unchanged behavior is established, but it is different from 60 fresh extractions under one documented refined snapshot. No per-run commit/prompt/schema/input hash establishes the claimed common code version.

The drivers rely on personal absolute paths and an external schema-attribute CSV. The selector currently defaults to 20 studies while the manuscript reports ten. The old outputs and disease corpus are gitignored, and their local availability does not establish public availability. First-attempt logs are overwritten by the same output path; the six initial failures and retry success need an immutable attempt ledger. Six initial failures among 60 initial runs is 10%; if six retries are included, it is 6/66 failed attempts. An observed zero final failures is not an estimated guarantee of zero risk.

The calls do not explicitly set temperature or a seed. Use “three repeated API runs” and report the actual request settings and run dates. Current official [Sonnet 5 documentation](https://platform.claude.com/docs/en/models/sonnet-5/whats-new-sonnet-5) describes default adaptive thinking and restrictions on non-default sampling parameters; omitted settings therefore need to be documented. The same page provides pricing, so missing entries in the local price table do not establish that the model cannot be priced.

**Required revision:** archive a tagged code snapshot, gold/schema versions, input and output checksums, cached retrieval artifacts or permitted retrieval manifests, complete attempt logs, crosswalks, and dependencies. Provide portable commands and an explicit reused-versus-rerun ledger. Record model-returned identifiers, usage, settings, and pricing dates.

**9. Major evidential gap: the domain-general and causal conclusions exceed the experimental design.**

Manuscript: lines 94–102, 274–287, 706–740, 744–753, 819–838.

There is one evaluation domain, ten studies used during iterative engineering, no held-out assessment, and no direct-extraction or deterministic-table baseline. Thus the experiment does not establish behavior on any schema-backed task or that corpus design generally dominates matcher design. The code contains domain-specific accession handling, aliases, and age rules. Repeated row counts establish count stability, not stable row identity, content, source retrieval, or semantic correctness.

Coverage-aware recall is an observed performance measure, not an ingestion-only ceiling: it still includes field omission and rewards wrong reported values. A ceiling would need an explicit bound based on available and correctly resolved samples/fields. Live external retrieval remains time-dependent even if its local scoring functions are deterministic.

**Required revision:** frame the current result as a microbiome case study. Add at least a deterministic-table/manifest baseline, a direct-LLM baseline, targeted retrieval and harmonization ablations, and a held-out evaluation. Use study-level paired comparisons or clustered uncertainty; three repeats measure sampling variability on these studies, not population-level generalizability. A second domain is needed for empirical claims of general-purpose performance.

**10. Factual claim requiring correction: QinJ_2012 was not retrieved by this pipeline; universal unreachability is not established.**

Manuscript: lines 27–28, 514–515, 723–725, 828–829.

A failed repository URL cannot establish that no full text or accession is reachable anywhere. During review, the public [NCBI BioProject record PRJNA422434](https://www.ncbi.nlm.nih.gov/bioproject/422434) explicitly linked the Qin paper and sequence data, and [JGI's SRA experiment record](https://gold.jgi.doe.gov/sraexperiment?id=SRX121979) identified SRP008047 under the study title. These do not prove that the existing pipeline would retrieve the correct curated cohort, but they refute the inference that accessions cannot be discovered without the missing full text.

**Required revision:** say “the configured retrieval sources did not recover full text or a manifest at the time of the benchmark.” Report endpoints, dates, failures, and identity validation, and treat repository search/link traversal as an untested recovery route.

**11. Provenance and auditability need a narrower description or implementation work.**

Manuscript: lines 229–233, 289–295. Implementation: `output.py:43`, `writers.py:58`, `bench.py:243`.

Structured provenance resides in study-level `fields`; sample rows are mostly scalars and lack per-cell evidence coordinates. The sample-level CSV branch returns before processing `include_provenance`, so `--csv-provenance` does not provide the promised provenance columns for sample rows. Age-derived sample values also lack individual derivation metadata. Table-selection logs are not an audit trail from each emitted cell to its source row and column.

The benchmark supplies no paper text for the evaluator's optional quote check, and records contract violations only when the faithfulness object is a dictionary even though it is a dataclass, yielding `null`. Consequently, a faithfulness mechanism exists in the library but is not substantively reported in this benchmark.

**Required revision:** distinguish study-level from per-sample provenance, retain source table/row/column and propagation/derivation records, and perform source-grounded audits before making non-fabrication claims.

**12. Presentation and submission preparation require a final consistency pass.**

The manuscript has no bibliography or in-text citations. At minimum cite the original [curatedMetagenomicData publication](https://pubmed.ncbi.nlm.nih.gov/29088129/), the specific curation release, related extraction systems, LinkML, retrieval resources, ontology resources, and MetaHarmonizer. Establish the methodological contribution relative to prior work rather than repeatedly asserting generality. Add author/affiliation information, funding and competing-interest declarations, and a durable data/code availability statement appropriate to the target journal.

Concrete corrections include:

- Figure 2's caption says Haiku has higher F1, while its displayed positional F1 is lower. The FP panel omits repeat whiskers despite the caption's broad uncertainty description.
- Figure 1 places discovery after extraction, unlike the implementation; it omits the central ENA/Unpaywall additions and labels Pydantic validation as enforcing faithfulness. Its top legend symbols are visibly clipped.
- Figure 3 connects different denominators and its legend overlaps the lower plotted row. Fix the scientific comparison before polishing the layout.
- The abstract says sample counts are stable without acknowledging the FanY exception; Section 3.2 says one repeat reaches 510 although the table shows two.
- Section 3.1 describes four accession-matched studies plus Pasolli while listing a six-study aligned set; there are five accession-matched studies plus Pasolli.
- Several “ingestion ceiling” and “agreement versus correctness” section references point to unrelated sections.
- “Exact/verbatim” matching actually lowercases and trims strings, sorts list values, and accepts a 5% numeric tolerance (`evaluation.py:284`). State these rules.
- `aggregate.py` renders integer FP counts as dashes because `_fmt` accepts only floats; this is visible in the advertised `AGGREGATE.md`.
- Figure data are manually transcribed in `make_figures.py`; generate them from versioned scoring outputs to prevent further drift.

**What is already supported and worth preserving.** The saved refined outputs do produce rows for nine studies, five manifest-fed studies align across all their gold rows under the present accession procedure, and most per-study row counts are stable across three repeats. The modular extraction/table architecture and retained outputs make failure analysis feasible. Distinguishing lexical agreement from reference correctness is a useful goal; the scorer must implement that distinction more strictly.

**Verification performed.** `python -m pytest -q` passed 125 tests; the separate alignment-test invocation also passed all six selected tests. I recomputed identity-aligned counts, presence/value metrics, positional FP contributions, and harmonization diagnostics using local saved inputs, and visually inspected all three figures. The diagnostic calculations did not overwrite benchmark outputs. Tests passing establishes the tested behavior, not publication validity. Fresh API behavior, the full ontology-build process, and every paper's evidence were not revalidated.

**Recommended revision order.** Fix entity alignment and scoring semantics first; audit fan-out and per-cell provenance second; regenerate all tables and figures from a frozen, documented experiment third; then rewrite the abstract and discussion around the supported results. Add held-out validation and baselines before making broad performance or deployment recommendations. A more defensible provisional title is “MetaExtractor: schema-guided metadata extraction from scientific literature and sequencing archives, evaluated on curatedMetagenomicData.”
