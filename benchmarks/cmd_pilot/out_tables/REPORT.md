# MetaExtractor × curatedMetagenomicData — pilot evaluation

Target schema: `curatedmetagenomicdata/cmd.linkml.yaml`. Gold: cMD `*_sample.tsv`. Samples joined **positionally**.

## Headline (content fields, micro-averaged)

- Precision **0.88**, Recall **0.73**, F1 **0.80**, value-accuracy-on-attempted **0.45**
- cells: TN=339 TPc=1867 TPw=2289 FN=1529 FP=588

## Per study

| study | pmid | gold n | ext n | align | content P | R | F1 | val-acc |
|---|---|--:|--:|---|--:|--:|--:|--:|
| Bengtsson-PalmeJ_2015 | 26259788 | 70 | 28 | aligned on ncbi_accession: 0/70 gold matched (ext=28) |   –  |   –  |   –  |   –  |
| TettAJ_2019_b | 31607556 | 44 | 171 | aligned on ncbi_accession: 44/44 gold matched (ext=171) | 1.00 | 0.38 | 0.55 | 0.34 |
| LiJ_2017 | 28143587 | 196 | 196 | aligned on ncbi_accession: 196/196 gold matched (ext=196) | 0.81 | 0.93 | 0.87 | 0.48 |
| NayakRR_2021 | – | – | – | no extraction output | – | – | – | – |
| PasolliE_2019 | 30661755 | 112 | 164 | aligned on ncbi_accession: 112/112 gold matched (ext=164) | 1.00 | 0.60 | 0.75 | 0.42 |

## Per field (all studies, micro)

| field | kind | N | TN | TPc | TPw | FN | FP | P | R | F1 | val-acc |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| age | content | 156 | 1 | 0 | 0 | 155 | 0 |   –  | 0.00 |   –  |   –  |
| age_group | content | 352 | 0 | 0 | 112 | 240 | 0 | 1.00 | 0.32 | 0.48 | 0.00 |
| age_max | content | 352 | 0 | 1 | 351 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.00 |
| age_min | content | 352 | 0 | 1 | 351 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.00 |
| age_unit | content | 156 | 1 | 112 | 0 | 43 | 0 | 1.00 | 0.72 | 0.84 | 1.00 |
| age_years | content | 156 | 1 | 0 | 0 | 155 | 0 |   –  | 0.00 |   –  |   –  |
| ancestry | content | 112 | 0 | 0 | 0 | 112 | 0 |   –  | 0.00 |   –  |   –  |
| ancestry_details | content | 112 | 0 | 0 | 112 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.00 |
| antibiotics_current_use | content | 308 | 0 | 196 | 0 | 112 | 0 | 1.00 | 0.64 | 0.78 | 1.00 |
| biomarker_name | content | 308 | 112 | 0 | 0 | 0 | 196 | 0.00 |   –  |   –  |   –  |
| biomarker_unit | content | 308 | 112 | 0 | 0 | 0 | 196 | 0.00 |   –  |   –  |   –  |
| biomarker_value | content | 308 | 112 | 0 | 0 | 0 | 196 | 0.00 |   –  |   –  |   –  |
| bmi | content | 112 | 0 | 0 | 0 | 112 | 0 |   –  | 0.00 |   –  |   –  |
| body_site | content | 352 | 0 | 44 | 196 | 112 | 0 | 1.00 | 0.68 | 0.81 | 0.18 |
| control | content | 352 | 0 | 153 | 155 | 44 | 0 | 1.00 | 0.88 | 0.93 | 0.50 |
| country | content | 352 | 0 | 196 | 112 | 44 | 0 | 1.00 | 0.88 | 0.93 | 0.64 |
| disease | content | 352 | 0 | 112 | 196 | 44 | 0 | 1.00 | 0.88 | 0.93 | 0.36 |
| dna_extraction_kit | content | 352 | 0 | 196 | 156 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.56 |
| family | content | 156 | 0 | 0 | 0 | 156 | 0 |   –  | 0.00 |   –  |   –  |
| family_role | content | 44 | 0 | 0 | 0 | 44 | 0 |   –  | 0.00 |   –  |   –  |
| location | content | 196 | 0 | 196 | 0 | 0 | 0 | 1.00 | 1.00 | 1.00 | 1.00 |
| sequencing_platform | content | 352 | 0 | 352 | 0 | 0 | 0 | 1.00 | 1.00 | 1.00 | 1.00 |
| sex | content | 112 | 0 | 0 | 0 | 112 | 0 |   –  | 0.00 |   –  |   –  |
| smoker | content | 196 | 0 | 0 | 196 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.00 |
| target_condition | content | 352 | 0 | 0 | 352 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.00 |
| westernized | content | 352 | 0 | 308 | 0 | 44 | 0 | 1.00 | 0.88 | 0.93 | 1.00 |
| curator | id/prov | 352 | 0 | 0 | 0 | 352 | 0 |   –  | 0.00 |   –  |   –  |
| host_species | id/prov | 352 | 0 | 352 | 0 | 0 | 0 | 1.00 | 1.00 | 1.00 | 1.00 |
| ncbi_accession | id/prov | 352 | 0 | 352 | 0 | 0 | 0 | 1.00 | 1.00 | 1.00 | 1.00 |
| pmid | id/prov | 352 | 0 | 352 | 0 | 0 | 0 | 1.00 | 1.00 | 1.00 | 1.00 |
| sample_id | id/prov | 352 | 0 | 0 | 352 | 0 | 0 | 1.00 | 1.00 | 1.00 | 0.00 |
| study_name | id/prov | 352 | 0 | 0 | 0 | 352 | 0 |   –  | 0.00 |   –  |   –  |
| subject_id | id/prov | 352 | 0 | 0 | 0 | 352 | 0 |   –  | 0.00 |   –  |   –  |

### Decision legend
TN=both not-reported · TPc=both reported & match · TPw=both reported but differ (often raw-vs-harmonized surface form) · FN=gold has it, extractor missed · FP=extractor claims it, gold blank.
