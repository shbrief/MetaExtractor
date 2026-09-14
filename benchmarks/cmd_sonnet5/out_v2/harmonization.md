# Ontology harmonization (identity-matched cells)

Median [min–max] over repeats. `raw` and `exact` on the **same coded cells** (both reported, gold carries a curated ontology id). `any-hit` is supplementary.

Ratios are over runs with at least one coded cell (`runs coded`).

| field | model | TP cells | coded cells | runs coded | raw acc (coded) | exact code-set correct | any-hit (suppl.) | concept P | concept R | agree (TP, exact) | coded terms → curated codes | studies |
|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|---|---|
| disease | sonnet | 34 [34–146] | 0 [0–112] | 1/3 | 1.000 [1.000–1.000] | 1.000 [1.000–1.000] | 1.000 [1.000–1.000] | 1.000 [1.000–1.000] | 1.000 [1.000–1.000] | 1.000 [1.000–1.000] | Healthy → NCIT:C115935 | PasolliE_2019 |
| disease | haiku | 112 [112–127] | 112 [112–112] | 3/3 | 1.000 [1.000–1.000] | 1.000 [1.000–1.000] | 1.000 [1.000–1.000] | 1.000 [1.000–1.000] | 1.000 [1.000–1.000] | 1.000 [1.000–1.000] | Healthy → NCIT:C115935 | PasolliE_2019 |
| body_site | sonnet | 49 [34–216] | 0 [0–182] | 1/3 | 0.385 [0.385–0.385] | 1.000 [1.000–1.000] | 1.000 [1.000–1.000] | 1.000 [1.000–1.000] | 1.000 [1.000–1.000] | 1.000 [0.306–1.000] | Stool, feces → UBERON:0001988 | Bengtsson-PalmeJ_2015, PasolliE_2019 |
| body_site | haiku | 180 [180–214] | 165 [165–165] | 3/3 | 0.321 [0.321–0.321] | 1.000 [1.000–1.000] | 1.000 [1.000–1.000] | 1.000 [1.000–1.000] | 1.000 [1.000–1.000] | 0.917 [0.841–1.000] | Stool, feces → UBERON:0001988 | Heitz-BuschartA_2016, PasolliE_2019 |
| treatment | sonnet | 34 [34–34] | 0 [0–0] | 0/3 | – | – | – | – | – | 0.500 [0.500–0.500] | – → – | – |
| treatment | haiku | 0 [0–31] | 0 [0–31] | 1/3 | 0.000 [0.000–0.000] | 0.000 [0.000–0.000] | 0.000 [0.000–0.000] | 0.000 [0.000–0.000] | 0.000 [0.000–0.000] | 0.000 [0.000–0.000] | Insulin replacement therapy → NCIT:C29711, SCDO:0000067 | Heitz-BuschartA_2016 |
