# MetaExtractor × curatedMetagenomicData — Sonnet 5 vs Haiku 4.5 (multi-seed)

Model comparison scored against `curatedMetagenomicData` (cMD) `*_sample.tsv` tables
as ground truth with the `curatedmetagenomicdata` LinkML target schema. Both models
run the **identical code, schema, studies, and eval** — only the model differs.
**Each study was run three times per model** (60 extractions) to separate genuine
model variance from pipeline noise; results are reported as **median [min–max]** over
the three repeats.

> **Read this first — the retrieval layer had to be fixed before the comparison was
> meaningful.** An initial multi-seed pass showed the same (study, model) pair giving
> wildly different sample counts across repeats (e.g. Haiku PasolliE_2019: 112, 112,
> **1**). The cause was **not the model** but transient document-fetch failures — an
> intermittently empty NCBI `elink` response (→ no PMCID → supplementary tables
> skipped), rate-limit 429s, truncated reads, and a full-text fallback that dropped
> the supplementary hrefs. After hardening retrieval (retry transient failures;
> distinguish a transient-empty elink from a genuine absence; recover S3 supplementary
> independent of which full-text source wins), the swings collapsed. All numbers below
> are the **fixed** pipeline (`out_ms/`); the pre-fix run is kept in
> `out_ms.pre_fetchfix/` as before/after evidence.

- **Path:** by-PMID — fetch full text + supplementary; per-sample rows come from
  supplementary tables via a deterministic column-mapper (the LLM never sees raw
  tables) and from prose.
- **Target schema:** `cmd.clean.linkml.yaml` (11 `reachable_from` ontology enums
  downgraded to string by `make_clean_schema.py`).
- **Gold:** `curatedMetagenomicDataCuration/inst/curated/<study>/<study>_sample.tsv`.
- **Studies:** the first 10 of the seed=42 draw (`select_studies.py`).
- **Join:** extracted samples ↔ gold rows **positionally** (no `--align-key`).
- **Outputs:** `out_ms/<model>_r<k>/` (k = 1..3); aggregate in `out_ms/AGGREGATE.md`.

## Headline (content fields, micro-averaged; median [min–max] over 3 repeats)

| model | Precision | Recall | F1 | value-acc | false positives |
|---|--:|--:|--:|--:|--:|
| **claude-sonnet-5** | **0.999** [0.993–0.999] | 0.590 [0.579–0.605] | 0.740 [0.733–0.754] | **0.679** [0.667–0.692] | **2** [2–20] |
| **claude-haiku-4-5** | 0.887 [0.885–0.888] | 0.619 [0.618–0.627] | 0.730 [0.727–0.735] | 0.538 [0.515–0.553] | 588 [588–589] |

**Sonnet 5 is precise and stable; Haiku is noisier and consistently low-precision.**
Sonnet wins precision and value-accuracy by a wide margin and almost never fabricates
(~2 vs ~588 FPs). Haiku's ~588 false positives are not run-to-run noise — essentially
all come from a *reproducible* count-explosion on one study (LiJ_2017 → 1,448 samples
every run). Post-fix, both models' metrics are tight across repeats; the pre-fix Haiku
precision range was [0.801–0.895], now [0.885–0.888].

## Per-study sample enumeration (gold n; three repeats each, fixed pipeline)

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

With retrieval fixed, most cells are stable across repeats. The residual,
model-attributable variance is narrow: Haiku's stable 1,448-row explosion on LiJ_2017,
small-count instability on NayakRR/ContevilleLC, and Sonnet's over-enumeration of FanY
(319 vs 510).

## Findings

**1. Retrieval robustness dominated the "variance".** Three studies whose Haiku counts
swung 0↔112 pre-fix (TettAJ 6/50/0, PasolliE 112/112/1, FanY 319/319/0) are now stable
(50/50/50, 112/112/112, 319/319/319). The instability was a document-fetch lottery, not
the model. Reproducible LLM-curation benchmarks require a fault-tolerant fetch layer.

