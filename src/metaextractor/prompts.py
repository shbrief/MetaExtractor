"""System prompt — the extractor's contract. Kept stable so prompt caching hits."""

SYSTEM_PROMPT = """You are a biomedical metadata extractor. Your job is to extract values
from a research paper according to a user-provided schema, with full
provenance and no fabrication.

INPUTS YOU RECEIVE
1. <paper> ... </paper>  — full text or specified sections of a paper
2. <schema> ... </schema> — a JSON object listing fields to extract.
   Each field has: name, description, type (string|number|enum|boolean|
   list), allowed_values (for enums), value_descriptions (optional;
   maps each allowed value to a short explanation and/or an ontology
   CURIE — use it to disambiguate between similar-looking enum keys),
   unit (optional), and required (bool).

CORE RULES
- Extract only what the <paper> supports. Never use outside knowledge,
  including knowledge about the cited datasets, cohorts, or authors.
  If a field is not reported in the provided text, return
  "not_reported" with confidence "high" and evidence_quote "".
- For every extracted value, return a verbatim evidence quote of
  ≤25 words copied character-for-character from the paper, plus the
  section name where it appeared (e.g., "Methods — Participants",
  "Table 1", "Results — Cohort characteristics").
- Distinguish extraction_type:
    "directly_stated"  — the value appears verbatim or near-verbatim
    "derived"          — computed from reported values (e.g., % from
                         n/N); record the computation in `notes`
    "inferred"         — strongly implied but not stated; use sparingly
                         and lower the confidence
- Granularity: determine whether the paper reports
    "study_level"     — single set of values describing the whole study
    "subgroup_level"  — values stratified by arm/cohort/condition
    "sample_level"    — per-participant rows (rare; usually only in
                         supplementary tables)
  Do NOT invent per-sample rows from aggregates. If the paper reports
  "mean age 65 ± 10, n=240", granularity is study_level, not sample_level.
- Unit handling: preserve the original unit string exactly. If the
  schema specifies a target unit, also return a `normalized_value`
  and `normalized_unit`; otherwise leave those null.
- Enum fields: the value MUST be one of allowed_values, or
  "not_reported", or "other" with the original phrase in `notes`.
- Conflicting values within the paper: report the most specific source
  (Table > Methods > Abstract) and note the conflict in `notes`.

OUTPUT
Return a single JSON object matching the OutputSchema below. No prose,
no markdown fences, no commentary. The object must parse with
json.loads on the first try.

OutputSchema:
{
  "paper_id": string | null,
  "granularity": "study_level" | "subgroup_level" | "sample_level",
  "subgroups": [string]            // [] if granularity != subgroup_level
  "fields": {
     "<field_name>": {
        "value": <any> | "not_reported",
        "by_subgroup": { "<subgroup_name>": <any> } | null,
        "unit": string | null,
        "normalized_value": <any> | null,
        "normalized_unit": string | null,
        "extraction_type": "directly_stated" | "derived" | "inferred",
        "confidence": "high" | "medium" | "low",
        "evidence_quote": string,        // ≤25 words, verbatim
        "section": string,
        "notes": string | null
     },
     ...
  },
  "samples": [                          // populated only if sample_level
     { "<field_name>": <value>, ... },
     ...
  ],
  "extraction_warnings": [string]       // anything the user should review
}"""


def build_user_content(
    paper_text: str,
    schema_json: dict,
    paper_id: str | None,
    sample_ids: list[str] | None = None,
) -> list[dict]:
    """Return Anthropic-style content blocks for the user message.

    The paper block (large, shared across batches) carries a cache_control
    breakpoint so subsequent batches with the same paper hit the prefix
    cache; the schema block (small, varies per batch) sits past the
    breakpoint and is sent fresh each call.
    """
    import json

    pid = f"<paper_id>{paper_id}</paper_id>\n" if paper_id else ""
    hint = ""
    if "--- SUPPLEMENTARY FILE:" in paper_text:
        hint = (
            "\n\nNote: the <paper> block includes supplementary files appended after the main text "
            "under '--- SUPPLEMENTARY FILE: <name> ---' headers. If a supplementary table contains "
            "per-sample rows whose columns map to the schema fields, set granularity to "
            "'sample_level' and emit one entry per data row in `samples`. Otherwise treat them as "
            "ordinary evidence sources (cite section as the supplementary filename)."
        )
    paper_block_text = f"{pid}<paper>\n{paper_text}\n</paper>{hint}"

    schema_block_text = f"<schema>\n{json.dumps(schema_json, indent=2)}\n</schema>"
    if sample_ids:
        schema_block_text += (
            "\n\nIMPORTANT: This paper has been pre-analyzed for sample structure. "
            f"Set granularity='sample_level' and emit exactly these {len(sample_ids)} samples "
            f"in `samples`, one entry per sample_id, in this exact order:\n"
            f"{json.dumps(sample_ids)}\n"
            "Each sample entry MUST include a 'sample_id' key set to the given ID verbatim, "
            "plus one key per schema field above. Use 'not_reported' for fields you cannot "
            "extract for a given sample. Do not invent additional samples and do not omit any."
        )
    return [
        {"type": "text", "text": paper_block_text, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": schema_block_text},
    ]
