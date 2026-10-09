# Aggregate — `/Users/sehyunoh/OmicsMLRepo/MetaExtractor/benchmarks/cmd_sonnet5/out_v5`

Content fields, micro-averaged; median [min–max] across repeats. Values are compared after harmonization: fields with a MetaHarmonizer crosswalk as ontology codes (against the curated ontology id where present), other fields as extracted. Precision = TPc/(TPc+TPw+FP), recall = TPc/(TPc+TPw+FN).

Harmonized fields (sonnet): body_site, disease, dna_extraction_kit, host_species, sequencing_platform, treatment.
Harmonized fields (haiku): body_site, disease, dna_extraction_kit, host_species, sequencing_platform, treatment.

## Score all curated

| model | precision | recall | F1 | TPc | TPw | FP | FN |
|---|--:|--:|--:|--:|--:|--:|--:|
| sonnet | 0.724 [0.697–0.747] | 0.099 [0.085–0.106] | 0.175 [0.152–0.186] | 1867 [1604–1993] | 697 [676–712] | 0 [0–0] | 16211 [16121–16489] |
| haiku | 0.686 [0.657–0.704] | 0.097 [0.083–0.102] | 0.170 [0.147–0.178] | 1829 [1553–1911] | 812 [803–839] | 0 [0–0] | 16122 [16076–16425] |

## Score matched

| model | precision | recall | F1 | TPc | TPw | FP | FN |
|---|--:|--:|--:|--:|--:|--:|--:|
| sonnet | 0.724 [0.697–0.747] | 0.317 [0.273–0.339] | 0.441 [0.392–0.466] | 1867 [1604–1993] | 697 [676–712] | 0 [0–0] | 3305 [3215–3583] |
| haiku | 0.686 [0.657–0.704] | 0.311 [0.268–0.327] | 0.428 [0.380–0.447] | 1829 [1553–1911] | 812 [803–839] | 0 [0–0] | 3216 [3130–3439] |

## Sensitivity: all curated, successful extractions only

| model | precision | recall | F1 | TPc | TPw | FP | FN |
|---|--:|--:|--:|--:|--:|--:|--:|
| sonnet | 0.724 [0.697–0.747] | 0.099 [0.085–0.106] | 0.175 [0.152–0.186] | 1867 [1604–1993] | 697 [676–712] | 0 [0–0] | 16211 [16121–16489] |
| haiku | 0.686 [0.657–0.704] | 0.097 [0.083–0.102] | 0.170 [0.147–0.178] | 1829 [1553–1911] | 812 [803–839] | 0 [0–0] | 16122 [16076–16425] |

Paired all-curated F1 difference (sonnet − haiku): +0.006, 95% study-cluster bootstrap CI [-0.007, +0.024] (10 studies, B=2000).


## Harmonized fields

