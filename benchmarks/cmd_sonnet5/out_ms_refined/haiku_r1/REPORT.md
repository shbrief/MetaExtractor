# MetaExtractor × curatedMetagenomicData — pilot evaluation

Target schema: `curatedmetagenomicdata/cmd.linkml.yaml`. Gold: cMD `*_sample.tsv`. Samples joined **positionally**.

## Headline (content fields, micro-averaged)

- Precision **0.90**, Recall **0.64**, F1 **0.75**, value-accuracy-on-attempted **0.53**
- cells: TN=406 TPc=3645 TPw=3277 FN=3892 FP=784

- **Coverage-aware recall 0.41** — recall when un/under-enumerated gold rows are counted as FN rather than dropped. The positional recall above (0.64) scores only the overlap `min(n_extracted, n_gold)`, so samples a study never enumerated do not enter the denominator.

## Per study

| study | pmid | gold n | ext n | align | content P | R | F1 | val-acc |
|---|---|--:|--:|---|--:|--:|--:|--:|
| Bengtsson-PalmeJ_2015 | 26259788 | 70 | 70 | match | 1.00 | 0.65 | 0.79 | 0.49 |
| TettAJ_2019_b | 31607556 | 44 | 50 | MISMATCH (50 vs 44) | 1.00 | 0.31 | 0.48 | 0.23 |
| LiJ_2017 | 28143587 | 196 | 1448 | MISMATCH (1448 vs 196) | 0.73 | 0.57 | 0.64 | 0.62 |
| NayakRR_2021 | 33440172 | 34 | 434 | MISMATCH (434 vs 34) | 1.00 | 1.00 | 1.00 | 0.26 |
| PasolliE_2019 | 30661755 | 112 | 112 | match | 1.00 | 0.75 | 0.86 | 0.47 |
| Heitz-BuschartA_2016 | 27723761 | 53 | 221 | MISMATCH (221 vs 53) | 0.95 | 0.50 | 0.66 | 0.45 |
| FanY_2023 | 37069399 | 147 | 319 | MISMATCH (319 vs 147) | 1.00 | 0.82 | 0.90 | 0.74 |
| QinJ_2012 | 23023125 | 363 | 0 | MISMATCH (0 vs 363) |   –  |   –  |   –  |   –  |
| ContevilleLC_2019 | 31417531 | 15 | 15 | match | 1.00 | 0.78 | 0.88 | 0.57 |
| LiSS_2016 | 27126044 | 55 | 430 | MISMATCH (430 vs 55) | 0.67 | 0.46 | 0.55 | 0.20 |

## Per field (all studies, micro)

