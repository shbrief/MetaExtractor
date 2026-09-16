# Development-set check (commit 852de78) vs out_v3 Haiku repeats

One Haiku 4.5 repeat on the ten development studies, scored post-harmonization
against each tree's own crosswalks. out_v3 columns are its three Haiku repeats.

## Per study

| study | records v3 (r1/r2/r3) | records dev | matched v3 | matched dev | F1 all-curated v3 | F1 all-curated dev | F1 matched v3 | F1 matched dev |
|---|---|---|---|---|---|---|---|---|
| Bengtsson-PalmeJ_2015 | 0/70/70 | 70 | 0/70/70 | 70 | –/0.455/0.476 | 0.190 | –/0.455/0.476 | 0.190 |
| TettAJ_2019_b | 50/50/50 | 50 | 0/0/0 | 0 | –/–/– | – | –/–/– | – |
| LiJ_2017 | 1448/1448/1448 | 6 | 0/0/0 | 0 | –/–/– | – | –/–/– | – |
| NayakRR_2021 | 434/434/434 | 434 | 34/34/34 | 34 | –/–/– | 0.067 | –/–/– | 0.067 |
| PasolliE_2019 | 112/112/112 | 112 | 112/112/112 | 112 | 0.606/0.606/0.588 | 0.563 | 0.606/0.606/0.588 | 0.563 |
| Heitz-BuschartA_2016 | 221/221/221 | 221 | 53/53/53 | 53 | 0.299/0.361/0.310 | 0.299 | 0.299/0.361/0.310 | 0.299 |
| FanY_2023 | 319/319/319 | 510 | 0/0/0 | 0 | –/–/– | – | –/–/– | – |
| QinJ_2012 | 0/0/0 | 0 | 0/0/0 | 0 | –/–/– | – | –/–/– | – |
| ContevilleLC_2019 | 15/15/15 | 15 | 15/15/15 | 15 | 0.500/0.500/0.500 | 0.400 | 0.500/0.500/0.500 | 0.400 |
| LiSS_2016 | 0/0/0 | 0 | 0/0/0 | 0 | –/–/– | – | –/–/– | – |

## Pooled over the ten studies

| run | join | TPc | TPw | FN | FP | F1 |
|---|---|---|---|---|---|---|
| out_v3 haiku_r1 | all curated | 1392 | 623 | 14840 | 0 | 0.1475 |
| out_v3 haiku_r2 | all curated | 1891 | 879 | 14085 | 0 | 0.1927 |
| out_v3 haiku_r3 | all curated | 1932 | 1259 | 13664 | 22 | 0.1925 |
| **devcheck** | all curated | 1422 | 746 | 14687 | 0 | **0.1495** |
| out_v3 haiku_r1 | matched | 1392 | 623 | 1832 | 0 | 0.4749 |
| out_v3 haiku_r2 | matched | 1891 | 879 | 2267 | 0 | 0.4844 |
| out_v3 haiku_r3 | matched | 1932 | 1259 | 1846 | 22 | 0.4684 |
| **devcheck** | matched | 1422 | 746 | 2869 | 0 | **0.3947** |

## Correct cells gained and lost, by field

`gold distinct` is the number of distinct values the field takes across that study's curated rows; 1 means a single study-wide value, which blanket study-to-sample propagation used to supply for free.

| study | field | best TPc in out_v3 | TPc dev | gold distinct |
|---|---|---|---|---|
| Bengtsson-PalmeJ_2015 | age | 16 | 0 | 9 |
| Bengtsson-PalmeJ_2015 | age_group | 70 | 0 | 1 (constant) |
| Bengtsson-PalmeJ_2015 | age_max | 2 | 0 | 9 |
| Bengtsson-PalmeJ_2015 | age_min | 26 | 0 | 9 |
| Bengtsson-PalmeJ_2015 | age_unit | 70 | 0 | 1 (constant) |
| Bengtsson-PalmeJ_2015 | antibiotics_current_use | 70 | 0 | 1 (constant) |
| Bengtsson-PalmeJ_2015 | sample_id | 0 | 70 | 70 |
| Bengtsson-PalmeJ_2015 | sex | 52 | 0 | 2 |
| Bengtsson-PalmeJ_2015 | westernized | 70 | 0 | 1 (constant) |
| ContevilleLC_2019 | disease | 15 | 0 | 1 (constant) |
| ContevilleLC_2019 | sample_id | 0 | 15 | 15 |
| ContevilleLC_2019 | subject_id | 15 | 0 | 15 |
| Heitz-BuschartA_2016 | disease | 24 | 0 | 5 |
| Heitz-BuschartA_2016 | sample_id | 0 | 53 | 53 |
| Heitz-BuschartA_2016 | subject_id | 0 | 53 | 20 |
| Heitz-BuschartA_2016 | westernized | 53 | 0 | 1 (constant) |
| NayakRR_2021 | host_species | 0 | 34 | 1 (constant) |
| NayakRR_2021 | sample_id | 0 | 34 | 34 |
| NayakRR_2021 | treatment | 0 | 17 | 2 |
| PasolliE_2019 | age_unit | 112 | 0 | 1 (constant) |

- correct cells **gained**: 276
- correct cells **lost** where the gold field is constant within the study: 460
- correct cells **lost** where the gold field varies within the study: 135
