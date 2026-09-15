# Haiku 4.5 smoke run of the table-path split (development studies)

`run_smoke.sh` at commit `2882a2c` (clean tree): PasolliE_2019, TettAJ_2019_b, LiJ_2017, one
extraction each with `claude-haiku-4-5`, fresh retrieval frozen under `_fetch/` (only
`fetched.json` is committed; text and parsed tables are not redistributed), lexical column mapper.

- `run/<study>.json`, `.csv` — MetaExtractor output (values as extracted, before MetaHarmonizer)
- `run/<study>.meta.json` — calls with stop reasons and the saved structure plans; cost estimate
- `run/<study>.log`, `status.txt`, `COMMIT.txt`

Estimated cost (list prices dated 2026-06-24): PasolliE_2019 US$0.183, TettAJ_2019_b US$0.160,
LiJ_2017 US$0.111. `../mapper_benchmark_tables.py` replays the saved plans with each column mapper.
