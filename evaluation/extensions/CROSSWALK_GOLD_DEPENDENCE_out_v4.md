# Gold-only crosswalk dependence — `out_v4` (`crosswalks`)

6 runs, 60 `cells.tsv` files, 6 harmonized field(s): `body_site`, `disease`, `dna_extraction_kit`, `host_species`, `sequencing_platform`, `treatment`.

A `TP_correct` cell is **dependent** when some term of its extracted value is mapped only by `crosswalk_gold_<field>.csv`. Because `Harmonizer.codes` requires every term of a value to map, one such term would leave the whole value unharmonized.

| field | gold-only entries | extracted entries | TP_correct | dependent | share |
|---|--:|--:|--:|--:|--:|
| `body_site` | 0 | 10 | 1243 | **0** | 0.000% |
| `disease` | 11 | 11 | 1311 | **0** | 0.000% |
| `dna_extraction_kit` | 4 | 13 | 189 | **0** | 0.000% |
| `host_species` | 0 | 3 | 2004 | **0** | 0.000% |
| `sequencing_platform` | 3 | 14 | 2004 | **0** | 0.000% |
| `treatment` | 5 | 18 | 0 | **0** | — |
| **all** | | | 6751 | **0** | 0.000% |

## Verdict

**No correct cell depended on a gold-only crosswalk entry.** The union in `load_field_crosswalk` is therefore inert for these runs: every extracted surface form that harmonized was mapped by the extracted crosswalk on its own. The exposure is real in the code and empty in the data, and can be stated that way.

### Gold-only entries, for reference

`disease` (11): anorexia → `NCIT:C2875`, borderline hypertension → `NCIT:C3907`, celiac disease → `NCIT:C26714`, cytomegaloviral infection → `NCIT:C53649`, fecal microbiota transplantation → `NCIT:C171138`, gestational diabetes → `NCIT:C34942`, hepatitis → `NCIT:C3095`, hypertension → `NCIT:C3117`, irritable bowel syndrome → `NCIT:C82343`, ra → `NCIT:C2884`, type 2 diabetes mellitus → `NCIT:C26747`

`dna_extraction_kit` (4): mpbio → `CMDKIT:0009`, norgenbiotek → `CMDKIT:0010`, qiagen → `CMDKIT:0007`, zymobiomics96magbead → `CMDKIT:0015`

`sequencing_platform` (3): illuminahiseq → `CMDPLAT:0001`, illuminanovaseq → `CMDPLAT:0004`, ionproton → `CMDPLAT:0005`

`treatment` (5): antihypertensive agents → `NCIT:C270`, mtx → `NCIT:C642`, no → `NCIT:C158078`, not applicable → `NCIT:C158078`, ssri → `NCIT:C94725`
