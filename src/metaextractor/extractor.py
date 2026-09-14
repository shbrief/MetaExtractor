"""Core extractor: wraps the Anthropic SDK call with prompt caching + JSON parsing.

Schemas with more than ``batch_size`` fields are transparently split into
batches and merged. Each batch reuses the cached system prompt and paper
text, so the marginal cost is only the per-batch output.
"""
from __future__ import annotations

import json
import os

from anthropic import Anthropic
from pydantic import ValidationError

from metaextractor.column_mapper import (
    ColumnMapping,
    apply_mapping,
    join_tables,
    map_columns,
)
from metaextractor.output import ExtractionResult, TableSelection
from metaextractor.prompts import SYSTEM_PROMPT, build_user_content
from metaextractor.sample_rules import (
    AgeBoundRules,
    ensure_provenance,
    fan_out_fields_to_samples,
    normalize_age_bounds,
)
from metaextractor.schema import Field, Schema
from metaextractor.supplementary import Table
from metaextractor.table_plan import (
    PlanExecutionError,
    PlanProposalError,
    TablePlan,
    execute_plan,
    propose_plan,
)
from metaextractor.table_select import score_table

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 16384
#: Upper bound for the output budget when a response stops at ``max_tokens``.
#: The budget doubles from ``max_tokens`` up to this value (adaptive-thinking
#: tokens count against the same budget). 64K is within every listed model's limit.
DEFAULT_MAX_TOKENS_CEILING = 64000
DEFAULT_BATCH_SIZE = 30
DEFAULT_MIN_TABLE_RELEVANCE = 0.15

# USD per 1M tokens. Cache read / write follow Anthropic's standard 5m
# ephemeral multipliers (0.1x / 1.25x of base input). Update as needed.
#: Date the base input/output rates below were last checked against Anthropic's
#: published model pricing table.
PRICING_AS_OF = "2026-06-24"
PRICING_USD_PER_MTOK: dict[str, dict[str, float]] = {
    "claude-sonnet-5":   {"input": 2.0, "output": 10.0, "cache_read": 0.20, "cache_write": 2.50},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_write": 3.75},
    "claude-opus-4-7":   {"input": 15.0, "output": 75.0, "cache_read": 1.50, "cache_write": 18.75},
    "claude-haiku-4-5":  {"input": 1.0, "output": 5.0,  "cache_read": 0.10, "cache_write": 1.25},
}


class ExtractionError(RuntimeError):
    """Raised when the LLM response cannot be parsed into ExtractionResult."""

    def __init__(self, message: str, raw_response: str | None = None):
        super().__init__(message)
        self.raw_response = raw_response


def _extract_json_blob(raw: str) -> str:
    """Find the JSON object in a possibly-prose-wrapped model response.

    Prefers a ```json fenced block; otherwise returns the substring from
    the first '{' to its matching '}' (string-aware).
    """
    s = raw.strip()
    # Fenced ```json … ```
    fence = s.find("```")
    if fence != -1:
        after = s[fence + 3:]
        if after.lower().startswith("json"):
            after = after[4:]
        end = after.find("```")
        if end != -1:
            return after[:end].strip()
    # First balanced { … }
    start = s.find("{")
    if start == -1:
        return s
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    return s[start:]


