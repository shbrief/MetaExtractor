# Decision-model probe — results and verdicts

`src/metaextractor/decision.py` is a seam for cheap bounded judgments. It is wired
to **nothing**. This document is the gate it has to pass through: a judgment is
not handed to a model before anyone knows how often the current heuristic is
right, and what a better one would have to beat.

Modelled on bugsigdb-curation-tools' `benchmarks/decision-probe/`, which issued a
GO for four judgments and a NO-GO for four others and wired only the GOs.

Everything below is measured offline from committed run artifacts by
[`probe.py`](probe.py); the raw tables it produced are in
[`MEASUREMENTS.md`](MEASUREMENTS.md). No API calls, no re-extraction.

**Small-n warning that applies to everything here.** Ten studies, two models,
three repeats. These are counts of tens, not hundreds. Every verdict below is a
direction, and none of them is a benchmark.

---

## Summary

| # | Judgment | Who decides today | Measured | Verdict |
|---|---|---|---|---|
| A | Does this table need a structure plan? | 6 hand-written rules | precision 0.57 (`out_v4`), 0.71 (`out_v3`); recall unmeasurable | **GO, narrowly** — two of six rules carry nearly all the waste |
| B | Which BioProject is the study's own? | 3 ordered rules over a term count | 2 of 6 confident resolutions were contested ties | **NO-GO for now** — needs a label, not a judge |
| C | Is this table relevant enough to read? | weighted sum vs a 0.15 gate | not measured | **NOT YET MEASURED** |
| D | Does this string describe a cohort or a sample? | one regex | not measured | **NOT YET MEASURED** |
| E | Is this a figure's source data? | one regex on the filename | not measurable as posed | **NO-GO** — fix the signal, don't add a judge |
| F | Which schema field does this column mean? | 4-tier cascade, fuzzy ≥ 90 | not measured | **NOT YET MEASURED** |

---

## A. The structure-plan decision — **GO, narrowly**

`table_plan.needs_structure_plan` decides whether a supplementary table can be
read as "row 0 is the header" or needs an LLM call to propose a structure. It is
the pipeline's cost router, and it is the one judgment with a label already
sitting in the committed runs: when a plan *was* requested, the plan the model
returned is recorded, and a plan of `header_rows=[0]` with no melt is
structurally the default parse — so that call bought nothing.

| tree | labelled | call warranted | call bought nothing | repeats disagreed | precision |
|---|--:|--:|--:|--:|--:|
| `out_v4` | 46 | 26 | 11 | 9 | **0.565** |
| `out_v3` | 101 | 34 | 5 | 9 | **0.708** |

**The interesting result is not the headline, it is the per-rule split.** On
`out_v4`:

| detector rule | warranted | bought nothing | disagreed |
|---|--:|--:|--:|
| row 0 has fewer than two labels | 16 | 0 | 1 |
| blank cells inside the header span | 9 | 7 | 7 |
| repeated column groups | 1 | 3 | 0 |
| row 1 looks like a second header row | 0 | 1 | 1 |

One rule — "row 0 has fewer than two labels" — is essentially never wrong
(16/16 warranted, 18/18 on `out_v3`). Two rules account for nearly all the waste:
"blank cells inside the header span" and "repeated column groups". That is a far
more useful finding than a single precision number, because it says a judge is
not needed for the whole decision, only for the two rules that are guessing.

**Verdict: GO, narrowly.** Wire a judgment only on the two imprecise rules, as a
veto: when "blank cells in the header span" or "repeated column groups" fires,
ask whether the table really needs re-reading, and fall back to firing the rule
when the judge abstains or is unsure. Leave the precise rule alone — asking about
it would add cost and risk for nothing.

**Two caveats that must travel with this.**

1. **Recall is unmeasurable from these runs.** A table the detector read as is was
   never shown to a model, so nothing says whether a plan was needed. Precision
   alone can be improved by simply firing less often, which would silently lose
   recall. So the lever's effect must be judged on end-to-end scores, never on
   this number. Measuring recall needs a paid run that plans every table.
2. **9 of 46 tables got different plans in different repeats** — the same table,
   the same prompt, a different answer. So part of what looks like detector error
   is model variance, and the label itself is noisy. A judge is being asked to
   predict something that is not fully determined.

## B. Project resolution — **NO-GO for now**

`sra_manifest.resolve_projects` picks the study's own BioProject by three ordered
rules over `context_score`, a count of hand-written data-availability phrases in a
250-character window. A wrong manifest is the failure mode the module exists to
prevent: `sra_manifest.py:9` records that some curated `_sra_meta.tsv` files hold
another study's runs.

