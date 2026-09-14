# MetaExtractor × curatedMetagenomicData — evaluation

Run dir: `sonnet_r3`. Gold: cMD `*_sample.tsv`. Content fields, micro-averaged. Values compared after harmonization; harmonized fields: body_site, disease, treatment (other fields as extracted).

| score | precision | recall | F1 | TPc | TPw | FN | FP |
|---|--:|--:|--:|--:|--:|--:|--:|
| all curated | 0.464 | 0.017 | 0.033 | 291 | 336 | 16228 | 0 |
| matched | 0.464 | 0.181 | 0.261 | 291 | 336 | 980 | 0 |

## Per study (all curated)

| study | gold n | ext n | key | matched | unmatched | pooled | ambiguous | extra (keyed) | extra (no key) | TPc | TPw | FN | FP |
|---|--:|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Bengtsson-PalmeJ_2015 | 70 | 0 | – | 0 | 70 | 0 | 0 | 0 | 0 | 0 | 0 | 1190 | 0 |
| TettAJ_2019_b | 44 | 50 | – | 0 | 44 | 0 | 0 | 50 | 0 | 0 | 0 | 701 | 0 |
| LiJ_2017 | 196 | 6 | – | 0 | 196 | 0 | 0 | 6 | 0 | 0 | 0 | 2744 | 0 |
| NayakRR_2021 | 34 | 434 | ncbi_accession | 34 | 0 | 0 | 0 | 400 | 0 | 117 | 155 | 102 | 0 |
| PasolliE_2019 (extraction failed) | 112 | 0 | – | 0 | 112 | 0 | 0 | 0 | 0 | 0 | 0 | 2240 | 0 |
| Heitz-BuschartA_2016 | 53 | 221 | ncbi_accession | 53 | 0 | 0 | 0 | 168 | 0 | 159 | 106 | 833 | 0 |
| FanY_2023 (extraction failed) | 147 | 0 | – | 0 | 147 | 0 | 0 | 0 | 0 | 0 | 0 | 1617 | 0 |
| QinJ_2012 | 363 | 0 | – | 0 | 363 | 0 | 0 | 0 | 0 | 0 | 0 | 6041 | 0 |
| ContevilleLC_2019 | 15 | 15 | ncbi_accession | 15 | 0 | 0 | 0 | 0 | 0 | 15 | 75 | 45 | 0 |
| LiSS_2016 | 55 | 0 | – | 0 | 55 | 0 | 0 | 0 | 0 | 0 | 0 | 715 | 0 |

TPc = both reported, harmonized values match · TPw = both reported, harmonized values differ · FN = gold reported, extraction did not · FP = extraction reported, gold blank. A gold-blank cell is not by itself evidence of fabrication.
