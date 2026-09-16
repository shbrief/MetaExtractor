# Aggregate — `/Users/sehyunoh/OmicsMLRepo/MetaExtractor/benchmarks/cmd_sonnet5/dev_analysis/devcheck_haiku45`

Content fields, micro-averaged; median [min–max] across repeats. Values are compared after harmonization: fields with a MetaHarmonizer crosswalk as ontology codes (against the curated ontology id where present), other fields as extracted. Precision = TPc/(TPc+TPw+FP), recall = TPc/(TPc+TPw+FN).

Harmonized fields (haiku): body_site, disease, treatment.

## Score all curated

| model | precision | recall | F1 | TPc | TPw | FP | FN |
|---|--:|--:|--:|--:|--:|--:|--:|
| sonnet | – | – | – | – | – | – | – |
| haiku | 0.656 [0.656–0.656] | 0.084 [0.084–0.084] | 0.150 [0.150–0.150] | 1422 [1422–1422] | 746 [746–746] | 0 [0–0] | 14687 [14687–14687] |

## Score matched

| model | precision | recall | F1 | TPc | TPw | FP | FN |
|---|--:|--:|--:|--:|--:|--:|--:|
| sonnet | – | – | – | – | – | – | – |
| haiku | 0.656 [0.656–0.656] | 0.282 [0.282–0.282] | 0.395 [0.395–0.395] | 1422 [1422–1422] | 746 [746–746] | 0 [0–0] | 2869 [2869–2869] |

## Sensitivity: all curated, successful extractions only

| model | precision | recall | F1 | TPc | TPw | FP | FN |
|---|--:|--:|--:|--:|--:|--:|--:|
| sonnet | – | – | – | – | – | – | – |
| haiku | 0.656 [0.656–0.656] | 0.084 [0.084–0.084] | 0.150 [0.150–0.150] | 1422 [1422–1422] | 746 [746–746] | 0 [0–0] | 14687 [14687–14687] |

## Harmonized fields

| field | model | score | precision | recall | F1 | TPc | TPw | FP | FN |
|---|---|---|--:|--:|--:|--:|--:|--:|--:|
| body_site | haiku | all curated | 1.000 [1.000–1.000] | 0.230 [0.230–0.230] | 0.373 [0.373–0.373] | 250 [250–250] | 0 [0–0] | 0 [0–0] | 839 [839–839] |
| body_site | haiku | matched | 1.000 [1.000–1.000] | 0.880 [0.880–0.880] | 0.936 [0.936–0.936] | 250 [250–250] | 0 [0–0] | 0 [0–0] | 34 [34–34] |
| disease | haiku | all curated | 1.000 [1.000–1.000] | 0.103 [0.103–0.103] | 0.187 [0.187–0.187] | 112 [112–112] | 0 [0–0] | 0 [0–0] | 977 [977–977] |
| disease | haiku | matched | 1.000 [1.000–1.000] | 0.394 [0.394–0.394] | 0.566 [0.566–0.566] | 112 [112–112] | 0 [0–0] | 0 [0–0] | 172 [172–172] |
| treatment | haiku | all curated | 0.500 [0.500–0.500] | 0.038 [0.038–0.038] | 0.071 [0.071–0.071] | 17 [17–17] | 17 [17–17] | 0 [0–0] | 411 [411–411] |
| treatment | haiku | matched | 0.500 [0.500–0.500] | 0.262 [0.262–0.262] | 0.343 [0.343–0.343] | 17 [17–17] | 17 [17–17] | 0 [0–0] | 31 [31–31] |

## sonnet: per study × repeat (content cells)

| study | gold n | repeat | ext n | key | matched | unmatched | pooled | ambiguous | extra | TPc | TPw | FN (all curated) | FN (matched) | FP |
|---|--:|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|

## haiku: per study × repeat (content cells)

| study | gold n | repeat | ext n | key | matched | unmatched | pooled | ambiguous | extra | TPc | TPw | FN (all curated) | FN (matched) | FP |
|---|--:|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|
| Bengtsson-PalmeJ_2015 | 70 | haiku_r1 | 70 | ncbi_accession | 70 | 0 | 0 | 0 | 0 | 140 | 140 | 910 | 910 | 0 |
| TettAJ_2019_b | 44 | haiku_r1 | 50 | – | 0 | 44 | 0 | 0 | 50 | 0 | 0 | 701 | 0 | 0 |
| LiJ_2017 | 196 | haiku_r1 | 6 | – | 0 | 196 | 0 | 0 | 6 | 0 | 0 | 2744 | 0 | 0 |
| NayakRR_2021 | 34 | haiku_r1 | 434 | ncbi_accession | 34 | 0 | 0 | 0 | 400 | 17 | 119 | 238 | 238 | 0 |
| PasolliE_2019 | 112 | haiku_r1 | 112 | sample_id | 112 | 0 | 0 | 0 | 0 | 1008 | 336 | 896 | 896 | 0 |
| Heitz-BuschartA_2016 | 53 | haiku_r1 | 221 | ncbi_accession | 53 | 0 | 0 | 0 | 168 | 212 | 106 | 780 | 780 | 0 |
| FanY_2023 | 147 | haiku_r1 | 510 | – | 0 | 147 | 0 | 0 | 510 | 0 | 0 | 1617 | 0 | 0 |
| QinJ_2012 | 363 | haiku_r1 | 0 | – | 0 | 363 | 0 | 0 | 0 | 0 | 0 | 6041 | 0 | 0 |
| ContevilleLC_2019 | 15 | haiku_r1 | 15 | ncbi_accession | 15 | 0 | 0 | 0 | 0 | 45 | 45 | 45 | 45 | 0 |
| LiSS_2016 | 55 | haiku_r1 | 0 | – | 0 | 55 | 0 | 0 | 0 | 0 | 0 | 715 | 0 | 0 |

### haiku: age bounds by provenance (all curated, pooled over repeats)

| field:source | TPc | TPw | FN | FP | precision |
|---|--:|--:|--:|--:|--:|
| age_max:age_rule | 112 | 0 | 0 | 0 | 1.000 |
| age_max:other | 0 | 0 | 781 | 0 | – |
| age_min:age_rule | 112 | 0 | 0 | 0 | 1.000 |
| age_min:other | 0 | 0 | 781 | 0 | – |

## Attempt ledger

- tasks 10, attempts 10, failed attempts 0, initial failures 0, final successes 10
- window 2026-09-16T02:31:41+00:00 → 2026-09-16T02:35:04+00:00 (UTC); commits ['852de78eaa5a550637811ec351443f9ca668ff06']; dirty tree: False
- haiku: estimated cost over all 10 attempts US$1.04 (76 calls), of which failed attempts US$0.00; attempts without metadata 0
