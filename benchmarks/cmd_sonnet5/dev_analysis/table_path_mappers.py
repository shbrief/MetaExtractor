"""Development-study evaluation of the table-path split (no model calls; out_v3 read only).

1. The committed needs_structure_plan decision for every selected development table,
   against the out_v3 LLM plans for the same table (both models, all repeats).
2. Distinct header -> field mappings on the tables read as is, per column mapper:
   lexical cascade, SchemaMapper stage 1, stages 1-2, stages 1-3 (MetaHarmonizer defaults).
3. The four single-manifest studies rebuilt from ENA manifests + BioSample attributes
   (live, public archive requests) with each mapper, combined with the out_v3 study-level
   answers and the current fan-out and age rules, scored with out_v3 crosswalks.

  CMD_CURATION_DIR=... HF_HUB_OFFLINE=1 python dev_analysis/table_path_mappers.py OUTDIR
"""
import glob, json, re, sys, collections, copy
from pathlib import Path
BENCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BENCH)); sys.path.insert(0, str(BENCH / "harmonize"))
import bench
from bench_paths import SCHEMA, AGE_RULES, SCHEMAMAPPER_DICTS, load_manifest
from crosswalk import Harmonizer
from metaextractor.schema_loader import load_schema_file
from metaextractor.fetcher import load_fetched
from metaextractor.extractor import MetaExtractor
from metaextractor.table_plan import needs_structure_plan
from metaextractor.table_select import score_table, is_figure_source_data
from metaextractor.schema_mapping import LexicalColumnMapper, SchemaMapperColumnMapper
from metaextractor.sra_manifest import manifest_for_paper
from metaextractor import sample_rules as sr
from metaextractor.output import ExtractionResult

class NoCall:
    class messages:
        def create(*a, **k): raise AssertionError("no model call")

schema = load_schema_file(SCHEMA); SF = [f.name for f in schema.fields]
rules = sr.AgeBoundRules.from_json(AGE_RULES)
sm = SchemaMapperColumnMapper(SCHEMAMAPPER_DICTS["target"], SCHEMAMAPPER_DICTS["alias"], SCHEMAMAPPER_DICTS["values"])
sm.engine.nci_client = None
def with_stages(st):
    m = copy.copy(sm); m.stages = st; return m
BACKENDS = {"lexical": LexicalColumnMapper(), "sm_stage1": with_stages((1,)),
            "sm_stages12": with_stages((1, 2)), "sm_stages123": with_stages((1, 2, 3))}

# 1. detector vs out_v3 plans
plans = collections.defaultdict(set)
for pth in glob.glob(str(BENCH / "out_v3" / "*_r*" / "*.json")):
    if pth.endswith((".meta.json", "summary.json")): continue
    st = Path(pth).stem
    for w in json.loads(Path(pth).read_text())["extraction_warnings"]:
        mm = re.search(r"Table '(.+?)': plan applied \(header_rows=(\[[^\]]*\]), melt=(\w+)", w)
        if mm:
            plans[(st, mm.group(1))].add("flat" if mm.group(2) == "[0]" and mm.group(3) == "no" else "structured")
conf = collections.Counter()
for m in load_manifest():
    try: T = load_fetched(BENCH / "out_v3/_fetch" / m["study"]).supplementary_tables
    except Exception: continue
    for t in T:
        if t.source == "ena" or (m["study"], t.name) not in plans: continue
        kinds = plans[(m["study"], t.name)]
        ref = "out_v3 plans all flat" if kinds == {"flat"} else ("out_v3 plans all structured" if "flat" not in kinds else "out_v3 plans disagree")
        conf[(ref, "structure plan" if needs_structure_plan(t)[0] else "read as is")] += 1
print("== committed detector vs out_v3 LLM plans (tables that received a plan in out_v3)")
for k, v in sorted(conf.items()): print(f"  {v:3d}  {k[0]} -> {k[1]}")

# 2. distinct header->field pairs on tables read as is + manifests, by backend
pairs = collections.defaultdict(collections.Counter)
tables = []
for m in load_manifest():
    try: T = load_fetched(BENCH / "out_v3/_fetch" / m["study"]).supplementary_tables
    except Exception: continue
    for t in T:
        if t.source == "ena" or is_figure_source_data(t): continue
        rel = score_table(t, schema)
        if rel.is_matrix or rel.score < 0.15 or needs_structure_plan(t)[0]: continue
        tables.append((m["study"], t))
