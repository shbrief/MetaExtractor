# Aggregate — `/Users/sehyunoh/OmicsMLRepo/MetaExtractor/benchmarks/cmd_sonnet5/dev_analysis/devfull`

Content fields, micro-averaged; median [min–max] across repeats. Values are compared after harmonization: fields with a MetaHarmonizer crosswalk as ontology codes (against the curated ontology id where present), other fields as extracted. Precision = TPc/(TPc+TPw+FP), recall = TPc/(TPc+TPw+FN).

Harmonized fields (sonnet): body_site, disease, treatment.
Harmonized fields (haiku): body_site, disease, treatment.

## Score all curated

| model | precision | recall | F1 | TPc | TPw | FP | FN |
|---|--:|--:|--:|--:|--:|--:|--:|
| sonnet | 0.710 [0.668–0.743] | 0.087 [0.078–0.089] | 0.154 [0.141–0.158] | 1469 [1314–1494] | 611 [454–731] | 0 [0–0] | 14750 [14655–15087] |
| haiku | 0.683 [0.678–0.699] | 0.096 [0.096–0.097] | 0.169 [0.168–0.170] | 1617 [1611–1635] | 746 [697–775] | 0 [0–0] | 14498 [14445–14541] |

## Score matched

| model | precision | recall | F1 | TPc | TPw | FP | FN |
|---|--:|--:|--:|--:|--:|--:|--:|
| sonnet | 0.710 [0.668–0.743] | 0.292 [0.261–0.297] | 0.406 [0.386–0.418] | 1469 [1314–1494] | 611 [454–731] | 0 [0–0] | 2932 [2837–3269] |
| haiku | 0.683 [0.678–0.699] | 0.321 [0.320–0.325] | 0.439 [0.436–0.440] | 1617 [1611–1635] | 746 [697–775] | 0 [0–0] | 2680 [2627–2723] |

## Sensitivity: all curated, successful extractions only

| model | precision | recall | F1 | TPc | TPw | FP | FN |
|---|--:|--:|--:|--:|--:|--:|--:|
| sonnet | 0.710 [0.668–0.743] | 0.087 [0.078–0.089] | 0.154 [0.141–0.158] | 1469 [1314–1494] | 611 [454–731] | 0 [0–0] | 14750 [14655–15087] |
| haiku | 0.683 [0.678–0.699] | 0.096 [0.096–0.097] | 0.169 [0.168–0.170] | 1617 [1611–1635] | 746 [697–775] | 0 [0–0] | 14498 [14445–14541] |

Paired all-curated F1 difference (sonnet − haiku): -0.018, 95% study-cluster bootstrap CI [-0.054, +0.008] (10 studies, B=2000).


## Harmonized fields

| field | model | score | precision | recall | F1 | TPc | TPw | FP | FN |
|---|---|---|--:|--:|--:|--:|--:|--:|--:|
| body_site | sonnet | all curated | 1.000 [1.000–1.000] | 0.148 [0.148–0.212] | 0.258 [0.258–0.350] | 161 [161–231] | 0 [0–0] | 0 [0–0] | 928 [858–928] |
| body_site | sonnet | matched | 1.000 [1.000–1.000] | 0.567 [0.567–0.813] | 0.724 [0.724–0.897] | 161 [161–231] | 0 [0–0] | 0 [0–0] | 123 [53–123] |
| disease | sonnet | all curated | 1.000 [1.000–1.000] | 0.134 [0.103–0.198] | 0.236 [0.187–0.331] | 146 [112–216] | 0 [0–0] | 0 [0–0] | 943 [873–977] |
| disease | sonnet | matched | 1.000 [1.000–1.000] | 0.514 [0.394–0.761] | 0.679 [0.566–0.864] | 146 [112–216] | 0 [0–0] | 0 [0–0] | 138 [68–172] |
| treatment | sonnet | all curated | 0.500 [0.500–0.500] | 0.038 [0.038–0.038] | 0.071 [0.071–0.071] | 17 [17–17] | 17 [17–17] | 0 [0–0] | 411 [411–411] |
| treatment | sonnet | matched | 0.500 [0.500–0.500] | 0.262 [0.262–0.262] | 0.343 [0.343–0.343] | 17 [17–17] | 17 [17–17] | 0 [0–0] | 31 [31–31] |
| body_site | haiku | all curated | 1.000 [1.000–1.000] | 0.261 [0.230–0.261] | 0.414 [0.373–0.414] | 284 [250–284] | 0 [0–0] | 0 [0–0] | 805 [805–839] |
| body_site | haiku | matched | 1.000 [1.000–1.000] | 1.000 [0.880–1.000] | 1.000 [0.936–1.000] | 284 [250–284] | 0 [0–0] | 0 [0–0] | 0 [0–34] |
| disease | haiku | all curated | 1.000 [0.839–1.000] | 0.139 [0.117–0.167] | 0.238 [0.209–0.286] | 151 [127–182] | 0 [0–29] | 0 [0–0] | 909 [907–962] |
| disease | haiku | matched | 1.000 [0.839–1.000] | 0.532 [0.447–0.641] | 0.651 [0.618–0.781] | 151 [127–182] | 0 [0–29] | 0 [0–0] | 104 [102–157] |
| treatment | haiku | all curated | 0.500 [0.500–0.500] | 0.038 [0.038–0.038] | 0.071 [0.071–0.071] | 17 [17–17] | 17 [17–17] | 0 [0–0] | 411 [411–411] |
| treatment | haiku | matched | 0.500 [0.500–0.500] | 0.262 [0.262–0.262] | 0.343 [0.343–0.343] | 17 [17–17] | 17 [17–17] | 0 [0–0] | 31 [31–31] |

