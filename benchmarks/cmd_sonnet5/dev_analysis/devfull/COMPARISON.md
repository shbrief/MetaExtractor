# Full development-set run (commit 5ace970) vs out_v3

Ten development studies x {Haiku 4.5, Sonnet 5} x 3 repeats in both trees,
scored post-harmonization against each tree's own crosswalks.

## Pooled content F1

| join | model | out_v3 (r1/r2/r3) | devfull (r1/r2/r3) | out_v3 mean | devfull mean |
|---|---|---|---|---|---|
| all curated | haiku | 0.1475/0.1927/0.1925 | 0.1687/0.1677/0.1697 | 0.1776 | **0.1687** |
| all curated | sonnet | 0.1796/0.2158/0.2029 | 0.1576/0.1542/0.1411 | 0.1994 | **0.1510** |
| matched | haiku | 0.4749/0.4844/0.4684 | 0.4399/0.4358/0.4391 | 0.4759 | **0.4383** |
| matched | sonnet | 0.4515/0.5379/0.5136 | 0.4184/0.4060/0.3862 | 0.5010 | **0.4035** |

## Per study, mean content F1 over the three repeats

| study | join | haiku out_v3 | haiku devfull | sonnet out_v3 | sonnet devfull |
|---|---|---|---|---|---|
| Bengtsson-PalmeJ_2015 | all curated | 0.465 | 0.371 | 0.517 | 0.243 |
| Bengtsson-PalmeJ_2015 | matched | 0.465 | 0.371 | 0.517 | 0.243 |
| NayakRR_2021 | all curated | – | 0.149 | 0.396 | 0.322 |
| NayakRR_2021 | matched | – | 0.149 | 0.396 | 0.322 |
| PasolliE_2019 | all curated | 0.600 | 0.563 | 0.611 | 0.549 |
| PasolliE_2019 | matched | 0.600 | 0.563 | 0.611 | 0.549 |
| Heitz-BuschartA_2016 | all curated | 0.323 | 0.307 | 0.297 | 0.285 |
| Heitz-BuschartA_2016 | matched | 0.323 | 0.307 | 0.297 | 0.285 |
| ContevilleLC_2019 | all curated | 0.500 | 0.436 | 0.143 | 0.156 |
| ContevilleLC_2019 | matched | 0.500 | 0.436 | 0.143 | 0.156 |

## Correct cells gained and lost, by field

Per model, over fields where the two trees differ. A field whose surviving out_v3 repeats disagree is counted as model variance.

| model | study | field | out_v3 TPc | devfull TPc | gold distinct | out_v3 agrees |
|---|---|---|---|---|---|---|
| haiku | Bengtsson-PalmeJ_2015 | age | 16/16 | 0/0/0 | 9 | yes |
| haiku | Bengtsson-PalmeJ_2015 | age_group | 70/70 | 0/0/0 | 1 (constant) | yes |
| haiku | Bengtsson-PalmeJ_2015 | age_max | 2/2 | 0/0/0 | 9 | yes |
| haiku | Bengtsson-PalmeJ_2015 | age_min | 26/26 | 0/0/0 | 9 | yes |
| haiku | Bengtsson-PalmeJ_2015 | age_unit | 70/70 | 0/0/0 | 1 (constant) | yes |
| haiku | Bengtsson-PalmeJ_2015 | sample_id | 0/0 | 70/70/70 | 70 | yes |
| haiku | Bengtsson-PalmeJ_2015 | sex | 52/52 | 0/0/0 | 2 | yes |
| haiku | Bengtsson-PalmeJ_2015 | westernized | 0/70 | 70/70/70 | 1 (constant) | no |
| haiku | NayakRR_2021 | body_site | 0/0/0 | 0/34/34 | 1 (constant) | yes |
| haiku | NayakRR_2021 | host_species | 0/0/0 | 34/34/34 | 1 (constant) | yes |
| haiku | NayakRR_2021 | sample_id | 0/0/0 | 34/34/34 | 34 | yes |
| haiku | NayakRR_2021 | treatment | 0/0/0 | 17/17/17 | 2 | yes |
| haiku | PasolliE_2019 | age_unit | 112/112/112 | 0/0/0 | 1 (constant) | yes |
| haiku | Heitz-BuschartA_2016 | sample_id | 0/0/0 | 53/53/53 | 53 | yes |
| haiku | Heitz-BuschartA_2016 | subject_id | 0/0/0 | 53/53/53 | 20 | yes |
| haiku | ContevilleLC_2019 | sample_id | 0/0/0 | 15/15/15 | 15 | yes |
| haiku | ContevilleLC_2019 | subject_id | 15/15/15 | 0/0/0 | 15 | yes |
| sonnet | Bengtsson-PalmeJ_2015 | age_group | 70/70/70 | 0/0/0 | 1 (constant) | yes |
| sonnet | Bengtsson-PalmeJ_2015 | age_max | 2/2/2 | 0/0/0 | 9 | yes |
| sonnet | Bengtsson-PalmeJ_2015 | age_min | 26/26/26 | 0/0/0 | 9 | yes |
| sonnet | Bengtsson-PalmeJ_2015 | age_unit | 70/70/70 | 0/0/0 | 1 (constant) | yes |
| sonnet | Bengtsson-PalmeJ_2015 | antibiotics_current_use | 70/70/70 | 0/70/0 | 1 (constant) | yes |
| sonnet | Bengtsson-PalmeJ_2015 | body_site | 70/70/70 | 0/70/0 | 1 (constant) | yes |
| sonnet | Bengtsson-PalmeJ_2015 | disease | 70/70/0 | 0/70/0 | 1 (constant) | no |
| sonnet | Bengtsson-PalmeJ_2015 | host_species | 70/0/70 | 0/0/0 | 1 (constant) | no |
| sonnet | Bengtsson-PalmeJ_2015 | sample_id | 0/0/0 | 70/70/70 | 70 | yes |
| sonnet | NayakRR_2021 | age_group | 32/32/32 | 0/0/0 | 2 | yes |
| sonnet | NayakRR_2021 | host_species | 0/34/0 | 34/34/34 | 1 (constant) | no |
| sonnet | NayakRR_2021 | sample_id | 0/0/0 | 34/34/34 | 34 | yes |
| sonnet | PasolliE_2019 | age_group | 110/110/110 | 0/0/0 | 3 | yes |
| sonnet | PasolliE_2019 | sequencing_platform | 0/112/112 | 112/0/0 | 1 (constant) | no |
| sonnet | Heitz-BuschartA_2016 | host_species | 0/0/0 | 53/53/53 | 1 (constant) | yes |
| sonnet | Heitz-BuschartA_2016 | pmid | 53/53/0 | 0/0/53 | 1 (constant) | no |
| sonnet | Heitz-BuschartA_2016 | sample_id | 0/0/0 | 53/53/53 | 53 | yes |
| sonnet | Heitz-BuschartA_2016 | subject_id | 0/0/0 | 53/53/53 | 20 | yes |
| sonnet | ContevilleLC_2019 | body_site | 0/0/0 | 15/15/15 | 1 (constant) | yes |
| sonnet | ContevilleLC_2019 | sample_id | 0/0/0 | 15/15/15 | 15 | yes |

- **haiku**: 345 correct cells gained, 363 lost to the code changes, 0 lost where the out_v3 repeats disagreed (model variance)
- **sonnet**: 327 correct cells gained, 450 lost to the code changes, 305 lost where the out_v3 repeats disagreed (model variance)