class MetaExtractor:
    def __init__(
        self,
        client: Anthropic | None = None,
        model: str = DEFAULT_MODEL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        batch_size: int = DEFAULT_BATCH_SIZE,
        sample_discovery: bool = True,
        api_key: str | None = None,
        min_table_relevance: float = DEFAULT_MIN_TABLE_RELEVANCE,
        age_rules: AgeBoundRules | None = None,
        max_tokens_ceiling: int = DEFAULT_MAX_TOKENS_CEILING,
    ):
        self.client = client or Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
        self.model = model
        self.max_tokens = max_tokens
        self.max_tokens_ceiling = max(max_tokens, max_tokens_ceiling)
        #: One record per API call of the last extract() call, including calls whose
        #: response was truncated and re-requested: purpose, fields, budget,
        #: stop_reason, output_tokens.
        self.last_calls: list[dict] = []
        self.batch_size = batch_size
        self.sample_discovery = sample_discovery
        self.min_table_relevance = min_table_relevance
        self.age_rules = age_rules
        #: Model identifiers returned by the API across the last extract() call.
        self.last_response_models: set[str] = set()
        #: schema field -> "table:<name>:<column>" / "manifest:<name>:<column>"
        #: for the table set that produced the last deterministic sample rows.
        self.last_table_sources: dict[str, str] = {}
        self.last_usage: dict[str, int] = {
            "input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "output_tokens": 0,
            "n_calls": 0,
        }

    def extract(
        self,
        paper_text: str,
        schema: Schema | dict | list,
        paper_id: str | None = None,
        tables: list | None = None,
    ) -> ExtractionResult:
        """Extract metadata from paper prose + optional structured tables.

        When ``tables`` is non-empty, the LLM only handles prose-derived
        fields and is told nothing about per-sample structure: samples
        come from the deterministic column-map + join pipeline. The LLM
        sample-discovery pass is skipped entirely in that mode.
        """
        schema_obj = schema if isinstance(schema, Schema) else Schema.from_dict(schema)
        self.last_usage = {k: 0 for k in self.last_usage}
        self.last_response_models = set()
        self.last_table_sources = {}
        self.last_calls = []

        # Deterministic table path: produce sample rows from structured tables,
        # then run the LLM only for prose-derived study-level fields.
        det_samples: list[dict] | None = None
        det_warnings: list[str] = []
        det_selections: list[TableSelection] = []
        if tables:
            det_samples, det_warnings, det_selections = self._build_samples_from_tables(
                tables, schema_obj
            )

        sample_ids: list[str] | None = None
        if self.sample_discovery and det_samples is None and "--- SUPPLEMENTARY FILE:" in paper_text:
            sample_ids = self._discover_sample_ids(paper_text, paper_id)

        if len(schema_obj.fields) <= self.batch_size:
            result = self._extract_one(paper_text, schema_obj, paper_id, sample_ids)
            if sample_ids:
                result.extraction_warnings.insert(
                    0, f"Sample discovery identified {len(sample_ids)} samples; "
                       f"per-batch extraction was constrained to these IDs."
                )
        else:
            batches = [
                Schema(fields=schema_obj.fields[i : i + self.batch_size])
                for i in range(0, len(schema_obj.fields), self.batch_size)
            ]
            results = [self._extract_one(paper_text, b, paper_id, sample_ids) for b in batches]
            result = _merge_results(results, sample_ids=sample_ids)
            if sample_ids:
                result.extraction_warnings.insert(
                    0, f"Sample discovery identified {len(sample_ids)} samples; "
                       f"per-batch extraction was constrained to these IDs."
                )

        if det_samples is not None:
            result.granularity = "sample_level"
            result.samples = det_samples
            result.table_selection = det_selections
            for w in det_warnings:
                result.extraction_warnings.append(w)
            result.sample_provenance = [
                {k: self.last_table_sources.get(k, "table") for k, v in s.items()
                 if not k.startswith("__") and v not in (None, "")}
                for s in det_samples
            ]
        else:
            result.sample_provenance = []
            ensure_provenance(result, default="llm_sample")

        if result.granularity == "sample_level" and result.samples and result.fields:
            counts = fan_out_fields_to_samples(result, schema_obj)
            if counts:
                detail = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
                result.extraction_warnings.append(
                    f"Fan-out of study/subgroup-level values into sample rows: {detail}."
                )

        # Per-subject age_min/age_max (opt-in via age_rules; runs after fan-out so
        # it can tell propagated ages from per-sample ones).
        n_age = normalize_age_bounds(result, self.age_rules, schema_obj)
        if n_age:
            result.extraction_warnings.append(
                f"Set {n_age} age_min/age_max cell(s) by the configured age-bound rules."
            )
        return result

    def _discover_sample_ids(
        self, paper_text: str, paper_id: str | None
    ) -> list[str] | None:
        """One-shot pass to enumerate stable per-sample identifiers.

        Returns the list of sample_ids if the model finds a sample-level
        structure (e.g. rows in a supplementary table), else None.
        """
        discovery_schema = Schema(fields=[
            Field(
                name="sample_id",
                description=(
                    "Stable identifier for each distinct biological sample described "
                    "in the paper or its supplementary tables. Encode all distinguishing "
                    "attributes (subject/pair, body site, timepoint, etc.) so different "
                    "samples have unique IDs. Use snake_case, e.g. 'pair1_infant_feces_T1'."
                ),
                type="string",
            )
        ])
        try:
            result = self._extract_one(paper_text, discovery_schema, paper_id, None,
                                       purpose="sample_discovery")
        except ExtractionError:
            return None
        if result.granularity != "sample_level" or not result.samples:
            return None
        seen: set[str] = set()
        ids: list[str] = []
        for s in result.samples:
            sid = s.get("sample_id")
            if not sid or sid == "not_reported" or sid in seen:
                continue
            seen.add(sid)
            ids.append(str(sid))
        return ids or None

    def _extract_one(
        self,
        paper_text: str,
        schema_obj: Schema,
        paper_id: str | None,
        sample_ids: list[str] | None = None,
        purpose: str = "fields",
    ) -> ExtractionResult:
        user_content = build_user_content(
            paper_text, schema_obj.to_prompt_json(), paper_id, sample_ids=sample_ids
        )

        budget = self.max_tokens
        while True:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=budget,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_content}],
            ) as stream:
                response = stream.get_final_message()

            if getattr(response, "model", None):
                self.last_response_models.add(str(response.model))
            u = response.usage
            self.last_usage["input_tokens"] += getattr(u, "input_tokens", 0) or 0
            self.last_usage["cache_creation_input_tokens"] += getattr(u, "cache_creation_input_tokens", 0) or 0
            self.last_usage["cache_read_input_tokens"] += getattr(u, "cache_read_input_tokens", 0) or 0
            self.last_usage["output_tokens"] += getattr(u, "output_tokens", 0) or 0
            self.last_usage["n_calls"] += 1
            stop_reason = getattr(response, "stop_reason", None)
            self.last_calls.append({
                "purpose": purpose, "n_fields": len(schema_obj.fields),
                "first_field": schema_obj.fields[0].name if schema_obj.fields else None,
                "max_tokens": budget, "stop_reason": stop_reason,
                "output_tokens": getattr(u, "output_tokens", None),
            })
            # A response cut off at the output budget is re-requested with a larger
            # budget; parsing a truncated JSON document can only fail.
            if stop_reason == "max_tokens" and budget < self.max_tokens_ceiling:
                budget = min(budget * 2, self.max_tokens_ceiling)
                continue
            break

        raw = "".join(block.text for block in response.content if block.type == "text").strip()
        if stop_reason == "max_tokens":
            raise ExtractionError(
                f"Model response truncated at max_tokens={budget} (the configured ceiling) "
                f"for a batch of {len(schema_obj.fields)} field(s).",
                raw_response=raw,
            )
        if stop_reason == "refusal":
            raise ExtractionError("Model declined to respond (stop_reason=refusal).",
                                  raw_response=raw)
        payload_str = _extract_json_blob(raw)
        try:
            payload = json.loads(payload_str)
        except json.JSONDecodeError as e:
            raise ExtractionError(f"Model returned non-JSON output: {e}", raw_response=raw) from e

        try:
            return ExtractionResult.model_validate(payload)
        except ValidationError as e:
            raise ExtractionError(
                f"Model output failed schema validation: {e}", raw_response=raw
            ) from e

    def _build_samples_from_tables(
        self,
        tables: list,
        schema: Schema,
    ) -> tuple[list[dict], list[str], list[TableSelection]]:
        """Build per-sample rows from tables, using any SRA/ENA run manifest
        (``source == "ena"``) strictly as a **fallback**.

        The auto-fetched run manifest is a per-sample source of last resort: it
        must never compete with — and possibly hijack the join anchor from — a
        study's own supplementary per-sample table (which would perturb studies
        that already enumerate correctly). So the article's own tables are
        processed first; the manifest is used only if they yield no sample rows.
        """
        if not tables:
            return [], [], []
        manifest_tables = [t for t in tables if getattr(t, "source", None) == "ena"]
        own_tables = [t for t in tables if getattr(t, "source", None) != "ena"]

        samples, warnings, selections = self._samples_from_table_set(own_tables, schema)
        self.last_table_sources = dict(self._set_sources)
        if samples:
            if manifest_tables:
                warnings.append(
                    f"SRA/ENA run manifest not used: the article's own tables already "
                    f"produced {len(samples)} sample row(s)."
                )
            return samples, warnings, selections
        if manifest_tables:
            warnings.append(
                "No per-sample rows from the article's own tables; falling back to "
                f"the SRA/ENA run manifest ({len(manifest_tables)} table(s))."
            )
            m_samples, m_warnings, m_selections = self._samples_from_table_set(
                manifest_tables, schema
            )
            self.last_table_sources = dict(self._set_sources)
            return m_samples, warnings + m_warnings, selections + m_selections
        return samples, warnings, selections

    def _samples_from_table_set(
        self,
        tables: list,
        schema: Schema,
    ) -> tuple[list[dict], list[str], list[TableSelection]]:
        """Table → sample-rows pipeline for one set of tables.

        Per table:
          1. Skip if it's a feature × samples matrix (taxa/genome × samples)
             — these would otherwise pollute per-sample output with one row
             per feature.
          2. Ask the LLM to propose a structural plan (multi-row header
             merge + optional long-format melt) and execute it. The plan
             never touches cell values. On plan failure, fall back to the
             default row-0-header parse.
          3. Lexical-map the resulting columns to schema field names.

        Then left-join across all kept tables on shared canonical keys.
        """
        self._set_sources: dict[str, str] = {}
        if not tables:
            return [], [], []
        schema_field_names = [f.name for f in schema.fields]
        warnings: list[str] = []
        selections: list[TableSelection] = []
        # (name, rows, relevance): relevance is retained so the join can anchor
        # on the most schema-relevant sample table (see the sort before join_tables).
        scored_tables: list[tuple[str, list[dict], float]] = []
        # table name -> (source kind, {schema field: source column})
        table_columns: dict[str, tuple[str, dict[str, str]]] = {}

        for t in tables:
            rel = score_table(t, schema)
            if rel.is_matrix:
                detail = rel.reasons[0] if rel.reasons else "feature × samples matrix"
                warnings.append(
                    f"Table {t.name!r}: skipped as measurement matrix "
                    f"({len(t.raw_rows)} rows × {len(t.columns)} cols; {detail})."
                )
                selections.append(TableSelection(
                    name=t.name, selected=False, score=rel.score, is_matrix=True,
                    matched_fields=rel.matched_fields, reasons=rel.reasons,
                ))
                continue
            if rel.score < self.min_table_relevance:
                detail = "; ".join(rel.reasons) or "no schema-matching columns"
                warnings.append(
                    f"Table {t.name!r}: skipped, low schema relevance "
                    f"(score={rel.score:.2f} < {self.min_table_relevance:.2f}; {detail})."
                )
                selections.append(TableSelection(
                    name=t.name, selected=False, score=rel.score,
                    matched_fields=rel.matched_fields, reasons=rel.reasons,
                ))
                continue
            warnings.append(
                f"Table {t.name!r}: selected (relevance={rel.score:.2f}; matched "
                f"{len(rel.matched_fields)}/{len(schema.fields)} schema fields)."
            )
            selections.append(TableSelection(
                name=t.name, selected=True, score=rel.score,
                matched_fields=rel.matched_fields, reasons=rel.reasons,
            ))

            transformed: list = None  # type: ignore[assignment]
            try:
                plan, usage = propose_plan(self.client, self.model, t, schema_field_names,
                                           calls=self.last_calls)
                _accumulate_usage(self.last_usage, usage)
                transformed = execute_plan(t, plan)
                _reconcile_dropped_schema_columns(
                    t, plan, transformed, schema_field_names, warnings
                )
                warnings.append(
                    f"Table {t.name!r}: plan applied "
                    f"(header_rows={plan.header_rows}, "
                    f"melt={'yes' if plan.melt else 'no'}, "
                    f"out_rows={len(transformed.rows)})."
                )
            except (PlanProposalError, PlanExecutionError) as e:
                if isinstance(e, PlanProposalError) and e.usage:
                    _accumulate_usage(self.last_usage, e.usage)
                warnings.append(
                    f"Table {t.name!r}: plan path failed ({type(e).__name__}: {e}); "
                    f"falling back to row-0-header parse."
                )
                transformed = t

            m: ColumnMapping = map_columns(transformed.columns, schema_field_names)
            renamed = apply_mapping(transformed.rows, m)
            kind = "manifest" if getattr(t, "source", None) == "ena" else "table"
            table_columns[transformed.name] = (
                kind,
                {**{c: c for c in transformed.columns if c in schema_field_names},
                 **{tgt: src for src, tgt in m.mapped.items()}},
            )
            scored_tables.append((transformed.name, renamed, rel.score))
            if m.collisions:
                for src, tgt in m.collisions:
                    warnings.append(
                        f"Table {transformed.name!r}: column {src!r} collided with another "
                        f"header already mapped to schema field {tgt!r}; left unmapped."
                    )
            if m.unmapped:
                warnings.append(
                    f"Table {transformed.name!r}: {len(m.unmapped)} column(s) passed "
                    f"through under original names (schema didn't match): {m.unmapped[:5]}"
                    + ("..." if len(m.unmapped) > 5 else "")
                )

        if not scored_tables:
            return [], warnings, selections

        # Anchor the join on the most schema-relevant table so the emitted sample
        # count reflects the best per-sample manifest — not whichever table came
        # first in file order, which for meta-analyses can be a giant public-repo
        # dump (e.g. 9k rows) rather than the study's own samples. Sort is stable,
        # so equal-relevance tables keep their original order.
        scored_tables.sort(key=lambda x: x[2], reverse=True)
        mapped_tables = [(name, rows) for name, rows, _ in scored_tables]
        # Attribute each field to the most relevant table that maps it (the join
        # keeps the primary's value on conflict, so this is the value's source).
        for name, _rows, _score in scored_tables:
            kind, cols = table_columns.get(name, ("table", {}))
            for fname, col in cols.items():
                self._set_sources.setdefault(fname, f"{kind}:{name}:{col}")
        merged, jplan = join_tables(mapped_tables)
        for j in jplan.joins:
            warnings.append(
                f"Joined table {j['right']!r} into {jplan.primary!r} on key "
                f"{j['key']!r} (overlap {j['overlap']}, {j['kept_rows']} rows matched)."
            )
        for s in jplan.skipped:
            warnings.append(
                f"Did not join table {s['right']!r} into {jplan.primary!r}: {s['reason']}."
            )
        return merged, warnings, selections


