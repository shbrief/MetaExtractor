# Aggregate — `out_v3`

Content fields, micro-averaged; median [min–max] across repeats. Values are compared after harmonization: fields with a MetaHarmonizer crosswalk as ontology codes (against the curated ontology id where present), other fields as extracted. Precision = TPc/(TPc+TPw+FP), recall = TPc/(TPc+TPw+FN).

Harmonized fields (sonnet): body_site, disease, treatment.
Harmonized fields (haiku): body_site, disease, treatment.

## Score all curated

| model | precision | recall | F1 | TPc | TPw | FP | FN |
|---|--:|--:|--:|--:|--:|--:|--:|
| sonnet | 0.739 [0.637–0.739] | 0.118 [0.105–0.126] | 0.203 [0.180–0.216] | 1982 [1762–2130] | 752 [699–1006] | 0 [0–0] | 14087 [13973–14174] |
| haiku | 0.683 [0.601–0.691] | 0.112 [0.083–0.115] | 0.193 [0.148–0.193] | 1891 [1392–1932] | 879 [623–1259] | 0 [0–22] | 14085 [13664–14840] |

## Score matched

| model | precision | recall | F1 | TPc | TPw | FP | FN |
|---|--:|--:|--:|--:|--:|--:|--:|
| sonnet | 0.739 [0.637–0.739] | 0.393 [0.350–0.423] | 0.514 [0.452–0.538] | 1982 [1762–2130] | 752 [699–1006] | 0 [0–0] | 2269 [2155–2356] |
| haiku | 0.683 [0.601–0.691] | 0.375 [0.362–0.384] | 0.475 [0.468–0.484] | 1891 [1392–1932] | 879 [623–1259] | 0 [0–22] | 1846 [1832–2267] |

## Sensitivity: all curated, successful extractions only

| model | precision | recall | F1 | TPc | TPw | FP | FN |
|---|--:|--:|--:|--:|--:|--:|--:|
| sonnet | 0.739 [0.637–0.739] | 0.118 [0.105–0.126] | 0.203 [0.180–0.216] | 1982 [1762–2130] | 752 [699–1006] | 0 [0–0] | 14087 [13973–14174] |
| haiku | 0.683 [0.601–0.691] | 0.112 [0.089–0.115] | 0.193 [0.157–0.193] | 1891 [1392–1932] | 879 [623–1259] | 0 [0–22] | 13664 [13650–14085] |

Paired all-curated F1 difference (sonnet − haiku): +0.021, 95% study-cluster bootstrap CI [-0.013, +0.088] (10 studies, B=2000).


## Harmonized fields

