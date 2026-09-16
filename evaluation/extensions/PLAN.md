# Phase 0: inspection for source adjudication (A) and repeat stability (B)

Status: **inspection only.** No script, no output, and no change to Section 2.4. Five points
below conflict with the task as written and need a decision before Phase 1 (see "Open
decisions"). The parameter table is unfilled; proposed values are at the end.

## 1. The scorer

| | |
|---|---|
| Module | `benchmarks/cmd_sonnet5/bench.py` |
| Entry point | `bench.py eval <run_dir>`, i.e. `cmd_eval` → `score_study` per study |
| Per-study scoring | `score_study(manifest_entry, run_json, Harmonizer) -> dict` |
| Per-cell records | `rec["_e2e"].per_cell`, each with `sample_idx`, `ext_sample_id`, `gold_sample_id`, `field`, `extracted`, `gold`, `decision` |
| Decisions | `TN`, `FN`, `FP`, `TP_correct`, `TP_wrong` (the task's TPc/TPw) |
| Already written to disk | `write_cells_tsv` emits `<run>/<study>.cells.tsv` — all-curated join, one row per cell, with `extracted_harmonized` / `gold_harmonized` |
| Alignment | `metaextractor.alignment.align_by_identity`, keys `ncbi_accession,sample_id,subject_id` |
| Comparison | `evaluate(...)` with `canonicalize=harm.canonicalize`; harmonized fields compare code sets, others compare surface strings |

**A per-cell table already exists.** `out_v3` holds 60 `*.cells.tsv` files (2 models x 3
repeats x 10 studies), 155,208 cell rows. Phase 1 is therefore an *enrichment* of an existing
scorer output, not a reimplementation: `cells.tsv` = the existing per-cell rows plus `model`,
`repeat`, `study_name`, `pmid`, `match_status`, term IDs and `harmonized_field`.

`match_status` is not in `cells.tsv` but is recoverable without touching the scorer:
`score_study` returns `rec["_alignment"]` carrying `unmatched_gold`, `pooled_gold` and
`ambiguous_gold` as gold-row index lists, and `extraction_failed` is on the record. Term IDs
come from `Harmonizer.codes(value, field)`.

## 2. Fan-out of study-level values

`metaextractor.sample_rules.fan_out_fields_to_samples` copies a study-level (or subgroup)
value onto sample rows that have no value of their own, governed by each slot's schema
annotations: `scope` (`study` / `sample` / unset), `propagate_study_value` (the allowlist:
`antibiotics_current_use`, `body_site`, `disease`) and `unit_of` (`age_unit` reaches only
records that carry an `age`). Values already present from a table or manifest are never
overwritten.

**In cell records it appears only through provenance, not in `cells.tsv`.** Each written cell
gets `result.sample_provenance[i][field]`, one of `study_fanout`, `subgroup_fanout:<name>`,
`table:<table>:<column>`, `manifest:<table>:<column>`. `score_study` reads it via
`_source_kind` into `by_source_end_to_end`, but `write_cells_tsv` does not emit it. Phase 1
will carry it as an extra column, since a TPw or FP cell that came from `study_fanout` is a
different kind of error from one read off a table, and the adjudicator's verdict means
something different in each case.

## 3. Repeat outputs

| | |
|---|---|
| Location | `benchmarks/cmd_sonnet5/out_v3/{sonnet,haiku}_r{1,2,3}/` |
| Per study | `<study>.json` (records), `.csv`, `.cells.tsv`, `.meta.json`, `.text.txt`, `.attemptN.log` |
| Models | `claude-sonnet-5`, `claude-haiku-4-5` |

**The three repeats read identical frozen inputs.** This is established by code and by logs,
not inferred:

- `run_frozen.py` fetches each study **once** into `out_v3/_fetch/<study>/` and every
  extraction runs `metaextractor.cli --fetch-cache <that dir> --require-fetch-cache`, which
  fails rather than reaching the network;
- `out_v3/_fetch/<study>/fetched.json` stores `text_sha256` and `tables_sha256`;
- `out_v3/ledger.jsonl` records one row per attempt with `frozen_retrieval`, the git commit,
  and checksums of the schema, manifest and age rules; `run_frozen.py verify` re-checks them.

So repeats differ only in the model's sampling, not in what the endpoints returned.

## 4. Source documents

Available locally, but **only as the frozen retrieval**: `out_v3/_fetch/<study>/text.txt`
(article body as retrieved) and `tables.json` (parsed supplementary tables), present for all
ten studies. `out_v3/<run>/<study>.text.txt` is the same text saved per run.

**No original PDFs or publisher supplements are stored.** This is the most consequential
finding for Part A and is item 3 under "Open decisions".

## 5. Consistency check — PASSED

Re-scored from the committed outputs and compared against the manuscript.

Manuscript Table 2 (Section 3.4), median [min–max] over three repeats, against recomputation:

| score | model | manuscript F1 | recomputed F1 |
|---|---|---|---|
| all curated | Sonnet 5 | 0.203 [0.180–0.216] | **0.203 [0.180–0.216]** |
| all curated | Haiku 4.5 | 0.193 [0.148–0.193] | **0.193 [0.148–0.193]** |
| matched | Sonnet 5 | 0.514 [0.452–0.538] | **0.514 [0.452–0.538]** |
| matched | Haiku 4.5 | 0.475 [0.468–0.484] | **0.475 [0.468–0.484]** |

Precision and recall also reproduce exactly (Sonnet all-curated P 0.739 [0.637–0.739],
R 0.118 [0.105–0.126]; Haiku P 0.683 [0.601–0.691], R 0.112 [0.083–0.115]).

Per-cell counts aggregated from the 60 `*.cells.tsv` files equal the `summary.json`
all-curated content counts for **all six model x repeat combinations**, e.g.

| run | TN | TPc | TPw | FN | FP |
|---|--:|--:|--:|--:|--:|
| sonnet_r1 | 1320 | 1762 | 1006 | 14087 | 0 |
| haiku_r3 | 1298 | 1932 | 1259 | 13664 | 22 |

The Phase 1 test ("aggregating `cells.tsv` reproduces the Section 2.4 counts") therefore
already passes on the material Phase 1 will be built from.

**Deviation:** the task says to *re-run the existing scorer*. Running `bench.py eval out_v3`
would rewrite `summary.json`, `REPORT.md` and the 60 `cells.tsv` files inside `out_v3`, which
the project's standing rule forbids ("do not edit, overwrite, or delete `out_v3/`"). The check
above instead re-scored **in memory** and read the committed outputs. Phase 1 will do the same
and write only under `evaluation/extensions/`.

## Open decisions

### 1. Which runs? `out_v3` reproduces Section 2.4; it is not the latest code

Section 2.4 and Table 2 are defined on `out_v3`, and the consistency gate passes there. The
newer full development run (`dev_analysis/devfull`, commit `5ace970`) has different scores and
is **not** what Section 2.4 reports. Recommendation: **`out_v3`**, so the adjudication attaches
to the numbers in the manuscript; the scripts will take the tree as an argument so the same
analysis can be re-run on `out_v4` later.

### 2. "Include all TPw units" is not feasible

After deduplicating on (study, gold row, field, gold value, extracted value) across both models
and all three repeats:

| outcome | distinct units |
|---|--:|
| TPw | **3,946** |
| FP | **22** |
| FN | **22,199** |
| total | 26,167 |

At 45–60 s per unit, all TPw alone is **50–65 hours** of adjudicator time. Recommendation:
stratify TPw by study x field like FP and FN (48 strata; 3 per stratum = 142 units), and keep
the "include all" rule only for FP, where 22 units is the entire population.

### 3. Adjudicating against the frozen text measures something narrower than intended

The adjudicator can only read what retrieval captured. For an FN where the value exists in a
publisher supplement we never fetched, the honest answer from the frozen text is "cannot
determine" — so FN verdicts would be confounded with retrieval coverage rather than testing
whether gold is right. Three options:

- **(a)** adjudicate from the published article via PMID/DOI, with the frozen text as an aid —
  measures gold correctness, and is what the task intends;
- **(b)** adjudicate from the frozen text only — cheaper and fully reproducible, but the
  question becomes "is the value in what MetaExtractor was given", and the report must say so;
- **(c)** (a) for FP and TPw, (b) for FN.

Recommendation: **(a)**, with the packet carrying the PMC/DOI link per study.

### 4. Two studies would consume the FN budget while yielding nothing

`QinJ_2012` (8,582 FN units) and `LiSS_2016` (1,100) retrieved **abstract only** — no body, no
tables — so extraction produced no records at all and every populated gold cell is an FN. Under
option (b) every one is "cannot determine"; under (a) they are a test of the curators, not of
the extractor. Recommendation: **exclude both from FN sampling** and report them separately as
a known retrieval ceiling, or cap them at one stratum's quota.

### 5. FP is too small to carry the metric the task asks for

22 distinct FP units, 22 FP cells in one run (haiku_r3) and 0 in the other five. "The fraction
of FP cells where the extraction was supported" will be a proportion out of 22 with a very wide
interval, and the paired bootstrap for it will be degenerate for five of six runs. I will
compute and report it with its interval, flagged as underpowered.

### 6. Placement

The task specifies `evaluation/extensions/`; the repo keeps benchmark code in
`benchmarks/cmd_sonnet5/`. This plan sits at the repo root path as written. Say if it should
move under the benchmark directory instead.

## Proposed parameters

| Parameter | Proposed | Why |
|---|---|---|
| `RUNS_DIR` | `benchmarks/cmd_sonnet5/out_v3` | the only tree that reproduces Section 2.4 |
| `GOLD` | `$CMD_CURATION_DIR/<gold_rel>` per `manifest.json`, checkout `4127171` | resolved by `bench_paths.gold_path`, not a new path |
| `SOURCES` | `out_v3/_fetch/<study>/{text.txt,tables.json}` + PMID/DOI link | pending decision 3 |
| `MODELS` | `sonnet` (claude-sonnet-5), `haiku` (claude-haiku-4-5) | both trees |
| `N_FP` | `all` (22 units) | entire population |
| `N_FN` | 3 per study x field stratum, excluding QinJ_2012 and LiSS_2016 | ≈ 500 units |
| TPw | 3 per stratum (not "all") | ≈ 142 units — see decision 2 |
| `N_TPC_CONTROL` | 50 | enough to detect a gross blinding failure, cheap |
| `N_DOUBLE` | 60 | κ on ~60 units gives a usable interval |
| `SHOW_HARMONIZED_LABEL` | yes | without it, code-set disagreements are invisible to the adjudicator |
| `SEED` | 0 | as specified |
| `BOOTSTRAP_B` | 2000 | matches Section 2.4 |

**Estimated adjudicator load:** ≈ 715 units (142 TPw + 22 FP + ~500 FN + 50 TPc control),
plus 60 double-adjudicated. At 45–60 s per unit that is **9–12 hours** for the primary
adjudicator and about 1 hour for the second.

Part B needs no adjudicator input and no decision above except the tree; it can start as soon
as Phase 1 is approved.