**2. Value-accuracy is the decisive model difference.** On cells both report, Sonnet 5
matches gold ~68% vs Haiku ~54%. Haiku's coverage comes bundled with more wrong values.

**3. Precision / fabrication: Sonnet is dramatically cleaner** (~2 FP vs ~588). Haiku's
588 FPs are concentrated in the single LiJ_2017 explosion — a stable defect, not noise.

**4. Reliability.** Across 60 extractions, 6 first-attempt failures (5 Haiku, 1 Sonnet),
all recovered on one retry: five malformed/truncated JSON, one `section: null` schema
crash. Both are LLM-output faults (not retrieval) and are more frequent on Haiku.

**5. Enumeration sets recall.** Six of ten studies enumerate 0 samples in both models
across all repeats — no machine-readable per-subject manifest is reachable. This is a
data-availability ceiling, not a model limit, and caps recall for both.

## Net read

On the same fixed code, **Sonnet 5 buys precision and correctness (P 0.999, value-acc
0.68, ~2 FPs) and stability; Haiku buys coverage cheaply but with ~588 FPs from a
reproducible explosion and a higher malformed-output rate.** For curation-assist where a
wrong cell costs more than a blank one, Sonnet 5 is the better default. Two code fixes
would help both models: retry on JSON-parse failure, and coerce a null `section`. And
per-sample recall should move onto the deterministic `tables=` + accession-aligned path,
which also prevents pathological count-explosions.

## Reproduce

```bash
cd benchmarks/cmd_sonnet5
python make_clean_schema.py cmd.clean.linkml.yaml
export ANTHROPIC_API_KEY=sk-ant-...                  # or a key file

# Multi-seed: 10 studies × 2 models × 3 repeats, bounded per-call wall-clock
python multiseed.py run   --workers 6      # writes out_ms/<model>_r<k>/
python multiseed.py eval                   # evals every run dir
python aggregate.py                        # -> out_ms/AGGREGATE.md (+ aggregate.json)
```

Outputs per run: `<study>.json` (raw extraction), `<study>.csv`, `<study>.cells.tsv`
(per-cell audit), `<study>.runlog.txt` (status/tokens/cost), `summary.json`, and
`REPORT.md`. `manifest.json` is the first 10 of the seed=42 selection.

---

# Harmonization pass — MetaHarmonizer SchemaMapper + OntologyMapper

A representative run of the extractions above was pushed through MetaHarmonizer
(`shbrief/MetaHarmonizer`) to test whether harmonization closes the
**raw-vs-harmonized surface-form gap** — the reason so many otherwise-correct cells
scored `TP_wrong` in the eval above. The harmonization question concerns the *mapping*,
not the extraction run, so these results are independent of the extraction variance
measured above. Scripts and outputs are under [`harmonize/`](harmonize/).

## SchemaMapper — `uncurated_metadata` free-text → cMD fields