| field | model | score | precision | recall | F1 | TPc | TPw | FP | FN |
|---|---|---|--:|--:|--:|--:|--:|--:|--:|
| body_site | sonnet | all curated | 1.000 [1.000–1.000] | 0.179 [0.093–0.223] | 0.304 [0.170–0.364] | 216 [112–269] | 0 [0–0] | 0 [0–0] | 991 [938–1095] |
| body_site | sonnet | matched | 1.000 [1.000–1.000] | 0.647 [0.335–0.805] | 0.785 [0.502–0.892] | 216 [112–269] | 0 [0–0] | 0 [0–0] | 118 [65–222] |
| disease | sonnet | all curated | 1.000 [0.884–1.000] | 0.134 [0.134–0.182] | 0.237 [0.237–0.302] | 162 [162–220] | 0 [0–29] | 0 [0–0] | 1045 [958–1045] |
| disease | sonnet | matched | 1.000 [0.884–1.000] | 0.485 [0.485–0.659] | 0.653 [0.653–0.755] | 162 [162–220] | 0 [0–29] | 0 [0–0] | 172 [85–172] |
| dna_extraction_kit | sonnet | all curated | 0.258 [0.201–0.258] | 0.106 [0.083–0.106] | 0.150 [0.117–0.150] | 68 [53–68] | 196 [196–211] | 0 [0–0] | 378 [378–378] |
| dna_extraction_kit | sonnet | matched | 0.258 [0.201–0.258] | 0.204 [0.159–0.204] | 0.227 [0.177–0.227] | 68 [53–68] | 196 [196–211] | 0 [0–0] | 70 [70–70] |
| host_species | sonnet | all curated | 1.000 [1.000–1.000] | 0.277 [0.277–0.277] | 0.433 [0.433–0.433] | 334 [334–334] | 0 [0–0] | 0 [0–0] | 873 [873–873] |
| host_species | sonnet | matched | 1.000 [1.000–1.000] | 1.000 [1.000–1.000] | 1.000 [1.000–1.000] | 334 [334–334] | 0 [0–0] | 0 [0–0] | 0 [0–0] |
| sequencing_platform | sonnet | all curated | 1.000 [1.000–1.000] | 0.277 [0.277–0.277] | 0.433 [0.433–0.433] | 334 [334–334] | 0 [0–0] | 0 [0–0] | 873 [873–873] |
| sequencing_platform | sonnet | matched | 1.000 [1.000–1.000] | 1.000 [1.000–1.000] | 1.000 [1.000–1.000] | 334 [334–334] | 0 [0–0] | 0 [0–0] | 0 [0–0] |
| treatment | sonnet | all curated | – | 0.000 [0.000–0.000] | – | 0 [0–0] | 0 [0–0] | 0 [0–0] | 445 [445–445] |
| treatment | sonnet | matched | – | 0.000 [0.000–0.000] | – | 0 [0–0] | 0 [0–0] | 0 [0–0] | 65 [65–65] |
| body_site | haiku | all curated | 1.000 [1.000–1.000] | 0.162 [0.089–0.163] | 0.278 [0.164–0.281] | 195 [108–197] | 0 [0–0] | 0 [0–0] | 1012 [1010–1099] |
| body_site | haiku | matched | 1.000 [1.000–1.000] | 0.587 [0.327–0.590] | 0.740 [0.493–0.742] | 195 [108–197] | 0 [0–0] | 0 [0–0] | 137 [137–222] |
| disease | haiku | all curated | 1.000 [1.000–1.000] | 0.134 [0.131–0.203] | 0.237 [0.232–0.337] | 162 [158–245] | 0 [0–0] | 0 [0–0] | 1045 [962–1049] |
| disease | haiku | matched | 1.000 [1.000–1.000] | 0.485 [0.479–0.738] | 0.653 [0.648–0.849] | 162 [158–245] | 0 [0–0] | 0 [0–0] | 172 [87–172] |
| dna_extraction_kit | haiku | all curated | 0.000 [0.000–0.057] | 0.000 [0.000–0.023] | 0.033 [0.033–0.033] | 0 [0–15] | 260 [247–264] | 0 [0–0] | 380 [378–382] |
| dna_extraction_kit | haiku | matched | 0.000 [0.000–0.057] | 0.000 [0.000–0.045] | 0.051 [0.051–0.051] | 0 [0–15] | 260 [247–264] | 0 [0–0] | 70 [70–70] |
| host_species | haiku | all curated | 1.000 [1.000–1.000] | 0.275 [0.273–0.277] | 0.431 [0.429–0.433] | 332 [330–334] | 0 [0–0] | 0 [0–0] | 875 [873–877] |
| host_species | haiku | matched | 1.000 [1.000–1.000] | 1.000 [1.000–1.000] | 1.000 [1.000–1.000] | 332 [330–334] | 0 [0–0] | 0 [0–0] | 0 [0–0] |
| sequencing_platform | haiku | all curated | 1.000 [1.000–1.000] | 0.275 [0.273–0.277] | 0.431 [0.429–0.433] | 332 [330–334] | 0 [0–0] | 0 [0–0] | 875 [873–877] |
| sequencing_platform | haiku | matched | 1.000 [1.000–1.000] | 1.000 [1.000–1.000] | 1.000 [1.000–1.000] | 332 [330–334] | 0 [0–0] | 0 [0–0] | 0 [0–0] |
| treatment | haiku | all curated | – | 0.000 [0.000–0.000] | – | 0 [0–0] | 0 [0–0] | 0 [0–0] | 445 [445–445] |
| treatment | haiku | matched | – | 0.000 [0.000–0.000] | – | 0 [0–0] | 0 [0–0] | 0 [0–0] | 65 [65–65] |

## sonnet: per study × repeat (content cells)