def _reconcile_dropped_schema_columns(
    raw: Table,
    plan: TablePlan,
    transformed: Table,
    schema_field_names: list[str],
    warnings: list[str],
) -> None:
    """Re-attach raw columns the LLM plan dropped that map to a schema field.

    ``execute_plan`` builds its output columns solely from the plan's
    ``id_columns``, so a raw column that lexically or via alias resolves to a
    schema field the plan didn't keep (e.g. an SRA/ENA manifest's
    ``instrument_model`` → ``sequencing_platform``) is lost *before*
    ``map_columns`` ever sees it. For a flat, single-header, un-melted table
    the executor emits exactly one output row per surviving raw data row, in
    order, so such a column can be spliced back by position and picked up by
    the subsequent ``map_columns`` pass under its original header.

    Mutates ``transformed`` in place. No-op for melted or multi-row-header
    plans, where the raw-row↔output-row correspondence is not 1:1.
    """
    if plan.melt is not None or len(plan.header_rows) != 1:
        return
    covered = set(map_columns(transformed.columns, schema_field_names).mapped.values())
    raw_map = map_columns(raw.columns, schema_field_names).mapped
    # schema fields the raw table carries but the plan dropped
    missing = {src: tgt for src, tgt in raw_map.items() if tgt not in covered}
    if not missing:
        return
    n_cols = max((len(r) for r in raw.raw_rows), default=0)
    drop_row_set = set(plan.drop_rows)
    kept = [
        ri for ri in range(plan.data_starts_at, len(raw.raw_rows))
        if ri not in drop_row_set
    ]
    if len(kept) != len(transformed.rows):
        return  # row alignment not guaranteed; bail rather than misattribute
    added: list[str] = []
    for src, tgt in missing.items():
        if src in transformed.columns:
            continue
        try:
            col_idx = raw.columns.index(src)
        except ValueError:
            continue
        if col_idx >= n_cols:
            continue
        for k, out_row in enumerate(transformed.rows):
            row = raw.raw_rows[kept[k]]
            out_row[src] = row[col_idx] if col_idx < len(row) else ""
        transformed.columns.append(src)
        added.append(f"{src}→{tgt}")
    if added:
        warnings.append(
            f"Table {transformed.name!r}: re-attached plan-dropped schema "
            f"column(s) {', '.join(added)} for downstream mapping."
        )


