#!/usr/bin/env python
"""Map an arbitrary term list through a (cached) OntologyMapper corpus.
Usage: map_terms.py <category> <corpus_category> <terms.json> <out.csv>
  category       : disease|bodysite|treatment  (OM corpus_category)
  root_override  : NCIt root to force (or '-' for registry default)
  terms.json     : JSON list of terms
  out.csv        : crosswalk output (query, match1, match1_score, match1_code)
Reads cache location from env (METAHARMONIZER_DATA_DIR etc.).
"""
import sys, json, pathlib
import pandas as pd
from metaharmonizer.engine import ontology_mapping_engine as ome

corpus_category, root_override, terms_path, out_path = sys.argv[1:5]
if root_override != "-":
    ome._CORPUS_REGISTRY[("disease", "ncit")] = root_override
from metaharmonizer import OntoMapEngine
from metaharmonizer._paths import RETRIEVED_ONTOLOGIES_DIR

terms = json.loads(pathlib.Path(terms_path).read_text())
eng = OntoMapEngine(corpus_category=corpus_category, query_ls=terms,
                    ontology_source="ncit", s3_strategy=None)
res = eng.run()
df = pd.read_csv(RETRIEVED_ONTOLOGIES_DIR / f"ncit_{corpus_category}_corpus.csv")
code_map = {str(l).strip().lower(): str(c) for l, c in zip(df["label"], df["obo_id"])}
res["match1_code"] = res["match1"].map(lambda l: code_map.get(str(l).strip().lower(), ""))
res[["query", "ref_match", "stage", "match1", "match1_score", "match1_code"]].to_csv(out_path, index=False)
print(f"wrote {out_path} ({len(res)} rows)")