## sonnet: per study × repeat (content cells)

| study | gold n | repeat | ext n | key | matched | unmatched | pooled | ambiguous | extra | TPc | TPw | FN (all curated) | FN (matched) | FP |
|---|--:|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Bengtsson-PalmeJ_2015 | 70 | sonnet_r1 | 70 | ncbi_accession | 70 | 0 | 0 | 0 | 0 | 140 | 140 | 910 | 910 | 0 |
| Bengtsson-PalmeJ_2015 | 70 | sonnet_r2 | 70 | ncbi_accession | 70 | 0 | 0 | 0 | 0 | 280 | 140 | 770 | 770 | 0 |
| Bengtsson-PalmeJ_2015 | 70 | sonnet_r3 | 70 | ncbi_accession | 70 | 0 | 0 | 0 | 0 | 140 | 140 | 910 | 910 | 0 |
| TettAJ_2019_b | 44 | sonnet_r1 | 50 | – | 0 | 44 | 0 | 0 | 50 | 0 | 0 | 701 | 0 | 0 |
| TettAJ_2019_b | 44 | sonnet_r2 | 50 | – | 0 | 44 | 0 | 0 | 50 | 0 | 0 | 701 | 0 | 0 |
| TettAJ_2019_b | 44 | sonnet_r3 | 50 | – | 0 | 44 | 0 | 0 | 50 | 0 | 0 | 701 | 0 | 0 |
| LiJ_2017 | 196 | sonnet_r1 | 6 | – | 0 | 196 | 0 | 0 | 6 | 0 | 0 | 2744 | 0 | 0 |
| LiJ_2017 | 196 | sonnet_r2 | 6 | – | 0 | 196 | 0 | 0 | 6 | 0 | 0 | 2744 | 0 | 0 |
| LiJ_2017 | 196 | sonnet_r3 | 6 | – | 0 | 196 | 0 | 0 | 6 | 0 | 0 | 2744 | 0 | 0 |
| NayakRR_2021 | 34 | sonnet_r1 | 434 | ncbi_accession | 34 | 0 | 0 | 0 | 400 | 119 | 119 | 136 | 136 | 0 |
| NayakRR_2021 | 34 | sonnet_r2 | 434 | ncbi_accession | 34 | 0 | 0 | 0 | 400 | 119 | 119 | 136 | 136 | 0 |
| NayakRR_2021 | 34 | sonnet_r3 | 434 | ncbi_accession | 34 | 0 | 0 | 0 | 400 | 51 | 119 | 204 | 204 | 0 |
| PasolliE_2019 | 112 | sonnet_r1 | 112 | sample_id | 112 | 0 | 0 | 0 | 0 | 1008 | 224 | 1008 | 1008 | 0 |
| PasolliE_2019 | 112 | sonnet_r2 | 112 | sample_id | 112 | 0 | 0 | 0 | 0 | 896 | 336 | 1008 | 1008 | 0 |
| PasolliE_2019 | 112 | sonnet_r3 | 112 | sample_id | 112 | 0 | 0 | 0 | 0 | 896 | 112 | 1232 | 1232 | 0 |
| Heitz-BuschartA_2016 | 53 | sonnet_r1 | 221 | ncbi_accession | 53 | 0 | 0 | 0 | 168 | 212 | 53 | 833 | 833 | 0 |
| Heitz-BuschartA_2016 | 53 | sonnet_r2 | 221 | ncbi_accession | 53 | 0 | 0 | 0 | 168 | 159 | 106 | 833 | 833 | 0 |
| Heitz-BuschartA_2016 | 53 | sonnet_r3 | 221 | ncbi_accession | 53 | 0 | 0 | 0 | 168 | 212 | 53 | 833 | 833 | 0 |
| FanY_2023 | 147 | sonnet_r1 | 100 | – | 0 | 147 | 0 | 0 | 100 | 0 | 0 | 1617 | 0 | 0 |
| FanY_2023 | 147 | sonnet_r2 | 510 | – | 0 | 147 | 0 | 0 | 510 | 0 | 0 | 1617 | 0 | 0 |
| FanY_2023 | 147 | sonnet_r3 | 100 | – | 0 | 147 | 0 | 0 | 100 | 0 | 0 | 1617 | 0 | 0 |
| QinJ_2012 | 363 | sonnet_r1 | 0 | – | 0 | 363 | 0 | 0 | 0 | 0 | 0 | 6041 | 0 | 0 |
| QinJ_2012 | 363 | sonnet_r2 | 0 | – | 0 | 363 | 0 | 0 | 0 | 0 | 0 | 6041 | 0 | 0 |
| QinJ_2012 | 363 | sonnet_r3 | 0 | – | 0 | 363 | 0 | 0 | 0 | 0 | 0 | 6041 | 0 | 0 |
| ContevilleLC_2019 | 15 | sonnet_r1 | 15 | ncbi_accession | 15 | 0 | 0 | 0 | 0 | 15 | 75 | 45 | 45 | 0 |
| ContevilleLC_2019 | 15 | sonnet_r2 | 15 | ncbi_accession | 15 | 0 | 0 | 0 | 0 | 15 | 30 | 90 | 90 | 0 |
| ContevilleLC_2019 | 15 | sonnet_r3 | 15 | ncbi_accession | 15 | 0 | 0 | 0 | 0 | 15 | 30 | 90 | 90 | 0 |
| LiSS_2016 | 55 | sonnet_r1 | 0 | – | 0 | 55 | 0 | 0 | 0 | 0 | 0 | 715 | 0 | 0 |
| LiSS_2016 | 55 | sonnet_r2 | 0 | – | 0 | 55 | 0 | 0 | 0 | 0 | 0 | 715 | 0 | 0 |
| LiSS_2016 | 55 | sonnet_r3 | 0 | – | 0 | 55 | 0 | 0 | 0 | 0 | 0 | 715 | 0 | 0 |

