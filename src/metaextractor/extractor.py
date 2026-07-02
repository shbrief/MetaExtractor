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
from metaextractor.schema import Field, Schema
from metaextractor.table_plan import (
    PlanExecutionError,
    PlanProposalError,
    execute_plan,
    propose_plan,
)
from metaextractor.table_select import score_table

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 16384
DEFAULT_BATCH_SIZE = 30
DEFAULT_MIN_TABLE_RELEVANCE = 0.15

# USD per 1M tokens. Cache read / write follow Anthropic's standard 5m
# ephemeral multipliers (0.1x / 1.25x of base input). Update as needed.
PRICING_USD_PER_MTOK: dict[str, dict[str, float]] = {
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
    ):
        self.client = client or Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
        self.model = model
        self.max_tokens = max_tokens
        self.batch_size = batch_size
        self.sample_discovery = sample_discovery
        self.min_table_relevance = min_table_relevance
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

        if result.granularity == "sample_level" and result.samples and result.fields:
            n = _fan_out_fields_to_samples(result)
            if n:
                result.extraction_warnings.append(
                    f"Fanned out {n} cell(s) of study/subgroup-level field values "
                    f"into per-sample rows."
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
            result = self._extract_one(paper_text, discovery_schema, paper_id, None)
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
    ) -> ExtractionResult:
        user_content = build_user_content(
            paper_text, schema_obj.to_prompt_json(), paper_id, sample_ids=sample_ids
        )

        with self.client.messages.stream(
            model=self.model,
            max_tokens=self.max_tokens,
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

        u = response.usage
        self.last_usage["input_tokens"] += getattr(u, "input_tokens", 0) or 0
        self.last_usage["cache_creation_input_tokens"] += getattr(u, "cache_creation_input_tokens", 0) or 0
        self.last_usage["cache_read_input_tokens"] += getattr(u, "cache_read_input_tokens", 0) or 0
        self.last_usage["output_tokens"] += getattr(u, "output_tokens", 0) or 0
        self.last_usage["n_calls"] += 1

        raw = "".join(block.text for block in response.content if block.type == "text").strip()
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
        """Table → sample-rows pipeline.

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
        if not tables:
            return [], [], []
        schema_field_names = [f.name for f in schema.fields]
        warnings: list[str] = []
        selections: list[TableSelection] = []
        # (name, rows, relevance): relevance is retained so the join can anchor
        # on the most schema-relevant sample table (see the sort before join_tables).
        scored_tables: list[tuple[str, list[dict], float]] = []

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
                plan, usage = propose_plan(self.client, self.model, t, schema_field_names)
                _accumulate_usage(self.last_usage, usage)
                transformed = execute_plan(t, plan)
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


def _normalize_subgroup(label: str) -> str:
    """Compare subgroup labels case- and plural-insensitively.

    Matches "mothers" (LLM subgroup) to "Mother" (table sample_type) and
    similar variants. Conservative — only strips a trailing 's'.
    """
    s = label.strip().lower()
    if s.endswith("s") and len(s) > 1:
        s = s[:-1]
    return s


def _stringify_field_value(v: Any) -> str:
    """Render a study/subgroup field value for insertion into a sample row."""
    if v is None:
        return ""
    if isinstance(v, list):
        return "; ".join(str(x) for x in v)
    return str(v)


def _fan_out_fields_to_samples(result: ExtractionResult) -> int:
    """Propagate study-level and subgroup-level field values into each sample.

    Per-sample values already present (from the supplementary-table path)
    take precedence — they're more specific than the LLM's prose-derived
    study/subgroup assignments. For each unfilled field on a sample:

      - If the sample's subgroup can be identified (by matching one of its
        string values against ``result.subgroups`` with plural- and case-
        insensitive comparison) AND the field has a value for that
        subgroup, that value is written.
      - Otherwise the field's study-level value is written, when present
        and not ``not_reported``.

    Returns the number of (sample, field) cells written.
    """
    if not result.samples or not result.fields:
        return 0

    subgroup_norm: dict[str, str] = {
        _normalize_subgroup(s): s for s in (result.subgroups or [])
    }

    def _sample_subgroup(sample: dict) -> str | None:
        for v in sample.values():
            if isinstance(v, str):
                norm = _normalize_subgroup(v)
                if norm in subgroup_norm:
                    return subgroup_norm[norm]
        return None

    def _is_nr(v: Any) -> bool:
        """A value counts as not-reported when it is empty, None, or any
        case-variant of the literal 'not_reported' / 'not reported' token."""
        if v is None:
            return True
        if isinstance(v, (list, dict)):
            return not v
        if isinstance(v, str):
            s = v.strip().lower().replace(" ", "_")
            return s in ("", "not_reported")
        return False

    n_written = 0
    for sample in result.samples:
        sg = _sample_subgroup(sample)
        for fname, field in result.fields.items():
            if not _is_nr(sample.get(fname)):
                continue
            value: str | None = None
            if sg and field.by_subgroup and sg in field.by_subgroup:
                v = field.by_subgroup[sg]
                if not _is_nr(v):
                    value = _stringify_field_value(v)
            if value is None and not _is_nr(field.value):
                value = _stringify_field_value(field.value)
            if value is not None:
                sample[fname] = value
                n_written += 1
    return n_written


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
) -> ExtractionResult:
    """Convenience one-shot wrapper."""
    return MetaExtractor(model=model, api_key=api_key).extract(
        paper_text=paper_text, schema=schema, paper_id=paper_id, tables=tables
    )