| field | model | score | precision | recall | F1 | TPc | TPw | FP | FN |
|---|---|---|--:|--:|--:|--:|--:|--:|--:|
| body_site | sonnet | all curated | 1.000 [0.843–1.000] | 0.198 [0.167–0.247] | 0.331 [0.279–0.396] | 216 [182–269] | 0 [0–34] | 0 [0–0] | 873 [820–873] |
| body_site | sonnet | matched | 1.000 [0.843–1.000] | 0.761 [0.641–0.947] | 0.864 [0.728–0.973] | 216 [182–269] | 0 [0–34] | 0 [0–0] | 68 [15–68] |
| disease | sonnet | all curated | 1.000 [1.000–1.000] | 0.167 [0.134–0.198] | 0.286 [0.236–0.331] | 182 [146–216] | 0 [0–0] | 0 [0–0] | 907 [873–943] |
| disease | sonnet | matched | 1.000 [1.000–1.000] | 0.641 [0.514–0.761] | 0.781 [0.679–0.864] | 182 [146–216] | 0 [0–0] | 0 [0–0] | 102 [68–138] |
| treatment | sonnet | all curated | 0.500 [0.500–0.500] | 0.038 [0.038–0.038] | 0.071 [0.071–0.071] | 17 [17–17] | 17 [17–17] | 0 [0–0] | 411 [411–411] |
| treatment | sonnet | matched | 0.500 [0.500–0.500] | 0.262 [0.262–0.262] | 0.343 [0.343–0.343] | 17 [17–17] | 17 [17–17] | 0 [0–0] | 31 [31–31] |
| body_site | haiku | all curated | 1.000 [1.000–1.000] | 0.230 [0.165–0.230] | 0.373 [0.284–0.373] | 250 [180–250] | 0 [0–0] | 0 [0–0] | 839 [839–909] |
| body_site | haiku | matched | 1.000 [1.000–1.000] | 0.880 [0.841–0.880] | 0.936 [0.914–0.936] | 250 [180–250] | 0 [0–0] | 0 [0–0] | 34 [34–34] |
| disease | haiku | all curated | 1.000 [0.839–1.000] | 0.117 [0.117–0.139] | 0.209 [0.209–0.238] | 127 [127–151] | 0 [0–29] | 0 [0–0] | 962 [909–962] |
| disease | haiku | matched | 1.000 [0.839–1.000] | 0.532 [0.447–0.593] | 0.651 [0.618–0.745] | 127 [127–151] | 0 [0–29] | 0 [0–0] | 104 [87–157] |
| treatment | haiku | all curated | 0.000 [0.000–0.000] | 0.000 [0.000–0.000] | – | 0 [0–0] | 0 [0–31] | 0 [0–22] | 445 [414–445] |
| treatment | haiku | matched | 0.000 [0.000–0.000] | 0.000 [0.000–0.000] | – | 0 [0–0] | 0 [0–31] | 0 [0–22] | 65 [34–65] |

haiku: extractions with no output after the retry (scored as producing no records): haiku_r1/Bengtsson-PalmeJ_2015

## sonnet: per study × repeat (content cells)

