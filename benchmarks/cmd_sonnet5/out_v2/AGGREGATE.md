# Aggregate — `out_v2`

Content fields, micro-averaged; median [min–max] across repeats. Values are compared after harmonization: fields with a MetaHarmonizer crosswalk as ontology codes (against the curated ontology id where present), other fields as extracted. Precision = TPc/(TPc+TPw+FP), recall = TPc/(TPc+TPw+FN).

Harmonized fields (sonnet): body_site, disease, treatment.
Harmonized fields (haiku): body_site, disease, treatment.

## Score all curated

| model | precision | recall | F1 | TPc | TPw | FP | FN |
|---|--:|--:|--:|--:|--:|--:|--:|
| sonnet | 0.569 [0.464–0.645] | 0.020 [0.017–0.099] | 0.038 [0.033–0.171] | 331 [291–1662] | 336 [251–913] | 0 [0–0] | 16228 [14280–16273] |
| haiku | 0.677 [0.673–0.712] | 0.080 [0.079–0.083] | 0.143 [0.141–0.148] | 1347 [1324–1392] | 620 [564–642] | 0 [0–22] | 14889 [14888–14899] |

## Score matched

| model | precision | recall | F1 | TPc | TPw | FP | FN |
|---|--:|--:|--:|--:|--:|--:|--:|
| sonnet | 0.569 [0.464–0.645] | 0.206 [0.181–0.330] | 0.302 [0.261–0.437] | 331 [291–1662] | 336 [251–913] | 0 [0–0] | 1025 [980–2462] |
| haiku | 0.677 [0.673–0.712] | 0.350 [0.344–0.362] | 0.462 [0.456–0.480] | 1347 [1324–1392] | 620 [564–642] | 0 [0–22] | 1881 [1880–1891] |

## Sensitivity: all curated, successful extractions only

| model | precision | recall | F1 | TPc | TPw | FP | FN |
|---|--:|--:|--:|--:|--:|--:|--:|
| sonnet | 0.569 [0.464–0.645] | 0.023 [0.022–0.109] | 0.044 [0.043–0.187] | 331 [291–1662] | 336 [251–913] | 0 [0–0] | 12663 [12371–14033] |
| haiku | 0.677 [0.673–0.712] | 0.080 [0.079–0.083] | 0.143 [0.141–0.148] | 1347 [1324–1392] | 620 [564–642] | 0 [0–22] | 14889 [14888–14899] |

Paired all-curated F1 difference (sonnet − haiku): -0.060, 95% study-cluster bootstrap CI [-0.202, +0.079] (10 studies, B=2000).


## Harmonized fields

