"""The gold firewall: curated data must never reach the extraction path.

MetaExtractor is scored against human-curated curatedMetagenomicData tables. An
extractor that could read those tables would make every metric meaningless, so
the boundary is worth a guard rather than a convention.

The boundary holds today -- exactly one function in the package reads curated
data from disk (:func:`metaextractor.evaluation.load_gold_tsv`), and
``metaextractor.cli`` imports neither ``evaluation`` nor ``alignment``. These
tests pin that, so a future change has to break a test rather than a habit.

Four invariants, checked four ways:

1. **Import graph** -- importing the CLI must not pull the scoring modules in.
   Checked in a subprocess, because this test session imports them itself.
2. **Source scan** -- no extraction-path module may name a curated path, even in
   code no test exercises. Static, so it survives dead code.
3. **One-way dependency** -- the eval side may import the library; the library
   may never import the eval side or the benchmark tree.
4. **The frozen-run argv** -- the benchmark runner knows where the curated
   checkout is (it records its git HEAD for provenance) but must never pass a
   path from it to the extractor.

A fifth test pins what the *schema* is allowed to tell the model: the answer
space (schema-derived enum labels and ontology CURIEs) but never the answers.

Two known exposures are deliberately **not** guarded here because they are
eval-side and documented at their source: ``bench.py run-tables`` feeds a file
from the curated checkout to the extractor as a supplementary table (ad hoc, and
not on the frozen path -- see test 4), and the harmonization crosswalks union the
gold side in when canonicalizing extracted values (see
``harmonize/crosswalk.py:load_field_crosswalk``). Both are measured rather than
asserted; see ``evaluation/extensions/``.
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "metaextractor"
BENCH = Path(__file__).resolve().parents[1] / "benchmarks" / "cmd_sonnet5"

#: Modules that run during an extraction. None of them may touch curated data.
#: Deliberately spelled out rather than discovered, so adding a module to the
#: extraction path is a conscious edit to this list.
EXTRACTION_PATH = (
    "extractor",
    "fetcher",
    "prompts",
    "table_select",
    "table_plan",
    "column_mapper",
    "sra_manifest",
    "sample_rules",
    "schema",
    "schema_loader",
    "supplementary",
    "writers",
    "output",
    "keys",
    "cli",
    "launch",
)

#: The scoring modules. They read gold; nothing on the extraction path may reach
#: them, directly or transitively.
GOLD_READERS = ("metaextractor.evaluation", "metaextractor.alignment")

#: Literals that only ever appear in code that reads curated data.
FORBIDDEN_LITERALS = (
    "CMD_CURATION_DIR",   # env var naming the curatedMetagenomicDataCuration checkout
    "_sample.tsv",        # the curated per-sample tables themselves
    "_ontology_term_id",  # the curators' ontology ids
    "crosswalk_",         # harmonization crosswalk files
    "load_gold",          # the gold loader
    "inst/curated",       # the curated subtree of the curation repo
)


def _module_path(name: str) -> Path:
    return SRC / f"{name}.py"


# ---------------------------------------------------------------------------
# 1. Import graph
# ---------------------------------------------------------------------------

def test_cli_import_does_not_pull_in_the_gold_readers():
    """Importing the CLI must not import evaluation or alignment.

    Run in a subprocess: this pytest session has already imported both (the
    evaluation tests do), so an in-process ``sys.modules`` check would pass
    vacuously or fail spuriously depending on test order.
    """
    probe = (
        "import sys, json\n"
        "import metaextractor.cli\n"
        f"print(json.dumps([m for m in {GOLD_READERS!r} if m in sys.modules]))\n"
    )
    proc = subprocess.run([sys.executable, "-c", probe],
                          capture_output=True, text=True, check=True)
    leaked = __import__("json").loads(proc.stdout.strip().splitlines()[-1])
    assert leaked == [], (
        f"importing metaextractor.cli pulled in {leaked}. The extraction path must "
        "not reach the scoring modules; move whatever is shared into a module that "
        "reads no gold."
    )


def test_importing_every_extraction_module_stays_clear_of_the_gold_readers():
    """Import the whole extraction path in one subprocess and report any leak.

    One subprocess rather than one per module: ``metaextractor/__init__.py``
    imports ``MetaExtractor``, so *any* ``import metaextractor.X`` already drags
    the core in, and sixteen separate interpreter launches would assert the same
    thing sixteen times. Per-module granularity comes from
    :func:`test_no_extraction_module_imports_a_gold_reader`, which reads the ASTs
    and costs nothing.
    """
    probe = (
        "import sys, json\n"
        + "".join(f"import metaextractor.{m}\n" for m in EXTRACTION_PATH)
        + f"print(json.dumps(sorted(m for m in {GOLD_READERS!r} if m in sys.modules)))\n"
    )
    proc = subprocess.run([sys.executable, "-c", probe],
                          capture_output=True, text=True, check=True)
    leaked = __import__("json").loads(proc.stdout.strip().splitlines()[-1])
    assert leaked == [], (
        f"importing the extraction path pulled in {leaked}. Check which module did "
        "it with test_no_extraction_module_imports_a_gold_reader."
    )


# ---------------------------------------------------------------------------
# 2. Source scan
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("module", EXTRACTION_PATH)
def test_extraction_module_names_no_curated_path(module):
    """A static scan, so it holds for code no test happens to exercise."""
    path = _module_path(module)
    assert path.exists(), f"{path} is missing; update EXTRACTION_PATH"
    text = path.read_text(encoding="utf-8")
    found = [lit for lit in FORBIDDEN_LITERALS if lit in text]
    assert found == [], (
        f"{module}.py names {found}. Only the scoring side may reference curated "
        "data; if this is a comment, reword it so the guard stays meaningful."
    )


# ---------------------------------------------------------------------------
# 3. One-way dependency
# ---------------------------------------------------------------------------

def _imported_names(path: Path) -> set[str]:
    """Every module name this file imports, including inside functions."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_library_never_imports_the_benchmark_or_harmonization_code():
    """The arrow points eval -> library, never the reverse.

    ``harmonize/crosswalk.py`` imports ``metaextractor.evaluation``. Nothing under
    ``src/`` may import ``crosswalk``, ``bench``, ``aggregate`` or anything else
    from the benchmark tree -- that would make the library depend on the thing
    that scores it.
    """
    offenders: dict[str, set[str]] = {}
    for path in sorted(SRC.rglob("*.py")):
        bad = {
            name for name in _imported_names(path)
            if name.split(".")[0] in {
                "crosswalk", "bench", "bench_paths", "aggregate", "run_frozen",
                "benchmarks", "harmonize",
            }
        }
        if bad:
            offenders[str(path.relative_to(SRC))] = bad
    assert offenders == {}, f"library modules importing eval/benchmark code: {offenders}"


