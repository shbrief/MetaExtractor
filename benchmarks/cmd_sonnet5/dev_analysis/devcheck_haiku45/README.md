# Development-set check at revision-v4 HEAD (Haiku 4.5, one repeat)

Purpose: see what the defect fixes (i)-(v) plus the table-path split do to the ten
**development** studies, before committing to the `out_v4` protocol run. This is NOT
`out_v4`: one model, one repeat, and the tree lives under `dev_analysis/`.

Produced by the frozen protocol, commit `852de78`, clean tree:

    CMD_CURATION_DIR=... python run_frozen.py fetch     --out dev_analysis/devcheck_haiku45 --fetch-wait 20
    CMD_CURATION_DIR=... python run_frozen.py run       --out dev_analysis/devcheck_haiku45 \
        --models haiku --repeats 1 --cap 3000 --workers 4 --api-key file:PATH
    CMD_CURATION_DIR=... python run_frozen.py harmonize --out dev_analysis/devcheck_haiku45
    CMD_CURATION_DIR=... python run_frozen.py eval      --out dev_analysis/devcheck_haiku45
    CMD_CURATION_DIR=... python run_frozen.py aggregate --out dev_analysis/devcheck_haiku45
    CMD_CURATION_DIR=... python run_frozen.py verify    --out dev_analysis/devcheck_haiku45   # VERIFIED

10 tasks, 10 attempts, 0 failures, estimated US$1.04 over all attempts.

Retrieval reproduces `out_v3/_fetch` exactly (same source, body flag, table count and text
length for all ten studies); the only difference is the runs' BioSample attributes now
appended to the six ENA manifests (route A). `_fetch/**/text.txt`, `_fetch/**/tables.json`
and `*.text.txt` are gitignored; `fetched.json` keeps their checksums.

Comparison against `out_v3`'s three Haiku repeats is in `COMPARISON.md`.