| field | model | score | precision | recall | F1 | TPc | TPw | FP | FN |
|---|---|---|--:|--:|--:|--:|--:|--:|--:|
| body_site | sonnet | all curated | 1.000 [0.306–1.000] | 0.031 [0.014–0.198] | 0.061 [0.026–0.331] | 34 [15–216] | 0 [0–34] | 0 [0–0] | 1040 [873–1055] |
| body_site | sonnet | matched | 1.000 [0.306–1.000] | 0.333 [0.147–0.761] | 0.500 [0.199–0.864] | 34 [15–216] | 0 [0–34] | 0 [0–0] | 68 [53–68] |
| disease | sonnet | all curated | 1.000 [1.000–1.000] | 0.031 [0.031–0.134] | 0.061 [0.061–0.236] | 34 [34–146] | 0 [0–0] | 0 [0–0] | 1055 [943–1055] |
| disease | sonnet | matched | 1.000 [1.000–1.000] | 0.333 [0.333–0.514] | 0.500 [0.500–0.679] | 34 [34–146] | 0 [0–0] | 0 [0–0] | 68 [68–138] |
| treatment | sonnet | all curated | 0.500 [0.500–0.500] | 0.038 [0.038–0.038] | 0.071 [0.071–0.071] | 17 [17–17] | 17 [17–17] | 0 [0–0] | 411 [411–411] |
| treatment | sonnet | matched | 0.500 [0.500–0.500] | 0.262 [0.262–0.262] | 0.343 [0.343–0.343] | 17 [17–17] | 17 [17–17] | 0 [0–0] | 31 [31–31] |
| body_site | haiku | all curated | 0.917 [0.841–1.000] | 0.165 [0.152–0.165] | 0.276 [0.260–0.284] | 180 [165–180] | 15 [0–34] | 0 [0–0] | 909 [875–909] |
| body_site | haiku | matched | 0.917 [0.841–1.000] | 0.841 [0.771–0.841] | 0.841 [0.838–0.914] | 180 [165–180] | 15 [0–34] | 0 [0–0] | 34 [0–34] |
| disease | haiku | all curated | 1.000 [1.000–1.000] | 0.103 [0.103–0.117] | 0.187 [0.187–0.209] | 112 [112–127] | 0 [0–0] | 0 [0–0] | 977 [962–977] |
| disease | haiku | matched | 1.000 [1.000–1.000] | 0.523 [0.523–0.593] | 0.687 [0.687–0.745] | 112 [112–127] | 0 [0–0] | 0 [0–0] | 102 [87–102] |
| treatment | haiku | all curated | 0.000 [0.000–0.000] | 0.000 [0.000–0.000] | – | 0 [0–0] | 0 [0–31] | 0 [0–22] | 445 [414–445] |
| treatment | haiku | matched | 0.000 [0.000–0.000] | 0.000 [0.000–0.000] | – | 0 [0–0] | 0 [0–31] | 0 [0–22] | 65 [34–65] |

sonnet: extractions with no output after the retry (scored as producing no records): sonnet_r1/FanY_2023, sonnet_r2/PasolliE_2019, sonnet_r3/FanY_2023, sonnet_r3/PasolliE_2019

## sonnet: per study × repeat (content cells)

