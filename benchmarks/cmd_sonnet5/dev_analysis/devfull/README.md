# Full development-set run at revision-v4 HEAD (both models, three repeats)

The `out_v3` matrix — ten **development** studies x {Sonnet 5, Haiku 4.5} x 3 repeats,
60 extractions — re-run with the current code, so the fixes can be compared against
`out_v3` like for like on both models.

This is NOT `out_v4`: it holds no held-out study and no baseline, and those decisions are
still open. `out_v4` stays reserved for the final protocol run.

## Protocol

Frozen retrieval, clean tree, `--require-fetch-cache`, fetch and attempt ledgers,
per-extraction and per-attempt `.meta.json`:

    CMD_CURATION_DIR=... python run_frozen.py fetch     --out dev_analysis/devfull --fetch-wait 20
    CMD_CURATION_DIR=... python run_frozen.py run       --out dev_analysis/devfull \
        --models haiku sonnet --repeats 3 --cap 3000 --workers 4 --api-key file:PATH
    CMD_CURATION_DIR=... python run_frozen.py harmonize --out dev_analysis/devfull
    CMD_CURATION_DIR=... python run_frozen.py eval      --out dev_analysis/devfull
    CMD_CURATION_DIR=... python run_frozen.py aggregate --out dev_analysis/devfull
    CMD_CURATION_DIR=... python run_frozen.py verify    --out dev_analysis/devfull

## Retrieval

Frozen after commit 450b504, which made a retrieval reproducible: ENA does not guarantee a
manifest row order, and the BioSample attribute columns followed that order, so refetching
the same study changed `tables.json` while its content was identical. Rows are now sorted by
`run_accession` and added attribute columns alphabetically; two consecutive live retrievals
of ContevilleLC_2019 and NayakRR_2021 then produced identical checksums.

What retrieval still cannot pin down is which rung answers: an earlier attempt got
Bengtsson-PalmeJ_2015 from `europepmc_pdf` because PMC's HTML did not answer that minute,
where `out_v3`, the development check and this tree all got `pmc_html`. `fetched.json`
records the rung and the checksums for each study.

`_fetch/**/text.txt`, `_fetch/**/tables.json` and `*.text.txt` are gitignored; their
checksums live in `fetched.json`.