def test_no_extraction_module_imports_a_gold_reader():
    """Direct-import check, complementing the subprocess module-graph test."""
    offenders = {}
    for module in EXTRACTION_PATH:
        bad = {n for n in _imported_names(_module_path(module))
               if n in GOLD_READERS}
        if bad:
            offenders[module] = bad
    assert offenders == {}, f"extraction modules importing gold readers: {offenders}"


# ---------------------------------------------------------------------------
# 4. The frozen-run argv
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not (BENCH / "run_frozen.py").exists(),
                    reason="benchmark tree not present")
def test_frozen_run_passes_no_curated_path_to_the_extractor():
    """``run_frozen.py`` builds the extractor's argv from frozen retrievals only.

    It *does* know where the curated checkout is -- it records that repo's git
    HEAD so a run is reproducible -- so the guard is on the argv, not on the
    import. Every flag the runner passes is checked against an allowlist; a new
    flag that could carry a curated path has to be added here deliberately.
    """
    source = (BENCH / "run_frozen.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    # Find the `cmd = [...]` assignment inside _task.
    cmd_elements: list[ast.expr] | None = None
    for node in ast.walk(tree):
        if (isinstance(node, ast.FunctionDef) and node.name == "_task"):
            for stmt in ast.walk(node):
                if (isinstance(stmt, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == "cmd"
                                for t in stmt.targets)
                        and isinstance(stmt.value, ast.List)):
                    cmd_elements = list(stmt.value.elts)
                    break
    assert cmd_elements is not None, "could not find the `cmd = [...]` list in _task"

    flags = {e.value for e in cmd_elements
             if isinstance(e, ast.Constant) and isinstance(e.value, str)
             and e.value.startswith("--")}
    allowed = {
        "--paper-id", "--schema", "--model", "--age-rules",
        "--fetch-cache", "--require-fetch-cache",
        "--out", "--csv", "--csv-provenance", "--save-text", "--run-meta",
    }
    unexpected = flags - allowed
    assert unexpected == set(), (
        f"run_frozen._task passes unrecognised flags {unexpected} to the extractor. "
        "If one of them can carry a path from the curated checkout, the frozen run "
        "is no longer blind; if it is harmless, add it to `allowed` here."
    )

    # The retrieval the extractor reads must come from the run tree, not the
    # curated checkout.
    assert "--require-fetch-cache" in flags, (
        "the frozen run must refuse to reach the network, so that what the "
        "extractor reads is exactly the committed frozen retrieval"
    )
    assert "curation_dir" not in source.split("def _task", 1)[1].split("\ndef ", 1)[0], (
        "_task references curation_dir(); the extractor's argv must not be built "
        "from the curated checkout"
    )


# ---------------------------------------------------------------------------
# 5. What the schema may tell the model
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not (BENCH / "cmd.clean.linkml.yaml").exists(),
                    reason="benchmark schema not present")
def test_schema_gives_the_model_the_answer_space_not_the_answers():
    """Dynamic enums are emptied to ``string``; static ones legitimately remain.

    ``make_clean_schema.py`` rewrites every enum with no ``permissible_values``
    to ``range: string``, so the big ontology-subtree fields -- including the two
    harmonized ones, ``disease`` and ``treatment`` -- reach the model with no
    candidate list. The enums that keep their values carry labels and ontology
    CURIEs that come from the *schema*, not from any curated row: that is the
    answer space, which the model is entitled to, and not the answers.
    """
    yaml = pytest.importorskip("yaml")
    doc = yaml.safe_load((BENCH / "cmd.clean.linkml.yaml").read_text(encoding="utf-8"))
    enums = doc.get("enums") or {}
    slots = doc.get("slots") or {}

    emptied = {n for n, v in enums.items() if not (v or {}).get("permissible_values")}
    assert emptied, "expected the dynamic enums to have been emptied"

    # No slot may still point at an emptied enum: it must have become a string,
    # or the model would receive a range it cannot satisfy.
    dangling = {n: s["range"] for n, s in slots.items()
                if (s or {}).get("range") in emptied}
    assert dangling == {}, (
        f"slots still ranged on emptied enums: {dangling}. make_clean_schema.py "
        "must rewrite these to `string`."
    )

    # The harmonized fields specifically must not ship a candidate list, since
    # those are the fields scored against curated ontology ids.
    for field in ("disease", "treatment"):
        if field in slots:
            assert slots[field].get("range") == "string", (
                f"{field} must reach the model as a free string, not an enum: it is "
                "scored against the curators' ontology ids after harmonization."
            )