| study | gold n | repeat | ext n | key | matched | unmatched | pooled | ambiguous | extra | TPc | TPw | FN (all curated) | FN (matched) | FP |
|---|--:|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Bengtsson-PalmeJ_2015 | 70 | sonnet_r1 | 70 | ncbi_accession | 70 | 0 | 0 | 0 | 0 | 350 | 70 | 770 | 770 | 0 |
| Bengtsson-PalmeJ_2015 | 70 | sonnet_r2 | 70 | ncbi_accession | 70 | 0 | 0 | 0 | 0 | 350 | 70 | 770 | 770 | 0 |
| Bengtsson-PalmeJ_2015 | 70 | sonnet_r3 | 70 | ncbi_accession | 70 | 0 | 0 | 0 | 0 | 140 | 70 | 980 | 980 | 0 |
| TettAJ_2019_b | 162 | sonnet_r1 | 50 | sample_id | 50 | 112 | 0 | 0 | 0 | 180 | 267 | 2189 | 400 | 0 |
| TettAJ_2019_b | 162 | sonnet_r2 | 50 | sample_id | 50 | 112 | 0 | 0 | 0 | 180 | 217 | 2239 | 450 | 0 |
| TettAJ_2019_b | 162 | sonnet_r3 | 50 | sample_id | 50 | 112 | 0 | 0 | 0 | 180 | 267 | 2189 | 400 | 0 |
| LiJ_2017 | 196 | sonnet_r1 | 6 | – | 0 | 196 | 0 | 0 | 6 | 0 | 0 | 2744 | 0 | 0 |
| LiJ_2017 | 196 | sonnet_r2 | 6 | – | 0 | 196 | 0 | 0 | 6 | 0 | 0 | 2744 | 0 | 0 |
| LiJ_2017 | 196 | sonnet_r3 | 6 | – | 0 | 196 | 0 | 0 | 6 | 0 | 0 | 2744 | 0 | 0 |
| NayakRR_2021 | 34 | sonnet_r1 | 434 | ncbi_accession | 34 | 0 | 0 | 0 | 400 | 102 | 68 | 204 | 204 | 0 |
| NayakRR_2021 | 34 | sonnet_r2 | 434 | ncbi_accession | 34 | 0 | 0 | 0 | 400 | 136 | 68 | 170 | 170 | 0 |
| NayakRR_2021 | 34 | sonnet_r3 | 434 | ncbi_accession | 34 | 0 | 0 | 0 | 400 | 34 | 68 | 272 | 272 | 0 |
| PasolliE_2019 | 112 | sonnet_r1 | 112 | sample_id | 112 | 0 | 0 | 0 | 0 | 1008 | 224 | 1008 | 1008 | 0 |
| PasolliE_2019 | 112 | sonnet_r2 | 112 | sample_id | 112 | 0 | 0 | 0 | 0 | 1008 | 224 | 1008 | 1008 | 0 |
| PasolliE_2019 | 112 | sonnet_r3 | 112 | sample_id | 112 | 0 | 0 | 0 | 0 | 1008 | 224 | 1008 | 1008 | 0 |
| Heitz-BuschartA_2016 | 53 | sonnet_r1 | 221 | ncbi_accession | 53 | 0 | 0 | 0 | 168 | 212 | 53 | 833 | 833 | 0 |
| Heitz-BuschartA_2016 | 53 | sonnet_r2 | 221 | ncbi_accession | 53 | 0 | 0 | 0 | 168 | 289 | 82 | 727 | 727 | 0 |
| Heitz-BuschartA_2016 | 53 | sonnet_r3 | 221 | ncbi_accession | 53 | 0 | 0 | 0 | 168 | 212 | 53 | 833 | 833 | 0 |
| FanY_2023 | 147 | sonnet_r1 | 100 | – | 0 | 147 | 0 | 0 | 100 | 0 | 0 | 1617 | 0 | 0 |
| FanY_2023 | 147 | sonnet_r2 | 100 | – | 0 | 147 | 0 | 0 | 100 | 0 | 0 | 1617 | 0 | 0 |
| FanY_2023 | 147 | sonnet_r3 | 100 | – | 0 | 147 | 0 | 0 | 100 | 0 | 0 | 1617 | 0 | 0 |
| QinJ_2012 | 363 | sonnet_r1 | 0 | – | 0 | 363 | 0 | 0 | 0 | 0 | 0 | 6041 | 0 | 0 |
| QinJ_2012 | 363 | sonnet_r2 | 0 | – | 0 | 363 | 0 | 0 | 0 | 0 | 0 | 6041 | 0 | 0 |
| QinJ_2012 | 363 | sonnet_r3 | 0 | – | 0 | 363 | 0 | 0 | 0 | 0 | 0 | 6041 | 0 | 0 |
| ContevilleLC_2019 | 15 | sonnet_r1 | 15 | ncbi_accession | 15 | 0 | 0 | 0 | 0 | 15 | 30 | 90 | 90 | 0 |
| ContevilleLC_2019 | 15 | sonnet_r2 | 15 | ncbi_accession | 15 | 0 | 0 | 0 | 0 | 30 | 15 | 90 | 90 | 0 |
| ContevilleLC_2019 | 15 | sonnet_r3 | 15 | ncbi_accession | 15 | 0 | 0 | 0 | 0 | 30 | 15 | 90 | 90 | 0 |
| LiSS_2016 | 55 | sonnet_r1 | 0 | – | 0 | 55 | 0 | 0 | 0 | 0 | 0 | 715 | 0 | 0 |
| LiSS_2016 | 55 | sonnet_r2 | 0 | – | 0 | 55 | 0 | 0 | 0 | 0 | 0 | 715 | 0 | 0 |
| LiSS_2016 | 55 | sonnet_r3 | 0 | – | 0 | 55 | 0 | 0 | 0 | 0 | 0 | 715 | 0 | 0 |