### sonnet: age bounds by provenance (all curated, pooled over repeats)

| field:source | TPc | TPw | FN | FP | precision |
|---|--:|--:|--:|--:|--:|
| age_max:age_rule | 336 | 0 | 0 | 0 | 1.000 |
| age_max:other | 0 | 0 | 2343 | 0 | – |
| age_min:age_rule | 336 | 0 | 0 | 0 | 1.000 |
| age_min:other | 0 | 0 | 2343 | 0 | – |

## haiku: per study × repeat (content cells)

| study | gold n | repeat | ext n | key | matched | unmatched | pooled | ambiguous | extra | TPc | TPw | FN (all curated) | FN (matched) | FP |
|---|--:|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Bengtsson-PalmeJ_2015 | 70 | haiku_r1 | 70 | ncbi_accession | 70 | 0 | 0 | 0 | 0 | 350 | 140 | 700 | 700 | 0 |
| Bengtsson-PalmeJ_2015 | 70 | haiku_r2 | 70 | ncbi_accession | 70 | 0 | 0 | 0 | 0 | 280 | 140 | 770 | 770 | 0 |
| Bengtsson-PalmeJ_2015 | 70 | haiku_r3 | 70 | ncbi_accession | 70 | 0 | 0 | 0 | 0 | 280 | 140 | 770 | 770 | 0 |
| TettAJ_2019_b | 44 | haiku_r1 | 50 | – | 0 | 44 | 0 | 0 | 50 | 0 | 0 | 701 | 0 | 0 |
| TettAJ_2019_b | 44 | haiku_r2 | 50 | – | 0 | 44 | 0 | 0 | 50 | 0 | 0 | 701 | 0 | 0 |
| TettAJ_2019_b | 44 | haiku_r3 | 50 | – | 0 | 44 | 0 | 0 | 50 | 0 | 0 | 701 | 0 | 0 |
| LiJ_2017 | 196 | haiku_r1 | 6 | – | 0 | 196 | 0 | 0 | 6 | 0 | 0 | 2744 | 0 | 0 |
| LiJ_2017 | 196 | haiku_r2 | 6 | – | 0 | 196 | 0 | 0 | 6 | 0 | 0 | 2744 | 0 | 0 |
| LiJ_2017 | 196 | haiku_r3 | 6 | – | 0 | 196 | 0 | 0 | 6 | 0 | 0 | 2744 | 0 | 0 |
| NayakRR_2021 | 34 | haiku_r1 | 434 | ncbi_accession | 34 | 0 | 0 | 0 | 400 | 17 | 85 | 272 | 272 | 0 |
| NayakRR_2021 | 34 | haiku_r2 | 434 | ncbi_accession | 34 | 0 | 0 | 0 | 400 | 51 | 119 | 204 | 204 | 0 |
| NayakRR_2021 | 34 | haiku_r3 | 434 | ncbi_accession | 34 | 0 | 0 | 0 | 400 | 51 | 119 | 204 | 204 | 0 |
| PasolliE_2019 | 112 | haiku_r1 | 112 | sample_id | 112 | 0 | 0 | 0 | 0 | 1008 | 336 | 896 | 896 | 0 |
| PasolliE_2019 | 112 | haiku_r2 | 112 | sample_id | 112 | 0 | 0 | 0 | 0 | 1008 | 336 | 896 | 896 | 0 |
| PasolliE_2019 | 112 | haiku_r3 | 112 | sample_id | 112 | 0 | 0 | 0 | 0 | 1008 | 336 | 896 | 896 | 0 |
| Heitz-BuschartA_2016 | 53 | haiku_r1 | 221 | ncbi_accession | 53 | 0 | 0 | 0 | 168 | 212 | 106 | 780 | 780 | 0 |
| Heitz-BuschartA_2016 | 53 | haiku_r2 | 221 | ncbi_accession | 53 | 0 | 0 | 0 | 168 | 212 | 106 | 780 | 780 | 0 |
| Heitz-BuschartA_2016 | 53 | haiku_r3 | 221 | ncbi_accession | 53 | 0 | 0 | 0 | 168 | 236 | 135 | 727 | 727 | 0 |
| FanY_2023 | 147 | haiku_r1 | 510 | – | 0 | 147 | 0 | 0 | 510 | 0 | 0 | 1617 | 0 | 0 |
| FanY_2023 | 147 | haiku_r2 | 510 | – | 0 | 147 | 0 | 0 | 510 | 0 | 0 | 1617 | 0 | 0 |
| FanY_2023 | 147 | haiku_r3 | 510 | – | 0 | 147 | 0 | 0 | 510 | 0 | 0 | 1617 | 0 | 0 |
| QinJ_2012 | 363 | haiku_r1 | 0 | – | 0 | 363 | 0 | 0 | 0 | 0 | 0 | 6041 | 0 | 0 |
| QinJ_2012 | 363 | haiku_r2 | 0 | – | 0 | 363 | 0 | 0 | 0 | 0 | 0 | 6041 | 0 | 0 |
| QinJ_2012 | 363 | haiku_r3 | 0 | – | 0 | 363 | 0 | 0 | 0 | 0 | 0 | 6041 | 0 | 0 |
| ContevilleLC_2019 | 15 | haiku_r1 | 15 | ncbi_accession | 15 | 0 | 0 | 0 | 0 | 30 | 30 | 75 | 75 | 0 |
| ContevilleLC_2019 | 15 | haiku_r2 | 15 | ncbi_accession | 15 | 0 | 0 | 0 | 0 | 60 | 45 | 30 | 30 | 0 |
| ContevilleLC_2019 | 15 | haiku_r3 | 15 | ncbi_accession | 15 | 0 | 0 | 0 | 0 | 60 | 45 | 30 | 30 | 0 |
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

## Attempt ledger

- tasks 60, attempts 64, failed attempts 4, initial failures 4, final successes 60
- window 2026-09-16T15:28:28+00:00 → 2026-09-16T18:10:40+00:00 (UTC); commits ['5ace97082dfe59f65e98037e942424bf1e98847e']; dirty tree: False
  - sonnet/1/NayakRR_2021: fail_rc1
  - sonnet/1/TettAJ_2019_b: fail_rc1
  - haiku/2/TettAJ_2019_b: fail_rc1
  - sonnet/2/Bengtsson-PalmeJ_2015: fail_rc1
- haiku: estimated cost over all 31 attempts US$3.18 (228 calls), of which failed attempts US$0.00; attempts without metadata 1
- sonnet: estimated cost over all 33 attempts US$13.00 (262 calls), of which failed attempts US$0.00; attempts without metadata 3
