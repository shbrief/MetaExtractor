# Multi-seed benchmark — enumeration stability & headline distributions

Each study run **3×** per model on the **fixed** fetcher (Europe PMC fallback is strictly additive: S3 supplementary recovered regardless of body source). Spread below is genuine LLM/pipeline run-to-run variance.


## sonnet

Headline content metrics per repeat (median [min–max] across 3 run(s)):

- **P**: 0.990 [0.960–0.993]
- **R**: 0.591 [0.569–0.593]
- **F1**: 0.741 [0.715–0.741]
- **vacc**: 0.609 [0.593–0.623]
- **fp**: – [–––]
- **R_cov (coverage-aware recall; un/under-enumerated gold rows counted as FN)**: 0.286 [0.275–0.287]

### Per-study sample enumeration across repeats

| study | gold | run1 | run2 | run3 | median | range | fetch src |
|---|--:|--:|--:|--:|--:|--:|---|
| Bengtsson-PalmeJ_2015 | 70 | 70 | 70 | 70 | 70 | 70–70 | euro |
| TettAJ_2019_b | 44 | 50 | 50 | 50 | 50 | 50–50 | pmc_ |
| LiJ_2017 | 196 | 6 | 6 | 6 | 6 | 6–6 | pmc_ |
| NayakRR_2021 | 34 | 434 | 434 | 434 | 434 | 434–434 | pmc_ |
| PasolliE_2019 | 112 | 112 | 112 | 112 | 112 | 112–112 | pmc_ |
| Heitz-BuschartA_2016 | 53 | 221 | 221 | 221 | 221 | 221–221 | unpa |
| FanY_2023 | 147 | 319 | 510 | 510 | 510 | 319–510 | pmc_ |
| QinJ_2012 | 363 | 0 | 0 | 0 | 0 | 0–0 | pubm |
| ContevilleLC_2019 | 15 | 15 | 15 | 15 | 15 | 15–15 | pmc_ |
| LiSS_2016 | 55 | 430 | 430 | 430 | 430 | 430–430 | unpa |

## haiku

Headline content metrics per repeat (median [min–max] across 3 run(s)):

- **P**: 0.901 [0.898–0.905]
- **R**: 0.660 [0.640–0.688]
- **F1**: 0.762 [0.748–0.782]
- **vacc**: 0.512 [0.480–0.527]
- **fp**: – [–––]
- **R_cov (coverage-aware recall; un/under-enumerated gold rows counted as FN)**: 0.423 [0.411–0.441]

### Per-study sample enumeration across repeats

| study | gold | run1 | run2 | run3 | median | range | fetch src |
|---|--:|--:|--:|--:|--:|--:|---|
| Bengtsson-PalmeJ_2015 | 70 | 70 | 70 | 70 | 70 | 70–70 | euro |
| TettAJ_2019_b | 44 | 50 | 50 | 50 | 50 | 50–50 | pmc_ |
| LiJ_2017 | 196 | 1448 | 1448 | 1448 | 1448 | 1448–1448 | pmc_ |
| NayakRR_2021 | 34 | 434 | 434 | 434 | 434 | 434–434 | pmc_ |
| PasolliE_2019 | 112 | 112 | 112 | 112 | 112 | 112–112 | pmc_ |
| Heitz-BuschartA_2016 | 53 | 221 | 221 | 221 | 221 | 221–221 | unpa |
| FanY_2023 | 147 | 319 | 319 | 319 | 319 | 319–319 | pmc_ |
| QinJ_2012 | 363 | 0 | 0 | 0 | 0 | 0–0 | pubm |
| ContevilleLC_2019 | 15 | 15 | 15 | 15 | 15 | 15–15 | pmc_ |
| LiSS_2016 | 55 | 430 | 430 | 430 | 430 | 430–430 | unpa |