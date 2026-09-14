# MetaExtractor × curatedMetagenomicData — evaluation

Run dir: `sonnet_r1`. Gold: cMD `*_sample.tsv`. Content fields, micro-averaged.

| join | value P | value R | value F1 | presence P | presence R | TPc | TPw | FN | FP |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| end-to-end (primary) | 0.582 | 0.089 | 0.154 | 1.000 | 0.153 | 1499 | 1076 | 14280 | 0 |
| conditional (matched rows) | 0.582 | 0.298 | 0.394 | 1.000 | 0.511 | 1499 | 1076 | 2462 | 0 |
| positional (supplementary) | 0.523 | 0.281 | 0.366 | 0.999 | 0.538 | 1662 | 1514 | 2730 | 2 |

## Per study (end-to-end)

| study | gold n | ext n | key | matched | unmatched | pooled | ambiguous | extra (keyed) | extra (no key) | TPc | TPw | FN | FP |
|---|--:|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Bengtsson-PalmeJ_2015 | 70 | 70 | ncbi_accession | 70 | 0 | 0 | 0 | 0 | 0 | 378 | 252 | 560 | 0 |
| TettAJ_2019_b | 44 | 50 | – | 0 | 44 | 0 | 0 | 50 | 0 | 0 | 0 | 701 | 0 |
| LiJ_2017 | 196 | 12 | – | 0 | 196 | 0 | 0 | 6 | 6 | 0 | 0 | 2744 | 0 |
| NayakRR_2021 | 34 | 434 | ncbi_accession | 34 | 0 | 0 | 0 | 400 | 0 | 68 | 170 | 136 | 0 |
| PasolliE_2019 | 112 | 112 | sample_id | 112 | 0 | 0 | 0 | 0 | 0 | 894 | 450 | 896 | 0 |
| Heitz-BuschartA_2016 | 53 | 221 | ncbi_accession | 53 | 0 | 0 | 0 | 168 | 0 | 159 | 159 | 780 | 0 |
| FanY_2023 (extraction failed) | 147 | 0 | – | 0 | 147 | 0 | 0 | 0 | 0 | 0 | 0 | 1617 | 0 |
| QinJ_2012 | 363 | 0 | – | 0 | 363 | 0 | 0 | 0 | 0 | 0 | 0 | 6041 | 0 |
| ContevilleLC_2019 | 15 | 15 | ncbi_accession | 15 | 0 | 0 | 0 | 0 | 0 | 0 | 45 | 90 | 0 |
| LiSS_2016 | 55 | 0 | – | 0 | 55 | 0 | 0 | 0 | 0 | 0 | 0 | 715 | 0 |

TPc = both reported, values match · TPw = both reported, values differ · FN = gold reported, extraction did not · FP = extraction reported, gold blank. A gold-blank cell is not by itself evidence of fabrication.