Instrumenting it (this branch) made the previously invisible visible:

| | |
|---|--:|
| studies probed | 10 |
| resolved by a confident rule | 6 |
| of those, the choice was a **contested tie** | **2** |
| abstained with nothing resolvable | 4 |

The two contested cases are `PasolliE_2019` (two BioProjects tied at score 6) and
`TettAJ_2019_b` (four tied at 5, so all four are fetched). Before the audit trail
these looked exactly as confident as the four uncontested ones.

**Verdict: NO-GO, and the reason matters.** There is no label here. We now know
*how often* the tie-break was contested; we do not know whether it chose *right*,
because nothing records which project the curators considered correct. Asking a
model to arbitrate an unlabelled decision would replace one unmeasured judgment
with another.

What to do instead, in order: (1) compare the resolved projects against the
accessions in the curated `*_sra_meta.tsv` to build the missing label; (2) only
then decide whether a judge beats the term count. Step 1 is eval-side work and
needs no model at all.

## C. Table relevance — **NOT YET MEASURED**

The gate most worth measuring, and the one with manuscript-stated motivation:
§4.5(iv) records that spurious enumeration accounted for **three of the ten
studies**. The score is a weighted sum (`0.20·shape + 0.20·id + 0.25·name +
0.35·enum`) against a `0.15` gate, all five constants hand-tuned.

A label is constructible from committed artifacts — join `TableSelection` against
the per-cell outcomes in `cells.tsv` by way of `sample_provenance`, and ask
whether a selected table's columns produced correct cells or false positives —
but it is a real piece of analysis rather than a few lines, and it belongs with
the `evaluation/extensions/` work rather than bolted onto this probe. Deferred
deliberately, not forgotten.

## D. Cohort-or-sample (`is_heterogeneous`) — **NOT YET MEASURED**

`sample_rules.is_heterogeneous` is one regex anchored on
`^(mixed|multiple|various|several|varies|varied|both)\b`, deciding whether a
study-level string describes a cohort (and so must not be propagated to every
sample) or one sample. Its own docstring concedes the evidence text cannot settle
it, which is an unusually honest signpost that a bounded judgment belongs here;
§4.5(v) is the matching defect.

The label is available in principle — every block increments a named counter and
every write records provenance, and `aggregate.py` already slices cell decisions
by provenance — so per-rule precision is computable. Not done here.

## E. Figure source data — **NO-GO**

`is_figure_source_data` is a single regex on the table *filename*
(`source[\s_-]*data`) with no content signal at all. It is the weakest decision in
the codebase, but a judge is the wrong fix and the probe cannot even score it: a
true positive is unobservable, because a table rejected this way is never read, so
there is no record of what it contained.

**Verdict: NO-GO.** The problem is a missing signal, not a missing judge. Score the
table's *content* the way `is_measurement_matrix` does, and let the filename be
one weak input among several. That is deterministic work.

## F. Column mapping, fuzzy tier — **NOT YET MEASURED**

`column_mapper` tier 4 accepts a mapping at `fuzz.ratio >= 90` computed against
**field names only** — no description, no values — and 90 is a bare constant that
is not exposed on the CLI. `ColumnMapping.tier_used` records the deciding tier
*and* the score per header, and `cells.tsv` says whether the resulting cell was
right, so precision per tier is directly computable. Not done here.

Worth noting that this is the judgment with the most obvious non-model fix
available first: tier 4 compares names while the schema also carries a
`description` and `allowed_values` that it ignores.

---

## What this probe does not say

- **Nothing about end-to-end effect.** Every verdict above is about one
  judgment in isolation. Whether wiring A changes a score is a question for a
  lever-on/lever-off pair from identical code, which costs a paid run.
- **Nothing about a calibrated classifier.** `HaikuDecisionModel` returns a
  self-reported confidence, which is not a calibrated probability. For the
  yes/no veto that verdict A recommends, that is adequate — the answer carries
  the decision and the confidence only gates abstention. For a *ranking* over
  twenty tables it would not be, and verdict C should keep that in mind when it
  is eventually measured.
- **Nothing with an interval.** Ten studies. Counts of tens.

## Next steps, in order

1. Build the missing label for B (resolved projects vs the curated SRA metadata).
   Eval-side, no model.
2. Measure C and F from `cells.tsv`, which is where the manuscript-stated defects
   are. Eval-side, no model.
3. Fix E deterministically — content signal, not filename.
4. Wire A's narrow veto behind a flag defaulting off, and report it as a
   lever-on/lever-off pair.