for name, be in BACKENDS.items():
    for st, t in tables:
        res = be.map_table(t.columns, t.rows, SF)
        for c, f in res.mapped.items():
            pairs[name][(c, f, res.tier_used.get(c, "lexical").split("(")[0])] += 1
print(f"== {len(tables)} development tables read as is: distinct header -> field mappings")
for name in BACKENDS:
    print(f"\n-- {name}: {len(pairs[name])} distinct")
    print("   ", "; ".join(f"{c}->{f}" + (f" [{tier.split(':',2)[-1] if 'schemamapper' in tier else 'lex'}]") for (c, f, tier) in sorted(pairs[name])))

harm = Harmonizer(BENCH / "out_v3" / "crosswalks")
report = collections.defaultdict(lambda: collections.defaultdict(bench._zero))
field_report = collections.defaultdict(lambda: collections.defaultdict(bench._zero))
OUT = Path(sys.argv[1])
for m in load_manifest():
    rec = json.loads((BENCH / "out_v3/_fetch" / m["study"] / "fetched.json").read_text())
    projects = re.findall(r"PRJ[A-Z]+\d+", (rec.get("sra_manifest_source") or "").split(" ")[0])
    if len(projects) != 1 or rec["n_tables"] != 1: continue
    man = manifest_for_paper("", explicit_project=projects[0]).table
    built = {}
    for name, be in BACKENDS.items():
        ex = MetaExtractor(client=NoCall(), column_mapper=be)
        samples, W, _ = ex._build_samples_from_tables([man], schema)
        built[name] = (samples, dict(ex.last_table_sources))
    for run in sorted(p for p in (BENCH / "out_v3").glob("*_r*") if p.is_dir()):
        rj = run / f"{m['study']}.json"; mk = run.name.split("_")[0]
        for variant in ["v3_rows_current_rules", *BACKENDS]:
            dst = OUT / variant / run.name; dst.mkdir(parents=True, exist_ok=True); out = dst / rj.name
            if not rj.exists():
                out.unlink(missing_ok=True)
            else:
                res = ExtractionResult.model_validate_json(rj.read_text())
                if variant == "v3_rows_current_rules":
                    for s_, p_ in zip(res.samples, res.sample_provenance):
                        for f, src in list(p_.items()):
                            if src.startswith(("study_fanout", "subgroup_fanout", "age_rule")):
                                s_.pop(f, None); del p_[f]
                else:
                    samples, sources = built[variant]
                    res.granularity = "sample_level"; res.samples = copy.deepcopy(samples)
                    res.sample_provenance = [{k: sources.get(k, "table") for k, v in s.items()
                                              if not k.startswith("__") and v not in (None, "")} for s in res.samples]
                if res.granularity == "sample_level" and res.samples:
                    sr.fan_out_fields_to_samples(res, schema)
                sr.normalize_age_bounds(res, rules, schema)
                out.write_text(res.model_dump_json())
            r = bench.score_study(m, out, harm)
            for join in ("end_to_end", "conditional"):
                bench._add(report[(m["study"], mk, variant)][join], r[join]["content"])
            for f, c in r["fields_end_to_end"].items():
                if f not in bench.META_FIELDS:
                    bench._add(field_report[(mk, variant)][f], c)
order = ["v3_rows_current_rules", *BACKENDS]
print("\n== manifest-only studies (out_v3 study-level answers reused; current fan-out and age rules in every variant)")
print("| study | model | variant | TPc | TPw | FP | FN | F1 all curated |")
for (st, mk, var), j in sorted(report.items(), key=lambda kv: (kv[0][0], kv[0][1], order.index(kv[0][2]))):
    e = j["end_to_end"]
    print(f"| {st} | {mk} | {var} | {e['tp_correct']} | {e['tp_wrong']} | {e['fp']} | {e['fn']} | {(bench.metrics(e)['f1'] or 0):.3f} |")
print("\n== fields that differ from v3_rows_current_rules (pooled over the 4 studies and 3 repeats): TPc/TPw/FP")
for mk in ("sonnet", "haiku"):
    base = field_report[(mk, "v3_rows_current_rules")]
    for var in BACKENDS:
        d = field_report[(mk, var)]
        ch = {f: f"{base[f]['tp_correct']}/{base[f]['tp_wrong']}/{base[f]['fp']} -> {d[f]['tp_correct']}/{d[f]['tp_wrong']}/{d[f]['fp']}"
              for f in d if (d[f]['tp_correct'], d[f]['tp_wrong'], d[f]['fp']) != (base[f]['tp_correct'], base[f]['tp_wrong'], base[f]['fp'])}
        print(f"- {mk} {var}: {ch}")
