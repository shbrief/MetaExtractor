# Aggregate — `out_v2`

Content fields, micro-averaged; median [min–max] across repeats. Value-aware metrics count only value-correct cells as hits; presence metrics count any reported value.


## end-to-end

| model | value P | value R | value F1 | presence P | presence R | presence F1 | value acc (TP) | FP | FN |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| sonnet | 0.481 [0.383–0.582] | 0.017 [0.014–0.089] | 0.032 [0.027–0.154] | 1.000 [1.000–1.000] | 0.037 [0.035–0.153] | 0.072 [0.067–0.265] | 0.481 [0.383–0.582] | 0 [0–0] | 16228 [14280–16273] |
| haiku | 0.621 [0.616–0.654] | 0.073 [0.072–0.076] | 0.131 [0.129–0.136] | 1.000 [0.989–1.000] | 0.117 [0.116–0.117] | 0.209 [0.208–0.209] | 0.628 [0.616–0.654] | 0 [0–22] | 14889 [14888–14899] |

## end-to-end-successful-only

| model | value P | value R | value F1 | presence P | presence R | presence F1 | value acc (TP) | FP | FN |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| sonnet | 0.481 [0.383–0.582] | 0.019 [0.018–0.098] | 0.037 [0.035–0.168] | 1.000 [1.000–1.000] | 0.048 [0.040–0.169] | 0.092 [0.077–0.289] | 0.481 [0.383–0.582] | 0 [0–0] | 12663 [12371–14033] |
| haiku | 0.621 [0.616–0.654] | 0.073 [0.072–0.076] | 0.131 [0.129–0.136] | 1.000 [0.989–1.000] | 0.117 [0.116–0.117] | 0.209 [0.208–0.209] | 0.628 [0.616–0.654] | 0 [0–22] | 14889 [14888–14899] |

## conditional

| model | value P | value R | value F1 | presence P | presence R | presence F1 | value acc (TP) | FP | FN |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| sonnet | 0.481 [0.383–0.582] | 0.174 [0.149–0.298] | 0.256 [0.215–0.394] | 1.000 [1.000–1.000] | 0.390 [0.362–0.511] | 0.561 [0.532–0.677] | 0.481 [0.383–0.582] | 0 [0–0] | 1025 [980–2462] |
| haiku | 0.621 [0.616–0.654] | 0.321 [0.315–0.333] | 0.423 [0.417–0.441] | 1.000 [0.989–1.000] | 0.511 [0.508–0.511] | 0.674 [0.674–0.676] | 0.628 [0.616–0.654] | 0 [0–22] | 1881 [1880–1891] |

## positional

| model | value P | value R | value F1 | presence P | presence R | presence F1 | value acc (TP) | FP | FN |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| sonnet | 0.428 [0.357–0.523] | 0.172 [0.149–0.281] | 0.232 [0.221–0.366] | 0.999 [0.998–0.999] | 0.482 [0.349–0.538] | 0.650 [0.517–0.699] | 0.428 [0.357–0.523] | 2 [2–2] | 2610 [1239–2730] |
| haiku | 0.679 [0.677–0.711] | 0.346 [0.336–0.384] | 0.458 [0.457–0.490] | 1.000 [0.995–1.000] | 0.510 [0.473–0.562] | 0.676 [0.642–0.719] | 0.682 [0.677–0.711] | 2 [1–23] | 4362 [3899–4694] |

Paired end-to-end value-F1 difference (sonnet − haiku): -0.058, 95% study-cluster bootstrap CI [-0.187, +0.061] (10 studies, B=2000).


sonnet: extractions with no output after the retry (scored end-to-end as all-FN): sonnet_r1/FanY_2023, sonnet_r2/PasolliE_2019, sonnet_r3/FanY_2023, sonnet_r3/PasolliE_2019

## sonnet: per study × repeat (end-to-end content cells)

