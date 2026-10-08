# Gold-only crosswalk dependence — `out_v3` (`crosswalks`)

6 runs, 60 `cells.tsv` files, 3 harmonized field(s): `body_site`, `disease`, `treatment`.

A `TP_correct` cell is **dependent** when some term of its extracted value is mapped only by `crosswalk_gold_<field>.csv`. Because `Harmonizer.codes` requires every term of a value to map, one such term would leave the whole value unharmonized.

| field | gold-only entries | extracted entries | TP_correct | dependent | share |
|---|--:|--:|--:|--:|--:|
| `body_site` | 0 | 10 | 1347 | **0** | 0.000% |
| `disease` | 9 | 13 | 949 | **0** | 0.000% |
| `treatment` | 5 | 22 | 51 | **0** | 0.000% |
| **all** | | | 2347 | **0** | 0.000% |

## Verdict

**No correct cell depended on a gold-only crosswalk entry.** The union in `load_field_crosswalk` is therefore inert for these runs: every extracted surface form that harmonized was mapped by the extracted crosswalk on its own. The exposure is real in the code and empty in the data, and can be stated that way.

### Gold-only entries, for reference

`disease` (9): anorexia → `NCIT:C2875`, borderline hypertension → `NCIT:C3907`, celiac disease → `NCIT:C26714`, cytomegaloviral infection → `NCIT:C53649`, fecal microbiota transplantation → `NCIT:C171138`, gestational diabetes → `NCIT:C34942`, hepatitis → `NCIT:C3095`, irritable bowel syndrome → `NCIT:C82343`, ra → `NCIT:C2884`

`treatment` (5): antihypertensive agents → `NCIT:C270`, mtx → `NCIT:C642`, no → `NCIT:C158078`, not applicable → `NCIT:C158078`, ssri → `NCIT:C94725`
