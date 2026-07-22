# Multi-seed benchmark — enumeration stability & headline distributions

Each study run **3×** per model on the **fixed** fetcher (Europe PMC fallback is strictly additive: S3 supplementary recovered regardless of body source). Spread below is genuine LLM/pipeline run-to-run variance.


## sonnet

Headline content metrics per repeat (median [min–max] across 3 run(s)):

- **P**: 0.999 [0.993–0.999]
- **R**: 0.590 [0.579–0.605]
- **F1**: 0.740 [0.733–0.754]
- **vacc**: 0.679 [0.667–0.692]
- **fp**: – [–––]

### Per-study sample enumeration across repeats

| study | gold | run1 | run2 | run3 | median | range | fetch src |
|---|--:|--:|--:|--:|--:|--:|---|
| Bengtsson-PalmeJ_2015 | 70 | 0 | 0 | 0 | 0 | 0–0 | pmc_ |
| TettAJ_2019_b | 44 | 50 | 50 | 50 | 50 | 50–50 | pmc_ |
| LiJ_2017 | 196 | 6 | 6 | 6 | 6 | 6–6 | pmc_ |
| NayakRR_2021 | 34 | 0 | 0 | 0 | 0 | 0–0 | pmc_ |
| PasolliE_2019 | 112 | 112 | 112 | 112 | 112 | 112–112 | pmc_ |
| Heitz-BuschartA_2016 | 53 | 0 | 0 | 0 | 0 | 0–0 | pubm |
| FanY_2023 | 147 | 319 | 510 | 510 | 510 | 319–510 | pmc_ |
| QinJ_2012 | 363 | 0 | 0 | 0 | 0 | 0–0 | pubm |
| ContevilleLC_2019 | 15 | 0 | 0 | 0 | 0 | 0–0 | pmc_ |
| LiSS_2016 | 55 | 0 | 0 | 0 | 0 | 0–0 | pubm |

## haiku

Headline content metrics per repeat (median [min–max] across 3 run(s)):

- **P**: 0.887 [0.885–0.888]
- **R**: 0.619 [0.618–0.627]
- **F1**: 0.730 [0.727–0.735]
- **vacc**: 0.538 [0.515–0.553]
- **fp**: – [–––]

### Per-study sample enumeration across repeats

| study | gold | run1 | run2 | run3 | median | range | fetch src |
|---|--:|--:|--:|--:|--:|--:|---|
| Bengtsson-PalmeJ_2015 | 70 | 0 | 0 | 0 | 0 | 0–0 | pmc_,pubm |
| TettAJ_2019_b | 44 | 50 | 50 | 50 | 50 | 50–50 | pmc_ |
| LiJ_2017 | 196 | 1448 | 1448 | 1448 | 1448 | 1448–1448 | pmc_ |
| NayakRR_2021 | 34 | 6 | 0 | 9 | 6 | 0–9 | pmc_ |
| PasolliE_2019 | 112 | 112 | 112 | 112 | 112 | 112–112 | pmc_ |
| Heitz-BuschartA_2016 | 53 | 0 | 0 | 0 | 0 | 0–0 | pubm |
| FanY_2023 | 147 | 319 | 319 | 319 | 319 | 319–319 | pmc_ |
| QinJ_2012 | 363 | 0 | 0 | 0 | 0 | 0–0 | pubm |
| ContevilleLC_2019 | 15 | 1 | 0 | 15 | 1 | 0–15 | pmc_ |
| LiSS_2016 | 55 | 0 | 0 | 0 | 0 | 0–0 | pubm |