| study | gold n | repeat | ext n | key | matched | unmatched | pooled | ambiguous | extra | TPc | TPw | FN | FP | positional FP |
|---|--:|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Bengtsson-PalmeJ_2015 | 70 | sonnet_r1 | 70 | ncbi_accession | 70 | 0 | 0 | 0 | 0 | 378 | 252 | 560 | 0 | 0 |
| Bengtsson-PalmeJ_2015 | 70 | sonnet_r2 | 0 | – | 0 | 70 | 0 | 0 | 0 | 0 | 0 | 1190 | 0 | 0 |
| Bengtsson-PalmeJ_2015 | 70 | sonnet_r3 | 0 | – | 0 | 70 | 0 | 0 | 0 | 0 | 0 | 1190 | 0 | 0 |
| TettAJ_2019_b | 44 | sonnet_r1 | 50 | – | 0 | 44 | 0 | 0 | 50 | 0 | 0 | 701 | 0 | 2 |
| TettAJ_2019_b | 44 | sonnet_r2 | 50 | – | 0 | 44 | 0 | 0 | 50 | 0 | 0 | 701 | 0 | 2 |
| TettAJ_2019_b | 44 | sonnet_r3 | 50 | – | 0 | 44 | 0 | 0 | 50 | 0 | 0 | 701 | 0 | 2 |
| LiJ_2017 | 196 | sonnet_r1 | 12 | – | 0 | 196 | 0 | 0 | 12 | 0 | 0 | 2744 | 0 | 0 |
| LiJ_2017 | 196 | sonnet_r2 | 6 | – | 0 | 196 | 0 | 0 | 6 | 0 | 0 | 2744 | 0 | 0 |
| LiJ_2017 | 196 | sonnet_r3 | 6 | – | 0 | 196 | 0 | 0 | 6 | 0 | 0 | 2744 | 0 | 0 |
| NayakRR_2021 | 34 | sonnet_r1 | 434 | ncbi_accession | 34 | 0 | 0 | 0 | 400 | 68 | 170 | 136 | 0 | 0 |
| NayakRR_2021 | 34 | sonnet_r2 | 434 | ncbi_accession | 34 | 0 | 0 | 0 | 400 | 68 | 204 | 102 | 0 | 0 |
| NayakRR_2021 | 34 | sonnet_r3 | 434 | ncbi_accession | 34 | 0 | 0 | 0 | 400 | 66 | 206 | 102 | 0 | 0 |
| PasolliE_2019 | 112 | sonnet_r1 | 112 | sample_id | 112 | 0 | 0 | 0 | 0 | 894 | 450 | 896 | 0 | 0 |
| PasolliE_2019 | 112 | sonnet_r2 (failed) | 0 | – | 0 | 112 | 0 | 0 | 0 | 0 | 0 | 2240 | 0 | 0 |
| PasolliE_2019 | 112 | sonnet_r3 (failed) | 0 | – | 0 | 112 | 0 | 0 | 0 | 0 | 0 | 2240 | 0 | 0 |
| Heitz-BuschartA_2016 | 53 | sonnet_r1 | 221 | ncbi_accession | 53 | 0 | 0 | 0 | 168 | 159 | 159 | 780 | 0 | 0 |
| Heitz-BuschartA_2016 | 53 | sonnet_r2 | 221 | ncbi_accession | 53 | 0 | 0 | 0 | 168 | 212 | 53 | 833 | 0 | 0 |
| Heitz-BuschartA_2016 | 53 | sonnet_r3 | 221 | ncbi_accession | 53 | 0 | 0 | 0 | 168 | 159 | 106 | 833 | 0 | 0 |
| FanY_2023 | 147 | sonnet_r1 (failed) | 0 | – | 0 | 147 | 0 | 0 | 0 | 0 | 0 | 1617 | 0 | 0 |
| FanY_2023 | 147 | sonnet_r2 | 510 | – | 0 | 147 | 0 | 0 | 510 | 0 | 0 | 1617 | 0 | 0 |
| FanY_2023 | 147 | sonnet_r3 (failed) | 0 | – | 0 | 147 | 0 | 0 | 0 | 0 | 0 | 1617 | 0 | 0 |
| QinJ_2012 | 363 | sonnet_r1 | 0 | – | 0 | 363 | 0 | 0 | 0 | 0 | 0 | 6041 | 0 | 0 |
| QinJ_2012 | 363 | sonnet_r2 | 0 | – | 0 | 363 | 0 | 0 | 0 | 0 | 0 | 6041 | 0 | 0 |
| QinJ_2012 | 363 | sonnet_r3 | 0 | – | 0 | 363 | 0 | 0 | 0 | 0 | 0 | 6041 | 0 | 0 |
| ContevilleLC_2019 | 15 | sonnet_r1 | 15 | ncbi_accession | 15 | 0 | 0 | 0 | 0 | 0 | 45 | 90 | 0 | 0 |
| ContevilleLC_2019 | 15 | sonnet_r2 | 15 | ncbi_accession | 15 | 0 | 0 | 0 | 0 | 0 | 45 | 90 | 0 | 0 |
| ContevilleLC_2019 | 15 | sonnet_r3 | 15 | ncbi_accession | 15 | 0 | 0 | 0 | 0 | 15 | 75 | 45 | 0 | 0 |
| LiSS_2016 | 55 | sonnet_r1 | 0 | – | 0 | 55 | 0 | 0 | 0 | 0 | 0 | 715 | 0 | 0 |
| LiSS_2016 | 55 | sonnet_r2 | 0 | – | 0 | 55 | 0 | 0 | 0 | 0 | 0 | 715 | 0 | 0 |
| LiSS_2016 | 55 | sonnet_r3 | 0 | – | 0 | 55 | 0 | 0 | 0 | 0 | 0 | 715 | 0 | 0 |