def _merge_results(
    results: list[ExtractionResult],
    sample_ids: list[str] | None = None,
) -> ExtractionResult:
    """Merge per-batch results.

    Granularity/subgroups taken from the first batch; mismatches flagged.
    When ``sample_ids`` is provided (i.e. discovery succeeded), `samples`
    are merged across batches by ``sample_id`` so each batch contributes
    its own field columns to the same rows. Otherwise the first batch's
    samples are kept (no safe way to merge anonymous rows).
    """
    first = results[0]
    merged_fields: dict = {}
    merged_warnings: list[str] = []

    if sample_ids:
        by_id: dict[str, dict] = {sid: {"sample_id": sid} for sid in sample_ids}
        for idx, r in enumerate(results):
            if r.granularity != "sample_level":
                merged_warnings.append(
                    f"Batch {idx} returned granularity={r.granularity!r} despite "
                    f"sample-id constraint; its sample rows were ignored."
                )
                continue
            for s in r.samples:
                sid = s.get("sample_id")
                if not sid:
                    merged_warnings.append(
                        f"Batch {idx} returned a sample row without sample_id; ignored."
                    )
                    continue
                if sid not in by_id:
                    merged_warnings.append(
                        f"Batch {idx} returned unknown sample_id {sid!r} (not in "
                        f"discovery list); ignored."
                    )
                    continue
                for k, v in s.items():
                    if k == "sample_id":
                        continue
                    if k in by_id[sid] and by_id[sid][k] != v:
                        merged_warnings.append(
                            f"Sample {sid!r} field {k!r}: batch {idx} value differs "
                            f"from earlier batch; kept earlier value."
                        )
                        continue
                    by_id[sid][k] = v
        merged_samples = list(by_id.values())
        granularity = "sample_level"
        subgroups: list[str] = []
    else:
        merged_samples = list(first.samples)
        granularity = first.granularity
        subgroups = first.subgroups

    for idx, r in enumerate(results):
        if not sample_ids and idx > 0 and r.granularity != first.granularity:
            merged_warnings.append(
                f"Batch {idx} returned granularity={r.granularity!r}, "
                f"differs from batch 0 ({first.granularity!r}); kept batch 0."
            )
        if not sample_ids and idx > 0 and set(r.subgroups) != set(first.subgroups):
            merged_warnings.append(
                f"Batch {idx} subgroups {r.subgroups} differ from "
                f"batch 0 {first.subgroups}; kept batch 0."
            )
        for name, field in r.fields.items():
            if name in merged_fields:
                merged_warnings.append(f"Duplicate field {name!r} across batches; kept first.")
                continue
            merged_fields[name] = field
        merged_warnings.extend(r.extraction_warnings)

    return ExtractionResult(
        paper_id=first.paper_id,
        granularity=granularity,
        subgroups=subgroups,
        fields=merged_fields,
        samples=merged_samples,
        extraction_warnings=merged_warnings,
    )


