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

from metaextractor.output import ExtractionResult
from metaextractor.prompts import SYSTEM_PROMPT, build_user_content
from metaextractor.schema import Field, Schema

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 16384
DEFAULT_BATCH_SIZE = 30

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
    ):
        self.client = client or Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
        self.model = model
        self.max_tokens = max_tokens
        self.batch_size = batch_size
        self.sample_discovery = sample_discovery
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
    ) -> ExtractionResult:
        schema_obj = schema if isinstance(schema, Schema) else Schema.from_dict(schema)
        self.last_usage = {k: 0 for k in self.last_usage}

        sample_ids: list[str] | None = None
        if self.sample_discovery and "--- SUPPLEMENTARY FILE:" in paper_text:
            sample_ids = self._discover_sample_ids(paper_text, paper_id)

        if len(schema_obj.fields) <= self.batch_size:
            result = self._extract_one(paper_text, schema_obj, paper_id, sample_ids)
            if sample_ids:
                result.extraction_warnings.insert(
                    0, f"Sample discovery identified {len(sample_ids)} samples; "
                       f"per-batch extraction was constrained to these IDs."
                )
            return result

        batches = [
            Schema(fields=schema_obj.fields[i : i + self.batch_size])
            for i in range(0, len(schema_obj.fields), self.batch_size)
        ]
        results = [self._extract_one(paper_text, b, paper_id, sample_ids) for b in batches]
        merged = _merge_results(results, sample_ids=sample_ids)
        if sample_ids:
            merged.extraction_warnings.insert(
                0, f"Sample discovery identified {len(sample_ids)} samples; "
                   f"per-batch extraction was constrained to these IDs."
            )
        return merged

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
    model: str = DEFAULT_MODEL,
    api_key: str | None = None,
) -> ExtractionResult:
    """Convenience one-shot wrapper."""
    return MetaExtractor(model=model, api_key=api_key).extract(
        paper_text=paper_text, schema=schema, paper_id=paper_id
    )