| study | gold n | repeat | ext n | key | matched | unmatched | pooled | ambiguous | extra | TPc | TPw | FN (all curated) | FN (matched) | FP |
|---|--:|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Bengtsson-PalmeJ_2015 | 70 | sonnet_r1 | 70 | ncbi_accession | 70 | 0 | 0 | 0 | 0 | 378 | 252 | 560 | 560 | 0 |
| Bengtsson-PalmeJ_2015 | 70 | sonnet_r2 | 0 | – | 0 | 70 | 0 | 0 | 0 | 0 | 0 | 1190 | 0 | 0 |
| Bengtsson-PalmeJ_2015 | 70 | sonnet_r3 | 0 | – | 0 | 70 | 0 | 0 | 0 | 0 | 0 | 1190 | 0 | 0 |
| TettAJ_2019_b | 44 | sonnet_r1 | 50 | – | 0 | 44 | 0 | 0 | 50 | 0 | 0 | 701 | 0 | 0 |
| TettAJ_2019_b | 44 | sonnet_r2 | 50 | – | 0 | 44 | 0 | 0 | 50 | 0 | 0 | 701 | 0 | 0 |
| TettAJ_2019_b | 44 | sonnet_r3 | 50 | – | 0 | 44 | 0 | 0 | 50 | 0 | 0 | 701 | 0 | 0 |
| LiJ_2017 | 196 | sonnet_r1 | 12 | – | 0 | 196 | 0 | 0 | 12 | 0 | 0 | 2744 | 0 | 0 |
| LiJ_2017 | 196 | sonnet_r2 | 6 | – | 0 | 196 | 0 | 0 | 6 | 0 | 0 | 2744 | 0 | 0 |
| LiJ_2017 | 196 | sonnet_r3 | 6 | – | 0 | 196 | 0 | 0 | 6 | 0 | 0 | 2744 | 0 | 0 |
| NayakRR_2021 | 34 | sonnet_r1 | 434 | ncbi_accession | 34 | 0 | 0 | 0 | 400 | 119 | 119 | 136 | 136 | 0 |
| NayakRR_2021 | 34 | sonnet_r2 | 434 | ncbi_accession | 34 | 0 | 0 | 0 | 400 | 119 | 153 | 102 | 102 | 0 |
| NayakRR_2021 | 34 | sonnet_r3 | 434 | ncbi_accession | 34 | 0 | 0 | 0 | 400 | 117 | 155 | 102 | 102 | 0 |
| PasolliE_2019 | 112 | sonnet_r1 | 112 | sample_id | 112 | 0 | 0 | 0 | 0 | 1006 | 338 | 896 | 896 | 0 |
| PasolliE_2019 | 112 | sonnet_r2 (failed) | 0 | – | 0 | 112 | 0 | 0 | 0 | 0 | 0 | 2240 | 0 | 0 |
| PasolliE_2019 | 112 | sonnet_r3 (failed) | 0 | – | 0 | 112 | 0 | 0 | 0 | 0 | 0 | 2240 | 0 | 0 |
| Heitz-BuschartA_2016 | 53 | sonnet_r1 | 221 | ncbi_accession | 53 | 0 | 0 | 0 | 168 | 159 | 159 | 780 | 780 | 0 |
| Heitz-BuschartA_2016 | 53 | sonnet_r2 | 221 | ncbi_accession | 53 | 0 | 0 | 0 | 168 | 212 | 53 | 833 | 833 | 0 |
| Heitz-BuschartA_2016 | 53 | sonnet_r3 | 221 | ncbi_accession | 53 | 0 | 0 | 0 | 168 | 159 | 106 | 833 | 833 | 0 |
| FanY_2023 | 147 | sonnet_r1 (failed) | 0 | – | 0 | 147 | 0 | 0 | 0 | 0 | 0 | 1617 | 0 | 0 |
| FanY_2023 | 147 | sonnet_r2 | 510 | – | 0 | 147 | 0 | 0 | 510 | 0 | 0 | 1617 | 0 | 0 |
| FanY_2023 | 147 | sonnet_r3 (failed) | 0 | – | 0 | 147 | 0 | 0 | 0 | 0 | 0 | 1617 | 0 | 0 |
| QinJ_2012 | 363 | sonnet_r1 | 0 | – | 0 | 363 | 0 | 0 | 0 | 0 | 0 | 6041 | 0 | 0 |
| QinJ_2012 | 363 | sonnet_r2 | 0 | – | 0 | 363 | 0 | 0 | 0 | 0 | 0 | 6041 | 0 | 0 |
| QinJ_2012 | 363 | sonnet_r3 | 0 | – | 0 | 363 | 0 | 0 | 0 | 0 | 0 | 6041 | 0 | 0 |
| ContevilleLC_2019 | 15 | sonnet_r1 | 15 | ncbi_accession | 15 | 0 | 0 | 0 | 0 | 0 | 45 | 90 | 90 | 0 |
| ContevilleLC_2019 | 15 | sonnet_r2 | 15 | ncbi_accession | 15 | 0 | 0 | 0 | 0 | 0 | 45 | 90 | 90 | 0 |
| ContevilleLC_2019 | 15 | sonnet_r3 | 15 | ncbi_accession | 15 | 0 | 0 | 0 | 0 | 15 | 75 | 45 | 45 | 0 |
| LiSS_2016 | 55 | sonnet_r1 | 0 | – | 0 | 55 | 0 | 0 | 0 | 0 | 0 | 715 | 0 | 0 |
| LiSS_2016 | 55 | sonnet_r2 | 0 | – | 0 | 55 | 0 | 0 | 0 | 0 | 0 | 715 | 0 | 0 |
| LiSS_2016 | 55 | sonnet_r3 | 0 | – | 0 | 55 | 0 | 0 | 0 | 0 | 0 | 715 | 0 | 0 |

### sonnet: age bounds by provenance (all curated, pooled over repeats)

