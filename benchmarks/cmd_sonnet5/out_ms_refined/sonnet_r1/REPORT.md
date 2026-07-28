# MetaExtractor × curatedMetagenomicData — pilot evaluation

Target schema: `curatedmetagenomicdata/cmd.linkml.yaml`. Gold: cMD `*_sample.tsv`. Samples joined **positionally**.

## Headline (content fields, micro-averaged)

- Precision **0.96**, Recall **0.57**, F1 **0.71**, value-accuracy-on-attempted **0.59**
- cells: TN=428 TPc=2752 TPw=1889 FN=3513 FP=192

- **Coverage-aware recall 0.28** — recall when un/under-enumerated gold rows are counted as FN rather than dropped. The positional recall above (0.57) scores only the overlap `min(n_extracted, n_gold)`, so samples a study never enumerated do not enter the denominator.

## Per study

| study | pmid | gold n | ext n | align | content P | R | F1 | val-acc |
|---|---|--:|--:|---|--:|--:|--:|--:|
| Bengtsson-PalmeJ_2015 | 26259788 | 70 | 70 | match | 1.00 | 0.59 | 0.74 | 0.64 |
| TettAJ_2019_b | 31607556 | 44 | 50 | MISMATCH (50 vs 44) | 1.00 | 0.69 | 0.81 | 0.56 |
| LiJ_2017 | 28143587 | 196 | 6 | MISMATCH (6 vs 196) | 1.00 | 0.79 | 0.88 | 0.68 |
| NayakRR_2021 | 33440172 | 34 | 434 | MISMATCH (434 vs 34) | 1.00 | 0.82 | 0.90 | 0.33 |
| PasolliE_2019 | 30661755 | 112 | 112 | match | 1.00 | 0.55 | 0.71 | 0.54 |
| Heitz-BuschartA_2016 | 27723761 | 53 | 221 | MISMATCH (221 vs 53) | 0.95 | 0.41 | 0.57 | 0.53 |
| FanY_2023 | 37069399 | 147 | 319 | MISMATCH (319 vs 147) | 1.00 | 0.64 | 0.78 | 0.71 |
| QinJ_2012 | 23023125 | 363 | 0 | MISMATCH (0 vs 363) |   –  |   –  |   –  |   –  |
| ContevilleLC_2019 | 31417531 | 15 | 15 | match | 1.00 | 0.33 | 0.50 | 0.33 |
| LiSS_2016 | 27126044 | 55 | 430 | MISMATCH (430 vs 55) | 0.67 | 0.46 | 0.55 | 0.70 |

## Per field (all studies, micro)

| field | kind | N | TN | TPc | TPw | FN | FP | P | R | F1 | val-acc |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| age | content | 475 | 15 | 1 | 41 | 417 | 1 | 0.98 | 0.09 | 0.17 | 0.02 |
| age_group | content | 536 | 0 | 218 | 4 | 314 | 0 | 1.00 | 0.41 | 0.59 | 0.98 |
| age_max | content | 340 | 0 | 2 | 68 | 270 | 0 | 1.00 | 0.21 | 0.34 | 0.03 |
| age_min | content | 340 | 0 | 26 | 44 | 270 | 0 | 1.00 | 0.21 | 0.34 | 0.37 |
| age_unit | content | 279 | 0 | 111 | 2 | 165 | 1 | 0.99 | 0.41 | 0.58 | 0.98 |
| age_years | content | 279 | 1 | 112 | 0 | 166 | 0 | 1.00 | 0.40 | 0.57 | 1.00 |
| ancestry | content | 112 | 0 | 0 | 0 | 112 | 0 |   –  | 0.00 |   –  |   –  |
| ancestry_details | content | 112 | 0 | 0 | 112 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.00 |
| antibiotics_current_use | content | 492 | 31 | 312 | 0 | 149 | 0 | 1.00 | 0.68 | 0.81 | 1.00 |
| biomarker_name | content | 226 | 118 | 0 | 50 | 0 | 58 | 0.46 | 1.00 | 0.63 | 0.00 |
| biomarker_unit | content | 226 | 121 | 0 | 0 | 50 | 55 | 0.00 | 0.00 |   –  |   –  |
| biomarker_value | content | 226 | 121 | 0 | 0 | 50 | 55 | 0.00 | 0.00 |   –  |   –  |
| bmi | content | 312 | 6 | 112 | 0 | 194 | 0 | 1.00 | 0.37 | 0.54 | 1.00 |
| body_site | content | 536 | 0 | 424 | 112 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.79 |
| control | content | 340 | 0 | 50 | 70 | 220 | 0 | 1.00 | 0.35 | 0.52 | 0.42 |
| country | content | 536 | 0 | 331 | 205 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.62 |
| days_from_first_collection | content | 212 | 0 | 0 | 34 | 178 | 0 | 1.00 | 0.16 | 0.28 | 0.00 |
| disease | content | 536 | 0 | 166 | 285 | 85 | 0 | 1.00 | 0.84 | 0.91 | 0.37 |
| dna_extraction_kit | content | 334 | 0 | 59 | 190 | 85 | 0 | 1.00 | 0.75 | 0.85 | 0.24 |
| family | content | 156 | 0 | 0 | 44 | 112 | 0 | 1.00 | 0.28 | 0.44 | 0.00 |
| family_role | content | 44 | 0 | 6 | 38 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.14 |
| lifestyle | content | 15 | 0 | 0 | 0 | 15 | 0 |   –  | 0.00 |   –  |   –  |
| location | content | 21 | 0 | 0 | 6 | 15 | 0 | 1.00 | 0.29 | 0.44 | 0.00 |
| sequencing_platform | content | 536 | 0 | 197 | 339 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.37 |
| sex | content | 486 | 15 | 288 | 24 | 159 | 0 | 1.00 | 0.66 | 0.80 | 0.92 |
| smoker | content | 153 | 0 | 0 | 6 | 147 | 0 | 1.00 | 0.04 | 0.08 | 0.00 |
| target_condition | content | 340 | 0 | 111 | 3 | 226 | 0 | 1.00 | 0.34 | 0.50 | 0.97 |
| treatment | content | 234 | 0 | 0 | 212 | 0 | 22 | 0.91 | 1.00 | 0.95 | 0.00 |
| westernized | content | 340 | 0 | 226 | 0 | 114 | 0 | 1.00 | 0.66 | 0.80 | 1.00 |
| curator | id/prov | 536 | 0 | 0 | 0 | 536 | 0 |   –  | 0.00 |   –  |   –  |
| host_species | id/prov | 536 | 0 | 320 | 216 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.60 |
| ncbi_accession | id/prov | 536 | 0 | 1 | 338 | 197 | 0 | 1.00 | 0.63 | 0.77 | 0.00 |
| pmid | id/prov | 536 | 0 | 0 | 0 | 536 | 0 |   –  | 0.00 |   –  |   –  |
| sample_id | id/prov | 536 | 0 | 112 | 424 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.21 |
| study_name | id/prov | 536 | 0 | 0 | 232 | 304 | 0 | 1.00 | 0.43 | 0.60 | 0.00 |
| subject_id | id/prov | 536 | 0 | 0 | 237 | 299 | 0 | 1.00 | 0.44 | 0.61 | 0.00 |
| uncurated_metadata | id/prov | 70 | 0 | 0 | 70 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.00 |

### Decision legend
TN=both not-reported · TPc=both reported & match · TPw=both reported but differ (often raw-vs-harmonized surface form) · FN=gold has it, extractor missed · FP=extractor claims it, gold blank.