The extractor dumps unstructured notes into `uncurated_metadata` (160 unique
strings, e.g. *"Increasing abundance of Proteobacteria observed in 25/35
students"*). We fed those strings as candidate columns to `SchemaMapEngine`
(`target_schema_path=cmd_target_attrs.csv`, `alias_dict_path=cmd_target_attrs_alias_haiku.csv`).

- **0 strong matches (`match1_score ≥ 0.80`); 17 moderate (`≥ 0.60`).** All
  moderate hits came from the **semantic Stage-3 fallback**, none from the
  dict/fuzzy stages — expected, since these are prose sentences, not column
  headers.
- The moderate hits route plausibly to **10 distinct cMD fields**:
  `sequencing_platform` (*"Sequencing method: Shotgun metagenomic…"*),
  `age_group` (*"Age categories: newborns, children…"*), `location`
  (*"Geographic locations: Indian peninsula…"*), `dietary_restriction`
  (*"Energy restriction diet: 30% calorie restricted…"*), plus `fmt_role`,
  `treatment`, `disease`, `antibiotics_exclusion_period`, `feces_phenotype_value`,
  `zigosity`.

**Read:** a little recoverable structured signal is buried in the free-text bucket
and SchemaMapper can *suggest* where it belongs, but nothing at
promote-without-review confidence. SchemaMapper is built to map column headers,
not narrative sentences. Output: [`harmonize/sm_uncurated_mapping.csv`](harmonize/sm_uncurated_mapping.csv).

## OntologyMapper — disease / body_site / treatment value harmonization

`OntoMapEngine` (MetaHarmonizer **v0.4.1**; NCIt via EVSREST; Stage 1 exact +
Stage 2 sap-bert embedding + Stage 2.5 synonym; **Stage 3 RAG and Stage 4 LLM
review disabled**). Corpus construction per category:

- **disease** — built the v0.4.1 way with `CombinedCorpusBuilder` over the cMD
  `disease` spec: dynamic root `NCIT:C7057` ("Disease, Disorder or Finding")
  **merged with the static term `NCIT:C115935` ("Healthy")** → 50,755-term
  combined corpus. The static term matters: `Healthy` is cMD's most common
  disease value (the controls) and is **not** under any disease subtree, so a
  plain root build misses it.
- **body_site** — built against **UBERON** (the ontology gold uses), not NCIt.
  cMD `body_site` is a static 6-value enum with explicit UBERON meanings
  (`feces`→`UBERON:0001988`, `oral cavity`→`UBERON:0000167`, …), so the corpus is
  exactly those 6 terms via `CombinedCorpusBuilder` static terms (OLS4).
- **treatment** → `NCIT:C1909` (26.8k), registry default.

**Two metrics, deliberately separated** (`harmonize/rescore_value_accuracy.csv`):

- `agree_acc` — extraction and gold map to the **same** OM code. Measures whether
  harmonization *reconciles surface forms*; does **not** prove the code is right.
- `correct_acc` — OM(extraction) equals gold's **own** curated
  `*_ontology_term_id`. This is true correctness, over the `n_gold_id` cells that
  actually carry a curated code.

Representative fixed-pipeline run (`out_ms/*_r1`):

| model | field | TP cells | raw value-acc | `agree_acc` | `correct_acc` | n w/ gold id |
|---|---|--:|--:|--:|--:|--:|
| Sonnet 5 | disease | 309 | 0.505 | 0.751 | **1.000** | 162 |
| Haiku 4.5 | disease | 506 | 0.310 | 0.709 | **1.000** | 352 |
| Sonnet 5 | body_site | 309 | 0.638 | 1.000 | **1.000** | 162 |
| Haiku 4.5 | body_site | 462 | 0.758 | 1.000 | **1.000** | 308 |
| Sonnet 5 | treatment | 147 | 0.000 | 0.184 | — | 0 |
| Haiku 4.5 | treatment | 153 | 0.000 | 0.203 | — | 0 |

(Unchanged from the pre-multi-seed run except Haiku's TP counts, which shift ~1%
with enumeration: disease 512→506, body_site 468→462, treatment 160→153;
`correct_acc` stays 1.00.)

**Disease — genuinely correct after the v0.4.1 rebuild.** With `Healthy` in the
corpus, OntologyMapper resolves every disease value that gold codes to the exact
NCIt code gold uses: `Healthy`→`C115935`, `Type 2 Diabetes Mellitus`→`C26747`,
`Hypertension`→`C3117`, `RA`↔`Rheumatoid Arthritis`→`C2884`. `correct_acc` is
**1.00 on all 162/352 cells that carry a curated ID** — this is verified against
gold's own codes, not self-consistency. It directly closes the pilot's Finding #4
(raw-vs-harmonized `TP_wrong`) for disease, and lifts raw value-accuracy from
0.51/0.31 to fully correct on the coded cells.

> A high `agree_acc` can be a self-consistency artifact: a code-normalization bug
> that briefly collapsed empty codes to the string `nan` produced a `nan`↔`nan`
> agreement with no correctness. Scoring against gold's own IDs (`correct_acc`) plus
> that fix make the number real; `agree_acc` (0.71–0.75) now correctly sits *below*
> `correct_acc`.

**body_site — genuinely correct against UBERON.** Rebuilt against the gold's own
ontology: OM resolves `feces` and `Stool` both to `UBERON:0001988`, matching gold's
`body_site_ontology_term_id` on **all 162/308 coded cells** (`correct_acc` 1.00).
(The earlier NCiT run scored `correct_acc` 0 purely because NCiT ≠ UBERON codes —
an ontology mismatch, not a mapping failure; targeting the gold's ontology fixes
it.) Because cMD `body_site` is a bounded 6-value enum, this needs no large build —
just the 6 static UBERON terms.

**treatment — no curated IDs to score against, and real disagreements.** The
treatment TP cells (FanY, NayakRR) carry **no** gold `treatment_ontology_term_id`
(`n_gold_id=0`), so correctness can't be measured. Agreement stays low because the
disagreements are *substantive, not lexical*: extraction asserts a drug (e.g.
SSRI) where gold says `no`/`Not applicable` (subject not on treatment) —
harmonization correctly refuses to reconcile that. Haiku's small edge is the
`MTX`↔`Methotrexate` cells. (Two v0.4.1 quirks noted: the exact stage tags hits as
label `Not Found` — codes backfilled from the corpus for scoring — and negations
are stripped, so `No metformin`→*Metformin*.)

## Net read (harmonization)

For **disease**, the v0.4.1 combined corpus (root + static `Healthy`) makes
OntologyMapper **genuinely correct** — 100% agreement with gold's own NCIt codes
on every coded cell — turning the pilot's largest `TP_wrong` bucket into true
matches. The critical lesson: the win came from **corpus construction** (including
the non-disease `Healthy` finding code), not from the matching algorithm, and it is
only visible once you score against gold's curated IDs (`correct_acc`) rather than
self-consistency (`agree_acc`). **body_site** is likewise fully correct
(`correct_acc` 1.00) once mapped to the gold's ontology (UBERON) — a bounded
6-value enum needing no large build. For **treatment**, gold carries no ontology
IDs on the relevant cells and the residual disagreements are real, so harmonization
neither can nor should move it. So on both fields that have curated ontology IDs,
harmonization reaches **100% agreement with the gold codes** — with the right
per-field ontology and corpus. Full numbers:
[`harmonize/rescore_value_accuracy.csv`](harmonize/rescore_value_accuracy.csv);
disease corpus [`harmonize/disease_corpus_v041.csv`](harmonize/); crosswalks
[`harmonize/crosswalk_*.csv`](harmonize/).

## Reproduce (harmonization)

```bash
cd benchmarks/cmd_sonnet5/harmonize
export MODEL_CACHE_ROOT=~/OmicsMLRepo/MetaHarmonizer/model_cache

# treatment corpus (NCIT:C1909) + extracted/gold crosswalks (main cache)
METAHARMONIZER_DATA_DIR=~/OmicsMLRepo/MetaHarmonizer/data python run_om.py
METAHARMONIZER_DATA_DIR=~/OmicsMLRepo/MetaHarmonizer/data python map_terms.py treatment - gold_terms_treatment.json crosswalk_gold_treatment.csv

# disease the v0.4.1 way: CombinedCorpusBuilder (C7057 + static C115935), isolated cache
TMP=$PWD/_disease_v041_cache
METAHARMONIZER_DATA_DIR=$TMP KNOWLEDGE_DB_DIR=$TMP/kb python build_disease_v041.py

# body_site against UBERON: 6 static cMD enum terms (OLS4), isolated cache
TMP=$PWD/_bodysite_v041_cache
METAHARMONIZER_DATA_DIR=$TMP KNOWLEDGE_DB_DIR=$TMP/kb python build_bodysite_v041.py

python rescore.py                # raw vs agree_acc vs correct_acc
python run_sm.py                 # SchemaMapper over uncurated_metadata keys
```