def _accumulate_usage(target: dict[str, int], source: dict[str, int]) -> None:
    """Add per-call usage numbers into a running tally."""
    for k, v in source.items():
        target[k] = target.get(k, 0) + (v or 0)


def estimate_cost_usd(usage: dict[str, int], model: str) -> dict[str, float]:
    """Estimate USD cost for a usage dict (input/output/cache tokens)."""
    rates = PRICING_USD_PER_MTOK.get(model)
    if not rates:
        return {"total_usd": 0.0, "note": f"no pricing entry for {model}"}
    per = 1_000_000
    input_usd = usage["input_tokens"] * rates["input"] / per
    output_usd = usage["output_tokens"] * rates["output"] / per
    cache_read_usd = usage["cache_read_input_tokens"] * rates["cache_read"] / per
    cache_write_usd = usage["cache_creation_input_tokens"] * rates["cache_write"] / per
    return {
        "input_usd": input_usd,
        "output_usd": output_usd,
        "cache_read_usd": cache_read_usd,
        "cache_write_usd": cache_write_usd,
        "total_usd": input_usd + output_usd + cache_read_usd + cache_write_usd,
    }


def extract(
    paper_text: str,
    schema: Schema | dict | list,
    *,
    paper_id: str | None = None,
    tables: list | None = None,
    model: str = DEFAULT_MODEL,
    api_key: str | None = None,
    age_rules: AgeBoundRules | None = None,
) -> ExtractionResult:
    """Convenience one-shot wrapper."""
    return MetaExtractor(model=model, api_key=api_key, age_rules=age_rules).extract(
        paper_text=paper_text, schema=schema, paper_id=paper_id, tables=tables
    )
