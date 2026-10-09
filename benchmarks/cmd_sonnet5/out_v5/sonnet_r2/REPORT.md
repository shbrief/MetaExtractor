# MetaExtractor × curatedMetagenomicData — evaluation

Run dir: `sonnet_r2`. Gold: cMD `*_sample.tsv`. Content fields, micro-averaged. Values compared after harmonization; harmonized fields: body_site, disease, dna_extraction_kit, host_species, sequencing_platform, treatment (other fields as extracted).

| score | precision | recall | F1 | TPc | TPw | FN | FP |
|---|--:|--:|--:|--:|--:|--:|--:|
| all curated | 0.747 | 0.106 | 0.186 | 1993 | 676 | 16121 | 0 |
| matched | 0.747 | 0.339 | 0.466 | 1993 | 676 | 3215 | 0 |

## Per study (all curated)

| study | gold n | ext n | key | matched | unmatched | pooled | ambiguous | extra (keyed) | extra (no key) | TPc | TPw | FN | FP |
|---|--:|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Bengtsson-PalmeJ_2015 | 70 | 70 | ncbi_accession | 70 | 0 | 0 | 0 | 0 | 0 | 350 | 70 | 770 | 0 |
| TettAJ_2019_b | 162 | 50 | sample_id | 50 | 112 | 0 | 0 | 0 | 0 | 180 | 217 | 2239 | 0 |
| LiJ_2017 | 196 | 6 | – | 0 | 196 | 0 | 0 | 6 | 0 | 0 | 0 | 2744 | 0 |
| NayakRR_2021 | 34 | 434 | ncbi_accession | 34 | 0 | 0 | 0 | 400 | 0 | 136 | 68 | 170 | 0 |
| PasolliE_2019 | 112 | 112 | sample_id | 112 | 0 | 0 | 0 | 0 | 0 | 1008 | 224 | 1008 | 0 |
| Heitz-BuschartA_2016 | 53 | 221 | ncbi_accession | 53 | 0 | 0 | 0 | 168 | 0 | 289 | 82 | 727 | 0 |
| FanY_2023 | 147 | 100 | – | 0 | 147 | 0 | 0 | 100 | 0 | 0 | 0 | 1617 | 0 |
| QinJ_2012 | 363 | 0 | – | 0 | 363 | 0 | 0 | 0 | 0 | 0 | 0 | 6041 | 0 |
| ContevilleLC_2019 | 15 | 15 | ncbi_accession | 15 | 0 | 0 | 0 | 0 | 0 | 30 | 15 | 90 | 0 |
| LiSS_2016 | 55 | 0 | – | 0 | 55 | 0 | 0 | 0 | 0 | 0 | 0 | 715 | 0 |

TPc = both reported, harmonized values match · TPw = both reported, harmonized values differ · FN = gold reported, extraction did not · FP = extraction reported, gold blank. A gold-blank cell is not by itself evidence of fabrication.
