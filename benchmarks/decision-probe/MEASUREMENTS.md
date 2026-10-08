## `out_v4`

### Probe A — the structure-plan decision

- tables with a label (a plan was requested): **46**
- the model's plan was non-trivial, so the call was warranted: **26**
- the model's plan was `header_rows=[0]`, no melt — structurally the default parse, so the call bought nothing: **11**
- repeats disagreed on the same table: **9**
- **precision = 0.565** (26/46)

Recall is not measurable here: a table the detector read as is was never shown to a model, so nothing says whether a plan was needed. Measuring it requires a paid run that plans every table.

By the rule that fired:

| detector reason | plan non-trivial | plan trivial | disagreed |
|---|--:|--:|--:|
| blank cells inside the header span (stacked or | 9 | 7 | 7 |
| repeated column groups ('d'/'r') | 0 | 1 | 0 |
| repeated column groups ('d1'/'d2') | 0 | 2 | 0 |
| repeated column groups ('h2'/'c') | 1 | 0 | 0 |
| row 0 has fewer than two labels | 16 | 0 | 1 |
| row 1 looks like a second header row | 0 | 1 | 1 |

### Probe B — project resolution

- studies probed: **10**
- resolved by a confident rule: **6**
- of those, the choice was a **contested tie**: **2**

| study | rule | contested | top score | margin | projects |
|---|---|:-:|--:|--:|---|
| Bengtsson-PalmeJ_2015 | `bioproject_in_context` |  | 4 |  | PRJEB7369 |
| TettAJ_2019_b | `bioproject_in_context` | yes | 5 |  | PRJNA504891, PRJNA529124, PRJNA529400, PRJEB31971 |
| LiJ_2017 | `abstain_nothing_resolvable` |  |  |  | — |
| NayakRR_2021 | `bioproject_in_context` |  | 5 |  | PRJNA656577 |
| PasolliE_2019 | `bioproject_in_context` | yes | 6 |  | PRJNA485056, PRJNA504891 |
| Heitz-BuschartA_2016 | `bioproject_in_context` |  | 3 |  | PRJNA289586 |
| FanY_2023 | `abstain_nothing_resolvable` |  |  |  | — |
| QinJ_2012 | `abstain_nothing_resolvable` |  |  |  | — |
| ContevilleLC_2019 | `bioproject_in_context` |  | 3 |  | PRJNA527208 |
| LiSS_2016 | `abstain_nothing_resolvable` |  |  |  | — |

## `out_v3`

### Probe A — the structure-plan decision

- tables with a label (a plan was requested): **101**
- the model's plan was non-trivial, so the call was warranted: **34**
- the model's plan was `header_rows=[0]`, no melt — structurally the default parse, so the call bought nothing: **5**
- repeats disagreed on the same table: **9**
- **precision = 0.708** (34/48)

Recall is not measurable here: a table the detector read as is was never shown to a model, so nothing says whether a plan was needed. Measuring it requires a paid run that plans every table.

By the rule that fired:

| detector reason | plan non-trivial | plan trivial | disagreed |
|---|--:|--:|--:|
| blank cells inside the header span (stacked or | 14 | 2 | 7 |
| repeated column groups ('d'/'r') | 1 | 0 | 0 |
| repeated column groups ('d1'/'d2') | 0 | 2 | 0 |
| repeated column groups ('h2'/'c') | 1 | 0 | 0 |
| row 0 has fewer than two labels | 18 | 0 | 1 |
| row 1 looks like a second header row | 0 | 1 | 1 |

### Probe B — project resolution

- studies probed: **10**
- resolved by a confident rule: **6**
- of those, the choice was a **contested tie**: **2**

| study | rule | contested | top score | margin | projects |
|---|---|:-:|--:|--:|---|
| Bengtsson-PalmeJ_2015 | `bioproject_in_context` |  | 4 |  | PRJEB7369 |
| TettAJ_2019_b | `bioproject_in_context` | yes | 5 |  | PRJNA504891, PRJNA529124, PRJNA529400, PRJEB31971 |
| LiJ_2017 | `abstain_nothing_resolvable` |  |  |  | — |
| NayakRR_2021 | `bioproject_in_context` |  | 5 |  | PRJNA656577 |
| PasolliE_2019 | `bioproject_in_context` | yes | 6 |  | PRJNA485056, PRJNA504891 |
| Heitz-BuschartA_2016 | `bioproject_in_context` |  | 3 |  | PRJNA289586 |
| FanY_2023 | `abstain_nothing_resolvable` |  |  |  | — |
| QinJ_2012 | `abstain_nothing_resolvable` |  |  |  | — |
| ContevilleLC_2019 | `bioproject_in_context` |  | 3 |  | PRJNA527208 |
| LiSS_2016 | `abstain_nothing_resolvable` |  |  |  | — |
