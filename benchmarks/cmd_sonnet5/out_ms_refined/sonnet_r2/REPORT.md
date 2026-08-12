# MetaExtractor × curatedMetagenomicData — pilot evaluation

Target schema: `curatedmetagenomicdata/cmd.linkml.yaml`. Gold: cMD `*_sample.tsv`. Samples joined **positionally**.

## Headline (content fields, micro-averaged)

- Precision **0.99**, Recall **0.63**, F1 **0.77**, value-accuracy-on-attempted **0.63**
- cells: TN=587 TPc=3229 TPw=1915 FN=3010 FP=33

- **Coverage-aware recall 0.31** — recall when un/under-enumerated gold rows are counted as FN rather than dropped. The positional recall above (0.63) scores only the overlap `min(n_extracted, n_gold)`, so samples a study never enumerated do not enter the denominator.

## Per study

| study | pmid | gold n | ext n | align | content P | R | F1 | val-acc |
|---|---|--:|--:|---|--:|--:|--:|--:|
| Bengtsson-PalmeJ_2015 | 26259788 | 70 | 70 | match | 1.00 | 0.65 | 0.79 | 0.67 |
| TettAJ_2019_b | 31607556 | 44 | 50 | MISMATCH (50 vs 44) | 1.00 | 0.81 | 0.89 | 0.48 |
| LiJ_2017 | 28143587 | 196 | 6 | MISMATCH (6 vs 196) | 1.00 | 0.82 | 0.90 | 0.57 |
| NayakRR_2021 | 33440172 | 34 | 434 | MISMATCH (434 vs 34) | 1.00 | 0.73 | 0.84 | 0.24 |
| PasolliE_2019 | 30661755 | 112 | 112 | match | 1.00 | 0.65 | 0.79 | 0.77 |
| Heitz-BuschartA_2016 | 27723761 | 53 | 221 | MISMATCH (221 vs 53) | 0.95 | 0.50 | 0.66 | 0.43 |
| FanY_2023 | 37069399 | 147 | 510 | MISMATCH (510 vs 147) | 1.00 | 0.64 | 0.78 | 0.71 |
| QinJ_2012 | 23023125 | 363 | 0 | MISMATCH (0 vs 363) |   –  |   –  |   –  |   –  |
| ContevilleLC_2019 | 31417531 | 15 | 15 | match | 1.00 | 0.33 | 0.50 | 0.33 |
| LiSS_2016 | 27126044 | 55 | 430 | MISMATCH (430 vs 55) | 1.00 | 0.54 | 0.70 | 0.60 |

## Per field (all studies, micro)