### sonnet: age bounds by provenance (end-to-end, pooled over repeats)

| field:source | TPc | TPw | FN | FP | value acc |
|---|--:|--:|--:|--:|--:|
| age_max:age_rule | 112 | 0 | 0 | 0 | 1.000 |
| age_max:other | 2 | 68 | 2497 | 0 | 0.029 |
| age_min:age_rule | 112 | 0 | 0 | 0 | 1.000 |
| age_min:other | 26 | 44 | 2497 | 0 | 0.371 |

## haiku: per study × repeat (end-to-end content cells)

| study | gold n | repeat | ext n | key | matched | unmatched | pooled | ambiguous | extra | TPc | TPw | FN | FP | positional FP |
|---|--:|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Bengtsson-PalmeJ_2015 | 70 | haiku_r1 | 0 | – | 0 | 70 | 0 | 0 | 0 | 0 | 0 | 1190 | 0 | 0 |
| Bengtsson-PalmeJ_2015 | 70 | haiku_r2 | 0 | – | 0 | 70 | 0 | 0 | 0 | 0 | 0 | 1190 | 0 | 0 |
| Bengtsson-PalmeJ_2015 | 70 | haiku_r3 | 0 | – | 0 | 70 | 0 | 0 | 0 | 0 | 0 | 1190 | 0 | 0 |
| TettAJ_2019_b | 44 | haiku_r1 | 50 | – | 0 | 44 | 0 | 0 | 50 | 0 | 0 | 701 | 0 | 1 |
| TettAJ_2019_b | 44 | haiku_r2 | 50 | – | 0 | 44 | 0 | 0 | 50 | 0 | 0 | 701 | 0 | 2 |
| TettAJ_2019_b | 44 | haiku_r3 | 50 | – | 0 | 44 | 0 | 0 | 50 | 0 | 0 | 701 | 0 | 1 |
| LiJ_2017 | 196 | haiku_r1 | 1448 | – | 0 | 196 | 0 | 0 | 1448 | 0 | 0 | 2744 | 0 | 0 |
| LiJ_2017 | 196 | haiku_r2 | 1448 | – | 0 | 196 | 0 | 0 | 1448 | 0 | 0 | 2744 | 0 | 0 |
| LiJ_2017 | 196 | haiku_r3 | 1448 | – | 0 | 196 | 0 | 0 | 1448 | 0 | 0 | 2744 | 0 | 0 |
| NayakRR_2021 | 34 | haiku_r1 | 434 | ncbi_accession | 34 | 0 | 0 | 0 | 400 | 0 | 136 | 238 | 0 | 0 |
| NayakRR_2021 | 34 | haiku_r2 | 434 | ncbi_accession | 34 | 0 | 0 | 0 | 400 | 0 | 102 | 272 | 0 | 0 |
| NayakRR_2021 | 34 | haiku_r3 | 434 | ncbi_accession | 34 | 0 | 0 | 0 | 400 | 0 | 102 | 272 | 0 | 0 |
| PasolliE_2019 | 112 | haiku_r1 | 112 | sample_id | 112 | 0 | 0 | 0 | 0 | 1008 | 336 | 896 | 0 | 0 |
| PasolliE_2019 | 112 | haiku_r2 | 112 | sample_id | 112 | 0 | 0 | 0 | 0 | 1008 | 448 | 784 | 0 | 0 |
| PasolliE_2019 | 112 | haiku_r3 | 112 | sample_id | 112 | 0 | 0 | 0 | 0 | 1008 | 448 | 784 | 0 | 0 |
| Heitz-BuschartA_2016 | 53 | haiku_r1 | 221 | ncbi_accession | 53 | 0 | 0 | 0 | 168 | 212 | 159 | 727 | 0 | 0 |
| Heitz-BuschartA_2016 | 53 | haiku_r2 | 221 | ncbi_accession | 53 | 0 | 0 | 0 | 168 | 159 | 159 | 780 | 0 | 0 |
| Heitz-BuschartA_2016 | 53 | haiku_r3 | 221 | ncbi_accession | 53 | 0 | 0 | 0 | 168 | 212 | 137 | 749 | 22 | 22 |
| FanY_2023 | 147 | haiku_r1 | 319 | – | 0 | 147 | 0 | 0 | 319 | 0 | 0 | 1617 | 0 | 0 |
| FanY_2023 | 147 | haiku_r2 | 319 | – | 0 | 147 | 0 | 0 | 319 | 0 | 0 | 1617 | 0 | 0 |
| FanY_2023 | 147 | haiku_r3 | 319 | – | 0 | 147 | 0 | 0 | 319 | 0 | 0 | 1617 | 0 | 0 |
| QinJ_2012 | 363 | haiku_r1 | 0 | – | 0 | 363 | 0 | 0 | 0 | 0 | 0 | 6041 | 0 | 0 |
| QinJ_2012 | 363 | haiku_r2 | 0 | – | 0 | 363 | 0 | 0 | 0 | 0 | 0 | 6041 | 0 | 0 |
| QinJ_2012 | 363 | haiku_r3 | 0 | – | 0 | 363 | 0 | 0 | 0 | 0 | 0 | 6041 | 0 | 0 |
| ContevilleLC_2019 | 15 | haiku_r1 | 15 | ncbi_accession | 15 | 0 | 0 | 0 | 0 | 60 | 45 | 30 | 0 | 0 |
| ContevilleLC_2019 | 15 | haiku_r2 | 15 | ncbi_accession | 15 | 0 | 0 | 0 | 0 | 45 | 45 | 45 | 0 | 0 |
| ContevilleLC_2019 | 15 | haiku_r3 | 15 | ncbi_accession | 15 | 0 | 0 | 0 | 0 | 15 | 45 | 75 | 0 | 0 |
| LiSS_2016 | 55 | haiku_r1 | 0 | – | 0 | 55 | 0 | 0 | 0 | 0 | 0 | 715 | 0 | 0 |
| LiSS_2016 | 55 | haiku_r2 | 0 | – | 0 | 55 | 0 | 0 | 0 | 0 | 0 | 715 | 0 | 0 |
| LiSS_2016 | 55 | haiku_r3 | 0 | – | 0 | 55 | 0 | 0 | 0 | 0 | 0 | 715 | 0 | 0 |

### haiku: age bounds by provenance (end-to-end, pooled over repeats)

| field:source | TPc | TPw | FN | FP | value acc |
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
