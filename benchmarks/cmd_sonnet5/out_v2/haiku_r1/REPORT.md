# MetaExtractor × curatedMetagenomicData — evaluation

Run dir: `haiku_r1`. Gold: cMD `*_sample.tsv`. Content fields, micro-averaged.

| join | value P | value R | value F1 | presence P | presence R | TPc | TPw | FN | FP |
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| end-to-end (primary) | 0.654 | 0.076 | 0.136 | 1.000 | 0.116 | 1280 | 676 | 14899 | 0 |
| conditional (matched rows) | 0.654 | 0.333 | 0.441 | 1.000 | 0.508 | 1280 | 676 | 1891 | 0 |
| positional (supplementary) | 0.711 | 0.336 | 0.457 | 1.000 | 0.473 | 2996 | 1219 | 4694 | 1 |

## Per study (end-to-end)

| study | gold n | ext n | key | matched | unmatched | pooled | ambiguous | extra (keyed) | extra (no key) | TPc | TPw | FN | FP |
|---|--:|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Bengtsson-PalmeJ_2015 | 70 | 0 | – | 0 | 70 | 0 | 0 | 0 | 0 | 0 | 0 | 1190 | 0 |
| TettAJ_2019_b | 44 | 50 | – | 0 | 44 | 0 | 0 | 50 | 0 | 0 | 0 | 701 | 0 |
| LiJ_2017 | 196 | 1448 | – | 0 | 196 | 0 | 0 | 1448 | 0 | 0 | 0 | 2744 | 0 |
| NayakRR_2021 | 34 | 434 | ncbi_accession | 34 | 0 | 0 | 0 | 400 | 0 | 0 | 136 | 238 | 0 |
| PasolliE_2019 | 112 | 112 | sample_id | 112 | 0 | 0 | 0 | 0 | 0 | 1008 | 336 | 896 | 0 |
| Heitz-BuschartA_2016 | 53 | 221 | ncbi_accession | 53 | 0 | 0 | 0 | 168 | 0 | 212 | 159 | 727 | 0 |
| FanY_2023 | 147 | 319 | – | 0 | 147 | 0 | 0 | 312 | 7 | 0 | 0 | 1617 | 0 |
| QinJ_2012 | 363 | 0 | – | 0 | 363 | 0 | 0 | 0 | 0 | 0 | 0 | 6041 | 0 |
| ContevilleLC_2019 | 15 | 15 | ncbi_accession | 15 | 0 | 0 | 0 | 0 | 0 | 60 | 45 | 30 | 0 |
| LiSS_2016 | 55 | 0 | – | 0 | 55 | 0 | 0 | 0 | 0 | 0 | 0 | 715 | 0 |

TPc = both reported, values match · TPw = both reported, values differ · FN = gold reported, extraction did not · FP = extraction reported, gold blank. A gold-blank cell is not by itself evidence of fabrication.