| field | kind | N | TN | TPc | TPw | FN | FP | P | R | F1 | val-acc |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| age | content | 475 | 15 | 1 | 111 | 347 | 1 | 0.99 | 0.24 | 0.39 | 0.01 |
| age_group | content | 536 | 0 | 212 | 4 | 320 | 0 | 1.00 | 0.40 | 0.57 | 0.98 |
| age_max | content | 340 | 0 | 115 | 116 | 109 | 0 | 1.00 | 0.68 | 0.81 | 0.50 |
| age_min | content | 340 | 0 | 139 | 92 | 109 | 0 | 1.00 | 0.68 | 0.81 | 0.60 |
| age_unit | content | 279 | 0 | 223 | 2 | 53 | 1 | 1.00 | 0.81 | 0.89 | 0.99 |
| age_years | content | 279 | 1 | 112 | 0 | 166 | 0 | 1.00 | 0.40 | 0.57 | 1.00 |
| ancestry | content | 112 | 0 | 0 | 0 | 112 | 0 |   –  | 0.00 |   –  |   –  |
| ancestry_details | content | 112 | 0 | 0 | 0 | 112 | 0 |   –  | 0.00 |   –  |   –  |
| antibiotics_current_use | content | 492 | 31 | 312 | 0 | 149 | 0 | 1.00 | 0.68 | 0.81 | 1.00 |
| biomarker_name | content | 226 | 173 | 0 | 50 | 0 | 3 | 0.94 | 1.00 | 0.97 | 0.00 |
| biomarker_unit | content | 226 | 173 | 0 | 50 | 0 | 3 | 0.94 | 1.00 | 0.97 | 0.00 |
| biomarker_value | content | 226 | 173 | 0 | 50 | 0 | 3 | 0.94 | 1.00 | 0.97 | 0.00 |
| bmi | content | 312 | 6 | 112 | 0 | 194 | 0 | 1.00 | 0.37 | 0.54 | 1.00 |
| body_site | content | 536 | 0 | 390 | 146 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.73 |
| control | content | 340 | 0 | 44 | 3 | 293 | 0 | 1.00 | 0.14 | 0.24 | 0.94 |
| country | content | 536 | 0 | 331 | 205 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.62 |
| days_from_first_collection | content | 212 | 0 | 0 | 55 | 157 | 0 | 1.00 | 0.26 | 0.41 | 0.00 |
| disease | content | 536 | 0 | 236 | 285 | 15 | 0 | 1.00 | 0.97 | 0.99 | 0.45 |
| dna_extraction_kit | content | 334 | 0 | 59 | 190 | 85 | 0 | 1.00 | 0.75 | 0.85 | 0.24 |
| family | content | 156 | 0 | 0 | 44 | 112 | 0 | 1.00 | 0.28 | 0.44 | 0.00 |
| family_role | content | 44 | 0 | 6 | 38 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.14 |
| lifestyle | content | 15 | 0 | 0 | 0 | 15 | 0 |   –  | 0.00 |   –  |   –  |
| location | content | 21 | 0 | 0 | 6 | 15 | 0 | 1.00 | 0.29 | 0.44 | 0.00 |
| sequencing_platform | content | 536 | 0 | 309 | 227 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.58 |
| sex | content | 486 | 15 | 285 | 26 | 160 | 0 | 1.00 | 0.66 | 0.80 | 0.92 |
| smoker | content | 153 | 0 | 6 | 0 | 147 | 0 | 1.00 | 0.04 | 0.08 | 1.00 |
| target_condition | content | 340 | 0 | 111 | 3 | 226 | 0 | 1.00 | 0.34 | 0.50 | 0.97 |
| treatment | content | 234 | 0 | 0 | 212 | 0 | 22 | 0.91 | 1.00 | 0.95 | 0.00 |
| westernized | content | 340 | 0 | 226 | 0 | 114 | 0 | 1.00 | 0.66 | 0.80 | 1.00 |
| curator | id/prov | 536 | 0 | 0 | 0 | 536 | 0 |   –  | 0.00 |   –  |   –  |
| host_species | id/prov | 536 | 0 | 333 | 203 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.62 |
| ncbi_accession | id/prov | 536 | 0 | 1 | 338 | 197 | 0 | 1.00 | 0.63 | 0.77 | 0.00 |
| pmid | id/prov | 536 | 0 | 53 | 0 | 483 | 0 | 1.00 | 0.10 | 0.18 | 1.00 |
| sample_id | id/prov | 536 | 0 | 112 | 424 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.21 |
| study_name | id/prov | 536 | 0 | 0 | 156 | 380 | 0 | 1.00 | 0.29 | 0.45 | 0.00 |
| subject_id | id/prov | 536 | 0 | 1 | 217 | 318 | 0 | 1.00 | 0.41 | 0.58 | 0.00 |
| uncurated_metadata | id/prov | 70 | 0 | 0 | 0 | 70 | 0 |   –  | 0.00 |   –  |   –  |

### Decision legend
TN=both not-reported · TPc=both reported & match · TPw=both reported but differ (often raw-vs-harmonized surface form) · FN=gold has it, extractor missed · FP=extractor claims it, gold blank.