| field | kind | N | TN | TPc | TPw | FN | FP | P | R | F1 | val-acc |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| age | content | 475 | 16 | 4 | 30 | 425 | 0 | 1.00 | 0.07 | 0.14 | 0.12 |
| age_group | content | 726 | 0 | 220 | 143 | 363 | 0 | 1.00 | 0.50 | 0.67 | 0.61 |
| age_max | content | 530 | 0 | 3 | 223 | 304 | 0 | 1.00 | 0.43 | 0.60 | 0.01 |
| age_min | content | 530 | 0 | 26 | 200 | 304 | 0 | 1.00 | 0.43 | 0.60 | 0.12 |
| age_unit | content | 279 | 1 | 112 | 0 | 166 | 0 | 1.00 | 0.40 | 0.57 | 1.00 |
| age_years | content | 279 | 1 | 112 | 0 | 166 | 0 | 1.00 | 0.40 | 0.57 | 1.00 |
| ancestry | content | 112 | 0 | 0 | 0 | 112 | 0 |   –  | 0.00 |   –  |   –  |
| ancestry_details | content | 112 | 0 | 0 | 112 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.00 |
| antibiotics_current_use | content | 682 | 31 | 502 | 0 | 149 | 0 | 1.00 | 0.77 | 0.87 | 1.00 |
| biomarker_name | content | 416 | 112 | 0 | 50 | 0 | 254 | 0.16 | 1.00 | 0.28 | 0.00 |
| biomarker_unit | content | 416 | 112 | 0 | 50 | 0 | 254 | 0.16 | 1.00 | 0.28 | 0.00 |
| biomarker_value | content | 416 | 112 | 0 | 50 | 0 | 254 | 0.16 | 1.00 | 0.28 | 0.00 |
| bmi | content | 312 | 6 | 112 | 0 | 194 | 0 | 1.00 | 0.37 | 0.54 | 1.00 |
| body_site | content | 726 | 0 | 481 | 201 | 44 | 0 | 1.00 | 0.94 | 0.97 | 0.71 |
| control | content | 530 | 0 | 0 | 70 | 460 | 0 | 1.00 | 0.13 | 0.23 | 0.00 |
| country | content | 726 | 0 | 466 | 260 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.64 |
| days_from_first_collection | content | 212 | 0 | 17 | 87 | 108 | 0 | 1.00 | 0.49 | 0.66 | 0.16 |
| disease | content | 726 | 0 | 181 | 422 | 123 | 0 | 1.00 | 0.83 | 0.91 | 0.30 |
| dna_extraction_kit | content | 524 | 0 | 211 | 199 | 114 | 0 | 1.00 | 0.78 | 0.88 | 0.51 |
| family | content | 156 | 0 | 0 | 0 | 156 | 0 |   –  | 0.00 |   –  |   –  |
| family_role | content | 44 | 0 | 6 | 38 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.14 |
| lifestyle | content | 15 | 0 | 15 | 0 | 0 | 0 | 1.00 | 1.00 | 1.00 | 1.00 |
| location | content | 211 | 0 | 0 | 15 | 196 | 0 | 1.00 | 0.07 | 0.13 | 0.00 |
| sequencing_platform | content | 726 | 0 | 455 | 227 | 44 | 0 | 1.00 | 0.94 | 0.97 | 0.67 |
| sex | content | 486 | 15 | 305 | 41 | 125 | 0 | 1.00 | 0.73 | 0.85 | 0.88 |
| smoker | content | 343 | 0 | 129 | 214 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.38 |
| target_condition | content | 530 | 0 | 53 | 433 | 44 | 0 | 1.00 | 0.92 | 0.96 | 0.11 |
| treatment | content | 234 | 0 | 0 | 212 | 0 | 22 | 0.91 | 1.00 | 0.95 | 0.00 |
| westernized | content | 530 | 0 | 235 | 0 | 295 | 0 | 1.00 | 0.44 | 0.61 | 1.00 |
| curator | id/prov | 726 | 0 | 0 | 0 | 726 | 0 |   –  | 0.00 |   –  |   –  |
| host_species | id/prov | 726 | 0 | 349 | 377 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.48 |
| ncbi_accession | id/prov | 726 | 0 | 2 | 337 | 387 | 0 | 1.00 | 0.47 | 0.64 | 0.01 |
| pmid | id/prov | 726 | 0 | 726 | 0 | 0 | 0 | 1.00 | 1.00 | 1.00 | 1.00 |
| sample_id | id/prov | 726 | 0 | 112 | 614 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.15 |
| study_name | id/prov | 726 | 0 | 0 | 439 | 287 | 0 | 1.00 | 0.60 | 0.75 | 0.00 |
| subject_id | id/prov | 726 | 0 | 1 | 128 | 597 | 0 | 1.00 | 0.18 | 0.30 | 0.01 |
| uncurated_metadata | id/prov | 70 | 0 | 0 | 70 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.00 |

### Decision legend
TN=both not-reported · TPc=both reported & match · TPw=both reported but differ (often raw-vs-harmonized surface form) · FN=gold has it, extractor missed · FP=extractor claims it, gold blank.