| study | gold n | repeat | ext n | key | matched | unmatched | pooled | ambiguous | extra | TPc | TPw | FN (all curated) | FN (matched) | FP |
|---|--:|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Bengtsson-PalmeJ_2015 | 70 | sonnet_r1 | 70 | ncbi_accession | 70 | 0 | 0 | 0 | 0 | 518 | 182 | 490 | 490 | 0 |
| Bengtsson-PalmeJ_2015 | 70 | sonnet_r2 | 70 | ncbi_accession | 70 | 0 | 0 | 0 | 0 | 518 | 322 | 350 | 350 | 0 |
| Bengtsson-PalmeJ_2015 | 70 | sonnet_r3 | 70 | ncbi_accession | 70 | 0 | 0 | 0 | 0 | 448 | 182 | 560 | 560 | 0 |
| TettAJ_2019_b | 44 | sonnet_r1 | 50 | – | 0 | 44 | 0 | 0 | 50 | 0 | 0 | 701 | 0 | 0 |
| TettAJ_2019_b | 44 | sonnet_r2 | 50 | – | 0 | 44 | 0 | 0 | 50 | 0 | 0 | 701 | 0 | 0 |
| TettAJ_2019_b | 44 | sonnet_r3 | 50 | – | 0 | 44 | 0 | 0 | 50 | 0 | 0 | 701 | 0 | 0 |
| LiJ_2017 | 196 | sonnet_r1 | 6 | – | 0 | 196 | 0 | 0 | 6 | 0 | 0 | 2744 | 0 | 0 |
| LiJ_2017 | 196 | sonnet_r2 | 6 | – | 0 | 196 | 0 | 0 | 6 | 0 | 0 | 2744 | 0 | 0 |
| LiJ_2017 | 196 | sonnet_r3 | 6 | – | 0 | 196 | 0 | 0 | 6 | 0 | 0 | 2744 | 0 | 0 |
| NayakRR_2021 | 34 | sonnet_r1 | 434 | ncbi_accession | 34 | 0 | 0 | 0 | 400 | 117 | 155 | 102 | 102 | 0 |
| NayakRR_2021 | 34 | sonnet_r2 | 434 | ncbi_accession | 34 | 0 | 0 | 0 | 400 | 117 | 121 | 136 | 136 | 0 |
| NayakRR_2021 | 34 | sonnet_r3 | 434 | ncbi_accession | 34 | 0 | 0 | 0 | 400 | 151 | 155 | 68 | 68 | 0 |
| PasolliE_2019 | 112 | sonnet_r1 | 112 | sample_id | 112 | 0 | 0 | 0 | 0 | 1006 | 450 | 784 | 784 | 0 |
| PasolliE_2019 | 112 | sonnet_r2 | 112 | sample_id | 112 | 0 | 0 | 0 | 0 | 1230 | 226 | 784 | 784 | 0 |
| PasolliE_2019 | 112 | sonnet_r3 | 112 | sample_id | 112 | 0 | 0 | 0 | 0 | 1118 | 226 | 896 | 896 | 0 |
| Heitz-BuschartA_2016 | 53 | sonnet_r1 | 221 | ncbi_accession | 53 | 0 | 0 | 0 | 168 | 106 | 159 | 833 | 833 | 0 |
| Heitz-BuschartA_2016 | 53 | sonnet_r2 | 221 | ncbi_accession | 53 | 0 | 0 | 0 | 168 | 265 | 53 | 780 | 780 | 0 |
| Heitz-BuschartA_2016 | 53 | sonnet_r3 | 221 | ncbi_accession | 53 | 0 | 0 | 0 | 168 | 265 | 106 | 727 | 727 | 0 |
| FanY_2023 | 147 | sonnet_r1 | 510 | – | 0 | 147 | 0 | 0 | 510 | 0 | 0 | 1617 | 0 | 0 |
| FanY_2023 | 147 | sonnet_r2 | 319 | – | 0 | 147 | 0 | 0 | 319 | 0 | 0 | 1617 | 0 | 0 |
| FanY_2023 | 147 | sonnet_r3 | 319 | – | 0 | 147 | 0 | 0 | 319 | 0 | 0 | 1617 | 0 | 0 |
| QinJ_2012 | 363 | sonnet_r1 | 0 | – | 0 | 363 | 0 | 0 | 0 | 0 | 0 | 6041 | 0 | 0 |
| QinJ_2012 | 363 | sonnet_r2 | 0 | – | 0 | 363 | 0 | 0 | 0 | 0 | 0 | 6041 | 0 | 0 |
| QinJ_2012 | 363 | sonnet_r3 | 0 | – | 0 | 363 | 0 | 0 | 0 | 0 | 0 | 6041 | 0 | 0 |
| ContevilleLC_2019 | 15 | sonnet_r1 | 15 | ncbi_accession | 15 | 0 | 0 | 0 | 0 | 15 | 60 | 60 | 60 | 0 |
| ContevilleLC_2019 | 15 | sonnet_r2 | 15 | ncbi_accession | 15 | 0 | 0 | 0 | 0 | 0 | 30 | 105 | 105 | 0 |
| ContevilleLC_2019 | 15 | sonnet_r3 | 15 | ncbi_accession | 15 | 0 | 0 | 0 | 0 | 0 | 30 | 105 | 105 | 0 |
| LiSS_2016 | 55 | sonnet_r1 | 0 | – | 0 | 55 | 0 | 0 | 0 | 0 | 0 | 715 | 0 | 0 |
| LiSS_2016 | 55 | sonnet_r2 | 0 | – | 0 | 55 | 0 | 0 | 0 | 0 | 0 | 715 | 0 | 0 |
| LiSS_2016 | 55 | sonnet_r3 | 0 | – | 0 | 55 | 0 | 0 | 0 | 0 | 0 | 715 | 0 | 0 |

### sonnet: age bounds by provenance (all curated, pooled over repeats)

