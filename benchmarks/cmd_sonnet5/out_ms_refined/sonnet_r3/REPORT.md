# MetaExtractor × curatedMetagenomicData — pilot evaluation

Target schema: `curatedmetagenomicdata/cmd.linkml.yaml`. Gold: cMD `*_sample.tsv`. Samples joined **positionally**.

## Headline (content fields, micro-averaged)

- Precision **0.99**, Recall **0.63**, F1 **0.77**, value-accuracy-on-attempted **0.62**
- cells: TN=569 TPc=3171 TPw=1983 FN=3000 FP=51

- **Coverage-aware recall 0.31** — recall when un/under-enumerated gold rows are counted as FN rather than dropped. The positional recall above (0.63) scores only the overlap `min(n_extracted, n_gold)`, so samples a study never enumerated do not enter the denominator.

## Per study

| study | pmid | gold n | ext n | align | content P | R | F1 | val-acc |
|---|---|--:|--:|---|--:|--:|--:|--:|
| Bengtsson-PalmeJ_2015 | 26259788 | 70 | 70 | match | 1.00 | 0.53 | 0.69 | 0.71 |
| TettAJ_2019_b | 31607556 | 44 | 50 | MISMATCH (50 vs 44) | 1.00 | 0.87 | 0.93 | 0.44 |
| LiJ_2017 | 28143587 | 196 | 6 | MISMATCH (6 vs 196) | 0.81 | 0.93 | 0.87 | 0.54 |
| NayakRR_2021 | 33440172 | 34 | 434 | MISMATCH (434 vs 34) | 1.00 | 0.73 | 0.84 | 0.37 |
| PasolliE_2019 | 30661755 | 112 | 112 | match | 1.00 | 0.65 | 0.79 | 0.69 |
| Heitz-BuschartA_2016 | 27723761 | 53 | 221 | MISMATCH (221 vs 53) | 0.96 | 0.60 | 0.74 | 0.45 |
| FanY_2023 | 37069399 | 147 | 510 | MISMATCH (510 vs 147) | 1.00 | 0.64 | 0.78 | 0.71 |
| QinJ_2012 | 23023125 | 363 | 0 | MISMATCH (0 vs 363) |   –  |   –  |   –  |   –  |
| ContevilleLC_2019 | 31417531 | 15 | 15 | match | 1.00 | 0.67 | 0.80 | 0.50 |
| LiSS_2016 | 27126044 | 55 | 430 | MISMATCH (430 vs 55) | 1.00 | 0.46 | 0.63 | 0.70 |

## Per field (all studies, micro)

| field | kind | N | TN | TPc | TPw | FN | FP | P | R | F1 | val-acc |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| age | content | 475 | 15 | 1 | 41 | 417 | 1 | 0.98 | 0.09 | 0.17 | 0.02 |
| age_group | content | 536 | 0 | 218 | 4 | 314 | 0 | 1.00 | 0.41 | 0.59 | 0.98 |
| age_max | content | 340 | 0 | 115 | 116 | 109 | 0 | 1.00 | 0.68 | 0.81 | 0.50 |
| age_min | content | 340 | 0 | 139 | 92 | 109 | 0 | 1.00 | 0.68 | 0.81 | 0.60 |
| age_unit | content | 279 | 0 | 111 | 2 | 165 | 1 | 0.99 | 0.41 | 0.58 | 0.98 |
| age_years | content | 279 | 1 | 112 | 0 | 166 | 0 | 1.00 | 0.40 | 0.57 | 1.00 |
| ancestry | content | 112 | 0 | 0 | 0 | 112 | 0 |   –  | 0.00 |   –  |   –  |
| ancestry_details | content | 112 | 0 | 0 | 0 | 112 | 0 |   –  | 0.00 |   –  |   –  |
| antibiotics_current_use | content | 492 | 31 | 312 | 0 | 149 | 0 | 1.00 | 0.68 | 0.81 | 1.00 |
| biomarker_name | content | 226 | 167 | 0 | 50 | 0 | 9 | 0.85 | 1.00 | 0.92 | 0.00 |
| biomarker_unit | content | 226 | 167 | 0 | 50 | 0 | 9 | 0.85 | 1.00 | 0.92 | 0.00 |
| biomarker_value | content | 226 | 167 | 0 | 50 | 0 | 9 | 0.85 | 1.00 | 0.92 | 0.00 |
| bmi | content | 312 | 6 | 112 | 0 | 194 | 0 | 1.00 | 0.37 | 0.54 | 1.00 |
| body_site | content | 536 | 0 | 424 | 112 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.79 |
| control | content | 340 | 0 | 47 | 115 | 178 | 0 | 1.00 | 0.48 | 0.65 | 0.29 |
| country | content | 536 | 0 | 331 | 205 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.62 |
| days_from_first_collection | content | 212 | 0 | 0 | 53 | 159 | 0 | 1.00 | 0.25 | 0.40 | 0.00 |
| disease | content | 536 | 0 | 236 | 285 | 15 | 0 | 1.00 | 0.97 | 0.99 | 0.45 |
| dna_extraction_kit | content | 334 | 0 | 74 | 190 | 70 | 0 | 1.00 | 0.79 | 0.88 | 0.28 |
| family | content | 156 | 0 | 0 | 44 | 112 | 0 | 1.00 | 0.28 | 0.44 | 0.00 |
| family_role | content | 44 | 0 | 6 | 38 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.14 |
| lifestyle | content | 15 | 0 | 15 | 0 | 0 | 0 | 1.00 | 1.00 | 1.00 | 1.00 |
| location | content | 21 | 0 | 0 | 21 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.00 |
| sequencing_platform | content | 536 | 0 | 309 | 227 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.58 |
| sex | content | 486 | 15 | 289 | 23 | 159 | 0 | 1.00 | 0.66 | 0.80 | 0.93 |
| smoker | content | 153 | 0 | 0 | 6 | 147 | 0 | 1.00 | 0.04 | 0.08 | 0.00 |
| target_condition | content | 340 | 0 | 111 | 47 | 182 | 0 | 1.00 | 0.46 | 0.63 | 0.70 |
| treatment | content | 234 | 0 | 0 | 212 | 0 | 22 | 0.91 | 1.00 | 0.95 | 0.00 |
| westernized | content | 340 | 0 | 209 | 0 | 131 | 0 | 1.00 | 0.61 | 0.76 | 1.00 |
| curator | id/prov | 536 | 0 | 0 | 0 | 536 | 0 |   –  | 0.00 |   –  |   –  |
| host_species | id/prov | 536 | 0 | 432 | 104 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.81 |
| ncbi_accession | id/prov | 536 | 0 | 2 | 337 | 197 | 0 | 1.00 | 0.63 | 0.77 | 0.01 |
| pmid | id/prov | 536 | 0 | 103 | 0 | 433 | 0 | 1.00 | 0.19 | 0.32 | 1.00 |
| sample_id | id/prov | 536 | 0 | 112 | 390 | 34 | 0 | 1.00 | 0.94 | 0.97 | 0.22 |
| study_name | id/prov | 536 | 0 | 0 | 209 | 327 | 0 | 1.00 | 0.39 | 0.56 | 0.00 |
| subject_id | id/prov | 536 | 0 | 2 | 127 | 407 | 0 | 1.00 | 0.24 | 0.39 | 0.02 |
| uncurated_metadata | id/prov | 70 | 0 | 0 | 70 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.00 |

### Decision legend
TN=both not-reported · TPc=both reported & match · TPw=both reported but differ (often raw-vs-harmonized surface form) · FN=gold has it, extractor missed · FP=extractor claims it, gold blank.
