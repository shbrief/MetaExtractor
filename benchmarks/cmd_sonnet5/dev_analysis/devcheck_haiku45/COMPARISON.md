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

`out_v3 TPc` lists the repeats whose extraction did not fail; the comparison uses their median. Where those repeats disagree the difference is repeat-to-repeat model variance, not a consequence of the rule changes, and is counted separately. `gold distinct` is how many distinct values the field takes across the study's curated rows; 1 means a single study-wide value, which blanket study-to-sample propagation used to supply without per-sample evidence.

| study | field | out_v3 TPc (completed repeats) | median | TPc dev | gold distinct | v3 repeats agree |
|---|---|---|---|---|---|---|
| Bengtsson-PalmeJ_2015 | age | 16/16 | 16 | 0 | 9 | yes |
| Bengtsson-PalmeJ_2015 | age_group | 70/70 | 70 | 0 | 1 (constant) | yes |
| Bengtsson-PalmeJ_2015 | age_max | 2/2 | 2 | 0 | 9 | yes |
| Bengtsson-PalmeJ_2015 | age_min | 26/26 | 26 | 0 | 9 | yes |
| Bengtsson-PalmeJ_2015 | age_unit | 70/70 | 70 | 0 | 1 (constant) | yes |
| Bengtsson-PalmeJ_2015 | antibiotics_current_use | 70/70 | 70 | 0 | 1 (constant) | yes |
| Bengtsson-PalmeJ_2015 | sample_id | 0/0 | 0 | 70 | 70 | yes |
| Bengtsson-PalmeJ_2015 | sex | 52/52 | 52 | 0 | 2 | yes |
| Bengtsson-PalmeJ_2015 | westernized | 0/70 | 35 | 0 | 1 (constant) | no |
| ContevilleLC_2019 | disease | 15/15/15 | 15 | 0 | 1 (constant) | yes |
| ContevilleLC_2019 | host_species | 15/0/15 | 15 | 15 | 1 (constant) | no |
| ContevilleLC_2019 | sample_id | 0/0/0 | 0 | 15 | 15 | yes |
| ContevilleLC_2019 | subject_id | 15/15/15 | 15 | 0 | 15 | yes |
| Heitz-BuschartA_2016 | disease | 0/0/24 | 0 | 0 | 5 | no |
| Heitz-BuschartA_2016 | host_species | 0/53/53 | 53 | 53 | 1 (constant) | no |
| Heitz-BuschartA_2016 | sample_id | 0/0/0 | 0 | 53 | 53 | yes |
| Heitz-BuschartA_2016 | subject_id | 0/0/0 | 0 | 53 | 20 | yes |
| Heitz-BuschartA_2016 | westernized | 0/53/0 | 0 | 0 | 1 (constant) | no |
| NayakRR_2021 | host_species | 0/0/0 | 0 | 34 | 1 (constant) | yes |
| NayakRR_2021 | sample_id | 0/0/0 | 0 | 34 | 34 | yes |
| NayakRR_2021 | treatment | 0/0/0 | 0 | 17 | 2 | yes |
| PasolliE_2019 | age_unit | 112/112/112 | 112 | 0 | 1 (constant) | yes |

- correct cells **gained**: 276
- correct cells **lost** where the out_v3 repeats agreed (attributable to the rule changes): 448
- correct cells **lost** where the out_v3 repeats disagreed (model variance): 35