| field:source | TPc | TPw | FN | FP | precision |
|---|--:|--:|--:|--:|--:|
| age_max:age_rule | 336 | 0 | 0 | 0 | 1.000 |
| age_max:other | 6 | 204 | 2133 | 0 | 0.029 |
| age_min:age_rule | 336 | 0 | 0 | 0 | 1.000 |
| age_min:other | 78 | 132 | 2133 | 0 | 0.371 |

## haiku: per study × repeat (content cells)

| study | gold n | repeat | ext n | key | matched | unmatched | pooled | ambiguous | extra | TPc | TPw | FN (all curated) | FN (matched) | FP |
|---|--:|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Bengtsson-PalmeJ_2015 | 70 | haiku_r1 (failed) | 0 | – | 0 | 70 | 0 | 0 | 0 | 0 | 0 | 1190 | 0 | 0 |
| Bengtsson-PalmeJ_2015 | 70 | haiku_r2 | 70 | ncbi_accession | 70 | 0 | 0 | 0 | 0 | 446 | 324 | 420 | 420 | 0 |
| Bengtsson-PalmeJ_2015 | 70 | haiku_r3 | 70 | ncbi_accession | 70 | 0 | 0 | 0 | 0 | 516 | 464 | 210 | 210 | 0 |
| TettAJ_2019_b | 44 | haiku_r1 | 50 | – | 0 | 44 | 0 | 0 | 50 | 0 | 0 | 701 | 0 | 0 |
| TettAJ_2019_b | 44 | haiku_r2 | 50 | – | 0 | 44 | 0 | 0 | 50 | 0 | 0 | 701 | 0 | 0 |
| TettAJ_2019_b | 44 | haiku_r3 | 50 | – | 0 | 44 | 0 | 0 | 50 | 0 | 0 | 701 | 0 | 0 |
| LiJ_2017 | 196 | haiku_r1 | 1448 | – | 0 | 196 | 0 | 0 | 1448 | 0 | 0 | 2744 | 0 | 0 |
| LiJ_2017 | 196 | haiku_r2 | 1448 | – | 0 | 196 | 0 | 0 | 1448 | 0 | 0 | 2744 | 0 | 0 |
| LiJ_2017 | 196 | haiku_r3 | 1448 | – | 0 | 196 | 0 | 0 | 1448 | 0 | 0 | 2744 | 0 | 0 |
| NayakRR_2021 | 34 | haiku_r1 | 434 | ncbi_accession | 34 | 0 | 0 | 0 | 400 | 0 | 136 | 238 | 238 | 0 |
| NayakRR_2021 | 34 | haiku_r2 | 434 | ncbi_accession | 34 | 0 | 0 | 0 | 400 | 0 | 68 | 306 | 306 | 0 |
| NayakRR_2021 | 34 | haiku_r3 | 434 | ncbi_accession | 34 | 0 | 0 | 0 | 400 | 0 | 136 | 238 | 238 | 0 |
| PasolliE_2019 | 112 | haiku_r1 | 112 | sample_id | 112 | 0 | 0 | 0 | 0 | 1120 | 336 | 784 | 784 | 0 |
| PasolliE_2019 | 112 | haiku_r2 | 112 | sample_id | 112 | 0 | 0 | 0 | 0 | 1120 | 336 | 784 | 784 | 0 |
| PasolliE_2019 | 112 | haiku_r3 | 112 | sample_id | 112 | 0 | 0 | 0 | 0 | 1120 | 448 | 672 | 672 | 0 |
| Heitz-BuschartA_2016 | 53 | haiku_r1 | 221 | ncbi_accession | 53 | 0 | 0 | 0 | 168 | 212 | 106 | 780 | 780 | 0 |
| Heitz-BuschartA_2016 | 53 | haiku_r2 | 221 | ncbi_accession | 53 | 0 | 0 | 0 | 168 | 265 | 106 | 727 | 727 | 0 |
| Heitz-BuschartA_2016 | 53 | haiku_r3 | 221 | ncbi_accession | 53 | 0 | 0 | 0 | 168 | 236 | 166 | 696 | 696 | 22 |
| FanY_2023 | 147 | haiku_r1 | 319 | – | 0 | 147 | 0 | 0 | 319 | 0 | 0 | 1617 | 0 | 0 |
| FanY_2023 | 147 | haiku_r2 | 319 | – | 0 | 147 | 0 | 0 | 319 | 0 | 0 | 1617 | 0 | 0 |
| FanY_2023 | 147 | haiku_r3 | 319 | – | 0 | 147 | 0 | 0 | 319 | 0 | 0 | 1617 | 0 | 0 |
| QinJ_2012 | 363 | haiku_r1 | 0 | – | 0 | 363 | 0 | 0 | 0 | 0 | 0 | 6041 | 0 | 0 |
| QinJ_2012 | 363 | haiku_r2 | 0 | – | 0 | 363 | 0 | 0 | 0 | 0 | 0 | 6041 | 0 | 0 |
| QinJ_2012 | 363 | haiku_r3 | 0 | – | 0 | 363 | 0 | 0 | 0 | 0 | 0 | 6041 | 0 | 0 |
| ContevilleLC_2019 | 15 | haiku_r1 | 15 | ncbi_accession | 15 | 0 | 0 | 0 | 0 | 60 | 45 | 30 | 30 | 0 |
| ContevilleLC_2019 | 15 | haiku_r2 | 15 | ncbi_accession | 15 | 0 | 0 | 0 | 0 | 60 | 45 | 30 | 30 | 0 |
| ContevilleLC_2019 | 15 | haiku_r3 | 15 | ncbi_accession | 15 | 0 | 0 | 0 | 0 | 60 | 45 | 30 | 30 | 0 |
| LiSS_2016 | 55 | haiku_r1 | 0 | – | 0 | 55 | 0 | 0 | 0 | 0 | 0 | 715 | 0 | 0 |
| LiSS_2016 | 55 | haiku_r2 | 0 | – | 0 | 55 | 0 | 0 | 0 | 0 | 0 | 715 | 0 | 0 |
| LiSS_2016 | 55 | haiku_r3 | 0 | – | 0 | 55 | 0 | 0 | 0 | 0 | 0 | 715 | 0 | 0 |