| field:source | TPc | TPw | FN | FP | precision |
|---|--:|--:|--:|--:|--:|
| age_max:age_rule | 112 | 0 | 0 | 0 | 1.000 |
| age_max:other | 2 | 68 | 2497 | 0 | 0.029 |
| age_min:age_rule | 112 | 0 | 0 | 0 | 1.000 |
| age_min:other | 26 | 44 | 2497 | 0 | 0.371 |

## haiku: per study × repeat (content cells)

| study | gold n | repeat | ext n | key | matched | unmatched | pooled | ambiguous | extra | TPc | TPw | FN (all curated) | FN (matched) | FP |
|---|--:|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Bengtsson-PalmeJ_2015 | 70 | haiku_r1 | 0 | – | 0 | 70 | 0 | 0 | 0 | 0 | 0 | 1190 | 0 | 0 |
| Bengtsson-PalmeJ_2015 | 70 | haiku_r2 | 0 | – | 0 | 70 | 0 | 0 | 0 | 0 | 0 | 1190 | 0 | 0 |
| Bengtsson-PalmeJ_2015 | 70 | haiku_r3 | 0 | – | 0 | 70 | 0 | 0 | 0 | 0 | 0 | 1190 | 0 | 0 |
| TettAJ_2019_b | 44 | haiku_r1 | 50 | – | 0 | 44 | 0 | 0 | 50 | 0 | 0 | 701 | 0 | 0 |
| TettAJ_2019_b | 44 | haiku_r2 | 50 | – | 0 | 44 | 0 | 0 | 50 | 0 | 0 | 701 | 0 | 0 |
| TettAJ_2019_b | 44 | haiku_r3 | 50 | – | 0 | 44 | 0 | 0 | 50 | 0 | 0 | 701 | 0 | 0 |
| LiJ_2017 | 196 | haiku_r1 | 1448 | – | 0 | 196 | 0 | 0 | 1448 | 0 | 0 | 2744 | 0 | 0 |
| LiJ_2017 | 196 | haiku_r2 | 1448 | – | 0 | 196 | 0 | 0 | 1448 | 0 | 0 | 2744 | 0 | 0 |
| LiJ_2017 | 196 | haiku_r3 | 1448 | – | 0 | 196 | 0 | 0 | 1448 | 0 | 0 | 2744 | 0 | 0 |
| NayakRR_2021 | 34 | haiku_r1 | 434 | ncbi_accession | 34 | 0 | 0 | 0 | 400 | 0 | 136 | 238 | 238 | 0 |
| NayakRR_2021 | 34 | haiku_r2 | 434 | ncbi_accession | 34 | 0 | 0 | 0 | 400 | 0 | 102 | 272 | 272 | 0 |
| NayakRR_2021 | 34 | haiku_r3 | 434 | ncbi_accession | 34 | 0 | 0 | 0 | 400 | 0 | 102 | 272 | 272 | 0 |
| PasolliE_2019 | 112 | haiku_r1 | 112 | sample_id | 112 | 0 | 0 | 0 | 0 | 1120 | 224 | 896 | 896 | 0 |
| PasolliE_2019 | 112 | haiku_r2 | 112 | sample_id | 112 | 0 | 0 | 0 | 0 | 1120 | 336 | 784 | 784 | 0 |
| PasolliE_2019 | 112 | haiku_r3 | 112 | sample_id | 112 | 0 | 0 | 0 | 0 | 1120 | 336 | 784 | 784 | 0 |
| Heitz-BuschartA_2016 | 53 | haiku_r1 | 221 | ncbi_accession | 53 | 0 | 0 | 0 | 168 | 212 | 159 | 727 | 727 | 0 |
| Heitz-BuschartA_2016 | 53 | haiku_r2 | 221 | ncbi_accession | 53 | 0 | 0 | 0 | 168 | 159 | 159 | 780 | 780 | 0 |
| Heitz-BuschartA_2016 | 53 | haiku_r3 | 221 | ncbi_accession | 53 | 0 | 0 | 0 | 168 | 212 | 137 | 749 | 749 | 22 |
| FanY_2023 | 147 | haiku_r1 | 319 | – | 0 | 147 | 0 | 0 | 319 | 0 | 0 | 1617 | 0 | 0 |
| FanY_2023 | 147 | haiku_r2 | 319 | – | 0 | 147 | 0 | 0 | 319 | 0 | 0 | 1617 | 0 | 0 |
| FanY_2023 | 147 | haiku_r3 | 319 | – | 0 | 147 | 0 | 0 | 319 | 0 | 0 | 1617 | 0 | 0 |
| QinJ_2012 | 363 | haiku_r1 | 0 | – | 0 | 363 | 0 | 0 | 0 | 0 | 0 | 6041 | 0 | 0 |
| QinJ_2012 | 363 | haiku_r2 | 0 | – | 0 | 363 | 0 | 0 | 0 | 0 | 0 | 6041 | 0 | 0 |
| QinJ_2012 | 363 | haiku_r3 | 0 | – | 0 | 363 | 0 | 0 | 0 | 0 | 0 | 6041 | 0 | 0 |
| ContevilleLC_2019 | 15 | haiku_r1 | 15 | ncbi_accession | 15 | 0 | 0 | 0 | 0 | 60 | 45 | 30 | 30 | 0 |
| ContevilleLC_2019 | 15 | haiku_r2 | 15 | ncbi_accession | 15 | 0 | 0 | 0 | 0 | 45 | 45 | 45 | 45 | 0 |
| ContevilleLC_2019 | 15 | haiku_r3 | 15 | ncbi_accession | 15 | 0 | 0 | 0 | 0 | 15 | 45 | 75 | 75 | 0 |
| LiSS_2016 | 55 | haiku_r1 | 0 | – | 0 | 55 | 0 | 0 | 0 | 0 | 0 | 715 | 0 | 0 |
| LiSS_2016 | 55 | haiku_r2 | 0 | – | 0 | 55 | 0 | 0 | 0 | 0 | 0 | 715 | 0 | 0 |
| LiSS_2016 | 55 | haiku_r3 | 0 | – | 0 | 55 | 0 | 0 | 0 | 0 | 0 | 715 | 0 | 0 |

