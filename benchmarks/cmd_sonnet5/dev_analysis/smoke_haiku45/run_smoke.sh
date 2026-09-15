#!/usr/bin/env bash
# Haiku 4.5 smoke run of the table-path split on three development studies whose
# supplementary tables need structure plans. Fresh retrieval (frozen under _fetch/),
# lexical column mapper; SchemaMapper variants are replayed offline from the saved plans
# (dev_analysis/smoke_replay_mappers.py). Usage: run_smoke.sh <api-key-spec>
set -u
cd "$(dirname "$0")"
REPO=$(git rev-parse --show-toplevel)
BENCH=$REPO/benchmarks/cmd_sonnet5
echo "commit $(git rev-parse HEAD) dirty=$(git status --porcelain --untracked-files=no | wc -l | tr -d ' ')" > run/COMMIT.txt
pmid() { case "$1" in PasolliE_2019) echo 30661755;; TettAJ_2019_b) echo 31607556;; LiJ_2017) echo 28143587;; esac; }
for st in PasolliE_2019 TettAJ_2019_b LiJ_2017; do
  ( PYTHONPATH=$REPO/src python -m metaextractor.cli --paper-id "$(pmid $st)" \
      --schema "$BENCH/cmd.clean.linkml.yaml" --model claude-haiku-4-5 \
      --age-rules "$BENCH/age_rules_cmd.json" --fetch-cache "_fetch/$st" \
      --out "run/$st.json" --csv "run/$st.csv" --csv-provenance --run-meta "run/$st.meta.json" \
      --column-mapper lexical --api-key "$1" > "run/$st.log" 2>&1
    echo "$st rc=$?" >> run/status.txt ) &
done
wait
echo DONE >> run/status.txt