### haiku: age bounds by provenance (all curated, pooled over repeats)

| field:source | TPc | TPw | FN | FP | precision |
|---|--:|--:|--:|--:|--:|
| age_max:age_rule | 336 | 0 | 0 | 0 | 1.000 |
| age_max:other | 4 | 136 | 2203 | 0 | 0.029 |
| age_min:age_rule | 336 | 0 | 0 | 0 | 1.000 |
| age_min:other | 52 | 88 | 2203 | 0 | 0.371 |

### haiku: false-positive source check (pooled over repeats)

Partial check only: whether the asserted value string, or the study-level evidence quote, occurs verbatim in the saved retrieved text. It does not establish fabrication or gold incompleteness.

| field | FP cells | value in text | study evidence in text |
|---|--:|--:|--:|
| treatment | 22 | 22 | 0 |

## Attempt ledger

- tasks 60, attempts 64, failed attempts 5, initial failures 4, final successes 59
- window 2026-09-14T19:42:38+00:00 → 2026-09-14T20:53:10+00:00 (UTC); commits ['c05c29acef6dc590bdbde0d99dbe7f6266d12cc6']; dirty tree: False
  - haiku/1/Bengtsson-PalmeJ_2015: fail_rc2
  - haiku/1/ContevilleLC_2019: fail_rc2
  - haiku/2/Bengtsson-PalmeJ_2015: fail_rc2
  - haiku/2/NayakRR_2021: fail_rc2