### sonnet: age bounds by provenance (all curated, pooled over repeats)

| field:source | TPc | TPw | FN | FP | precision |
|---|--:|--:|--:|--:|--:|
| age_max:age_rule | 414 | 69 | 0 | 0 | 0.857 |
| age_max:other | 0 | 0 | 2550 | 0 | – |
| age_min:age_rule | 414 | 69 | 0 | 0 | 0.857 |
| age_min:other | 0 | 0 | 2550 | 0 | – |

## haiku: per study × repeat (content cells)

| study | gold n | repeat | ext n | key | matched | unmatched | pooled | ambiguous | extra | TPc | TPw | FN (all curated) | FN (matched) | FP |
|---|--:|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Bengtsson-PalmeJ_2015 | 70 | haiku_r1 | 70 | ncbi_accession | 70 | 0 | 0 | 0 | 0 | 350 | 70 | 770 | 770 | 0 |
| Bengtsson-PalmeJ_2015 | 70 | haiku_r2 | 70 | ncbi_accession | 70 | 0 | 0 | 0 | 0 | 140 | 70 | 980 | 980 | 0 |
| Bengtsson-PalmeJ_2015 | 70 | haiku_r3 | 70 | ncbi_accession | 70 | 0 | 0 | 0 | 0 | 420 | 70 | 700 | 700 | 0 |
| TettAJ_2019_b | 162 | haiku_r1 | 50 | sample_id | 50 | 112 | 0 | 0 | 0 | 180 | 267 | 2189 | 400 | 0 |
| TettAJ_2019_b | 162 | haiku_r2 | 50 | sample_id | 50 | 112 | 0 | 0 | 0 | 180 | 267 | 2189 | 400 | 0 |
| TettAJ_2019_b | 162 | haiku_r3 | 50 | sample_id | 50 | 112 | 0 | 0 | 0 | 180 | 267 | 2189 | 400 | 0 |
| LiJ_2017 | 196 | haiku_r1 | 6 | – | 0 | 196 | 0 | 0 | 6 | 0 | 0 | 2744 | 0 | 0 |
| LiJ_2017 | 196 | haiku_r2 | 6 | – | 0 | 196 | 0 | 0 | 6 | 0 | 0 | 2744 | 0 | 0 |
| LiJ_2017 | 196 | haiku_r3 | 6 | – | 0 | 196 | 0 | 0 | 6 | 0 | 0 | 2744 | 0 | 0 |
| NayakRR_2021 | 34 | haiku_r1 | 434 | ncbi_accession | 34 | 0 | 0 | 0 | 400 | 34 | 68 | 272 | 272 | 0 |
| NayakRR_2021 | 34 | haiku_r2 | 434 | ncbi_accession | 34 | 0 | 0 | 0 | 400 | 34 | 68 | 272 | 272 | 0 |
| NayakRR_2021 | 34 | haiku_r3 | 434 | ncbi_accession | 34 | 0 | 0 | 0 | 400 | 34 | 68 | 272 | 272 | 0 |
| PasolliE_2019 | 112 | haiku_r1 | 112 | sample_id | 112 | 0 | 0 | 0 | 0 | 1008 | 336 | 896 | 896 | 0 |
| PasolliE_2019 | 112 | haiku_r2 | 108 | sample_id | 108 | 4 | 0 | 0 | 0 | 972 | 324 | 944 | 864 | 0 |
| PasolliE_2019 | 112 | haiku_r3 | 110 | sample_id | 110 | 2 | 0 | 0 | 0 | 990 | 330 | 920 | 880 | 0 |
| Heitz-BuschartA_2016 | 53 | haiku_r1 | 221 | ncbi_accession | 53 | 0 | 0 | 0 | 168 | 212 | 53 | 833 | 833 | 0 |
| Heitz-BuschartA_2016 | 53 | haiku_r2 | 221 | ncbi_accession | 53 | 0 | 0 | 0 | 168 | 212 | 53 | 833 | 833 | 0 |
| Heitz-BuschartA_2016 | 53 | haiku_r3 | 221 | ncbi_accession | 53 | 0 | 0 | 0 | 168 | 212 | 53 | 833 | 833 | 0 |
| FanY_2023 | 147 | haiku_r1 | 510 | – | 0 | 147 | 0 | 0 | 510 | 0 | 0 | 1617 | 0 | 0 |
| FanY_2023 | 147 | haiku_r2 | 510 | – | 0 | 147 | 0 | 0 | 510 | 0 | 0 | 1617 | 0 | 0 |
| FanY_2023 | 147 | haiku_r3 | 510 | – | 0 | 147 | 0 | 0 | 510 | 0 | 0 | 1617 | 0 | 0 |
| QinJ_2012 | 363 | haiku_r1 | 0 | – | 0 | 363 | 0 | 0 | 0 | 0 | 0 | 6041 | 0 | 0 |
| QinJ_2012 | 363 | haiku_r2 | 0 | – | 0 | 363 | 0 | 0 | 0 | 0 | 0 | 6041 | 0 | 0 |
| QinJ_2012 | 363 | haiku_r3 | 0 | – | 0 | 363 | 0 | 0 | 0 | 0 | 0 | 6041 | 0 | 0 |
| ContevilleLC_2019 | 15 | haiku_r1 | 15 | ncbi_accession | 15 | 0 | 0 | 0 | 0 | 45 | 45 | 45 | 45 | 0 |
| ContevilleLC_2019 | 15 | haiku_r2 | 15 | ncbi_accession | 15 | 0 | 0 | 0 | 0 | 15 | 30 | 90 | 90 | 0 |
| ContevilleLC_2019 | 15 | haiku_r3 | 15 | ncbi_accession | 15 | 0 | 0 | 0 | 0 | 75 | 15 | 45 | 45 | 0 |
| LiSS_2016 | 55 | haiku_r1 | 0 | – | 0 | 55 | 0 | 0 | 0 | 0 | 0 | 715 | 0 | 0 |
| LiSS_2016 | 55 | haiku_r2 | 0 | – | 0 | 55 | 0 | 0 | 0 | 0 | 0 | 715 | 0 | 0 |
| LiSS_2016 | 55 | haiku_r3 | 0 | – | 0 | 55 | 0 | 0 | 0 | 0 | 0 | 715 | 0 | 0 |

### haiku: age bounds by provenance (all curated, pooled over repeats)

| field:source | TPc | TPw | FN | FP | precision |
|---|--:|--:|--:|--:|--:|
| age_max:age_rule | 408 | 69 | 0 | 0 | 0.855 |
| age_max:other | 0 | 0 | 2556 | 0 | – |
| age_min:age_rule | 408 | 69 | 0 | 0 | 0.855 |
| age_min:other | 0 | 0 | 2556 | 0 | – |

## Attempt ledger

- tasks 60, attempts 63, failed attempts 3, initial failures 3, final successes 60
- window 2026-10-09T00:09:22+00:00 → 2026-10-09T01:32:23+00:00 (UTC); commits ['097d8a1b9185a7efb305f61ba42d4ff59693d13a']; dirty tree: False
  - sonnet/3/TettAJ_2019_b: fail_rc1
  - sonnet/2/FanY_2023: fail_rc1
  - haiku/3/TettAJ_2019_b: fail_rc1
- haiku: estimated cost over all 31 attempts US$3.13 (228 calls), of which failed attempts US$0.00; attempts without metadata 1
- sonnet: estimated cost over all 32 attempts US$12.91 (261 calls), of which failed attempts US$0.00; attempts without metadata 2