### haiku: age bounds by provenance (all curated, pooled over repeats)

| field:source | TPc | TPw | FN | FP | precision |
|---|--:|--:|--:|--:|--:|
| age_max:age_rule | 336 | 0 | 0 | 0 | 1.000 |
| age_max:other | 0 | 0 | 2343 | 0 | – |
| age_min:age_rule | 336 | 0 | 0 | 0 | 1.000 |
| age_min:other | 0 | 0 | 2343 | 0 | – |

### haiku: false-positive source check (pooled over repeats)

Partial check only: whether the asserted value string, or the study-level evidence quote, occurs verbatim in the saved retrieved text. It does not establish fabrication or gold incompleteness.

| field | FP cells | value in text | study evidence in text |
|---|--:|--:|--:|
| treatment | 22 | 22 | 0 |

## Attempt ledger

- tasks 60, attempts 68, failed attempts 12, initial failures 8, final successes 56
- window 2026-09-14T15:15:06+00:00 → 2026-09-14T17:21:47+00:00 (UTC); commits ['be6a7c15cb9b47a2ec103555d59dbb44071c30b5']; dirty tree: False
  - sonnet/1/FanY_2023: fail_rc2
  - sonnet/2/TettAJ_2019_b: fail_rc2
  - sonnet/2/PasolliE_2019: fail_rc2
  - haiku/3/LiJ_2017: fail_rc2
  - sonnet/3/Heitz-BuschartA_2016: fail_rc1
  - haiku/3/Heitz-BuschartA_2016: fail_rc1
  - sonnet/3/PasolliE_2019: fail_rc2
  - sonnet/3/FanY_2023: fail_rc2
