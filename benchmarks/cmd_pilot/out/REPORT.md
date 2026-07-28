# MetaExtractor × curatedMetagenomicData — pilot evaluation

Target schema: `curatedmetagenomicdata/cmd.linkml.yaml`. Gold: cMD `*_sample.tsv`. Samples joined **positionally**.

## Headline (content fields, micro-averaged)

- Precision **0.85**, Recall **0.59**, F1 **0.70**, value-accuracy-on-attempted **0.53**
- cells: TN=339 TPc=1813 TPw=1594 FN=2344 FP=588

## Per study

| study | pmid | gold n | ext n | align | content P | R | F1 | val-acc |
|---|---|--:|--:|---|--:|--:|--:|--:|
| Bengtsson-PalmeJ_2015 | 26259788 | 70 | 0 | MISMATCH (0 vs 70) |   –  |   –  |   –  |   –  |
| TettAJ_2019_b | 31607556 | 44 | 1023 | MISMATCH (1023 vs 44) | 1.00 | 0.06 | 0.12 | 1.00 |
| LiJ_2017 | 28143587 | 196 | 196 | match | 0.77 | 0.71 | 0.74 | 0.70 |
| NayakRR_2021 | 33440172 | 34 | 6 | MISMATCH (6 vs 34) | 1.00 | 0.77 | 0.87 | 0.51 |
| PasolliE_2019 | 30661755 | 112 | 9316 | MISMATCH (9316 vs 112) | 1.00 | 0.60 | 0.75 | 0.27 |

## Per field (all studies, micro)

| field | kind | N | TN | TPc | TPw | FN | FP | P | R | F1 | val-acc |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| age | content | 162 | 1 | 0 | 8 | 153 | 0 | 1.00 | 0.05 | 0.09 | 0.00 |
| age_group | content | 358 | 0 | 40 | 78 | 240 | 0 | 1.00 | 0.33 | 0.50 | 0.34 |
| age_max | content | 352 | 0 | 1 | 111 | 240 | 0 | 1.00 | 0.32 | 0.48 | 0.01 |
| age_min | content | 352 | 0 | 0 | 112 | 240 | 0 | 1.00 | 0.32 | 0.48 | 0.00 |
| age_unit | content | 156 | 1 | 0 | 0 | 155 | 0 |   –  | 0.00 |   –  |   –  |
| age_years | content | 156 | 1 | 0 | 0 | 155 | 0 |   –  | 0.00 |   –  |   –  |
| ancestry | content | 112 | 0 | 0 | 0 | 112 | 0 |   –  | 0.00 |   –  |   –  |
| ancestry_details | content | 112 | 0 | 0 | 112 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.00 |
| antibiotics_current_use | content | 314 | 0 | 202 | 0 | 112 | 0 | 1.00 | 0.64 | 0.78 | 1.00 |
| biomarker_name | content | 308 | 112 | 0 | 0 | 0 | 196 | 0.00 |   –  |   –  |   –  |
| biomarker_unit | content | 308 | 112 | 0 | 0 | 0 | 196 | 0.00 |   –  |   –  |   –  |
| biomarker_value | content | 308 | 112 | 0 | 0 | 0 | 196 | 0.00 |   –  |   –  |   –  |
| bmi | content | 112 | 0 | 0 | 0 | 112 | 0 |   –  | 0.00 |   –  |   –  |
| body_site | content | 358 | 0 | 202 | 112 | 44 | 0 | 1.00 | 0.88 | 0.93 | 0.64 |
| control | content | 352 | 0 | 112 | 0 | 240 | 0 | 1.00 | 0.32 | 0.48 | 1.00 |
| country | content | 358 | 0 | 202 | 112 | 44 | 0 | 1.00 | 0.88 | 0.93 | 0.64 |
| days_from_first_collection | content | 6 | 0 | 0 | 0 | 6 | 0 |   –  | 0.00 |   –  |   –  |
| disease | content | 358 | 0 | 156 | 202 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.44 |
| dna_extraction_kit | content | 358 | 0 | 196 | 118 | 44 | 0 | 1.00 | 0.88 | 0.93 | 0.62 |
| family | content | 156 | 0 | 0 | 0 | 156 | 0 |   –  | 0.00 |   –  |   –  |
| family_role | content | 44 | 0 | 0 | 0 | 44 | 0 |   –  | 0.00 |   –  |   –  |
| location | content | 196 | 0 | 196 | 0 | 0 | 0 | 1.00 | 1.00 | 1.00 | 1.00 |
| sequencing_platform | content | 358 | 0 | 309 | 5 | 44 | 0 | 1.00 | 0.88 | 0.93 | 0.98 |
| sex | content | 118 | 0 | 1 | 2 | 115 | 0 | 1.00 | 0.03 | 0.05 | 0.33 |
| smoker | content | 196 | 0 | 0 | 196 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.00 |
| target_condition | content | 352 | 0 | 0 | 308 | 44 | 0 | 1.00 | 0.88 | 0.93 | 0.00 |
| treatment | content | 6 | 0 | 0 | 6 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.00 |
| westernized | content | 352 | 0 | 196 | 112 | 44 | 0 | 1.00 | 0.88 | 0.93 | 0.64 |
| curator | id/prov | 358 | 0 | 0 | 0 | 358 | 0 |   –  | 0.00 |   –  |   –  |
| host_species | id/prov | 358 | 0 | 352 | 6 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.98 |
| ncbi_accession | id/prov | 358 | 0 | 0 | 6 | 352 | 0 | 1.00 | 0.02 | 0.03 | 0.00 |
| pmid | id/prov | 358 | 0 | 246 | 112 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.69 |
| sample_id | id/prov | 358 | 0 | 0 | 352 | 6 | 0 | 1.00 | 0.98 | 0.99 | 0.00 |
| study_name | id/prov | 358 | 0 | 0 | 352 | 6 | 0 | 1.00 | 0.98 | 0.99 | 0.00 |
| subject_id | id/prov | 358 | 0 | 0 | 6 | 352 | 0 | 1.00 | 0.02 | 0.03 | 0.00 |

### Decision legend
TN=both not-reported · TPc=both reported & match · TPw=both reported but differ (often raw-vs-harmonized surface form) · FN=gold has it, extractor missed · FP=extractor claims it, gold blank.
