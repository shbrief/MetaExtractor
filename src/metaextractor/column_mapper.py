"""Deterministic lexical column → schema-field mapping.

Four-tier confidence cascade. The first tier that matches wins; unmapped
source columns are returned untouched so a downstream semantic mapper
(e.g. MetaHarmonizer's SchemaMapper) can take a second pass.

Tiers, in order:
  1. exact (case-insensitive)
  2. normalized exact (strip non-alphanum, lowercase, collapse separators)
  3. curated alias dictionary
  4. fuzzy ratio ≥ ``fuzzy_threshold`` (rapidfuzz; default 90)

No semantic embeddings. No value normalization. No transforms. Columns
that don't pass any tier are returned as-is in ``unmapped``.

This module is intentionally schema-agnostic: the caller passes the list
of schema field names. A small built-in alias dict covers obvious
biomedical synonyms (gender↔sex, pmid↔pmid, …) and can be extended or
replaced per-schema by the caller.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

try:
    from rapidfuzz import fuzz
    _HAS_RAPIDFUZZ = True
except ImportError:
    _HAS_RAPIDFUZZ = False


DEFAULT_FUZZY_THRESHOLD = 90

# Hand-curated biomedical aliases. Keys are *source* header names
# (post-normalization); values are canonical schema field names. Keep
# small and conservative — anything ambiguous belongs to SchemaMapper.
DEFAULT_ALIASES: dict[str, str] = {
    "gender": "sex",
    "participant_sex": "sex",
    "participantsex": "sex",
    "subject_sex": "sex",
    "bodysite": "body_site",
    "body_site_name": "body_site",
    "anatomical_site": "body_site",
    "anatomicalsite": "body_site",
    "subjectid": "subject_id",
    "subject": "subject_id",
    "participant_id": "subject_id",
    "participantid": "subject_id",
    "sampleid": "sample_id",
    "sample": "sample_id",
    "specimen_id": "sample_id",
    "specimenid": "sample_id",
    "countrycode": "country",
    "nation": "country",
    "ncbi": "ncbi_accession",
    "sra_accession": "ncbi_accession",
    "sraaccession": "ncbi_accession",
    "bioproject": "ncbi_accession",
    "bioproject_id": "ncbi_accession",
    "pmid_id": "pmid",
    "pubmed_id": "pmid",
    "pubmedid": "pmid",
    "diseasestate": "disease",
    "disease_status": "disease",
    "studyname": "study_name",
    "study": "study_name",
    "agegroup": "age_group",
    "age_at_collection": "age",
    "ageatcollection": "age",
    "ageyears": "age_years",
    "ageunit": "age_unit",
    "agemin": "age_min",
    "agemax": "age_max",
    "bodymassindex": "bmi",
    "body_mass_index": "bmi",
    "dnakit": "dna_extraction_kit",
    "extraction_kit": "dna_extraction_kit",
    "extractionkit": "dna_extraction_kit",
    "sequencing": "sequencing_platform",
    "platform": "sequencing_platform",
    "sequencer": "sequencing_platform",
    # SRA/ENA run-manifest column. Map the specific model (e.g. "Illumina HiSeq
    # 2000"), which is what cMD's sequencing_platform curates — not the generic
    # instrument_platform ("ILLUMINA"), which would win the collision by header
    # order and yield a less specific value.
    "instrument": "sequencing_platform",
    "instrument_model": "sequencing_platform",
    "instrumentmodel": "sequencing_platform",
    "treatmentname": "treatment",
    "smoking": "smoker",
    "smoking_status": "smoker",
    "isolation_source": "body_site",
    "westernised": "westernized",
}


@dataclass
class ColumnMapping:
    """Result of mapping one table's headers against a schema."""

    # source header → canonical schema field name (confidently mapped only)
    mapped: dict[str, str] = field(default_factory=dict)
    # source headers that did not pass any tier
    unmapped: list[str] = field(default_factory=list)
    # per-source-header note about which tier matched (for audit/debug)
    tier_used: dict[str, str] = field(default_factory=dict)
    # collisions: schema fields that multiple source headers matched to
    # (only the first/best is kept in ``mapped``; the rest go to unmapped)
    collisions: list[tuple[str, str]] = field(default_factory=list)


def _normalize(s: str) -> str:
    """Strip non-alphanum, collapse separators, lowercase. ``Sample-ID`` → ``sampleid``."""
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def map_columns(
    headers: list[str],
    schema_field_names: list[str],
    aliases: dict[str, str] | None = None,
    fuzzy_threshold: int = DEFAULT_FUZZY_THRESHOLD,
) -> ColumnMapping:
    """Map source headers to schema field names using lexical tiers 1-4.

    A schema field may be the target of at most one source header per
    table; later headers that would collide with an earlier mapping are
    recorded in ``collisions`` and remain in ``unmapped``.
    """
    aliases = aliases if aliases is not None else DEFAULT_ALIASES

    # Build lookup indexes once.
    field_by_lower: dict[str, str] = {f.lower(): f for f in schema_field_names}
    field_by_norm: dict[str, str] = {_normalize(f): f for f in schema_field_names}
    alias_by_norm: dict[str, str] = {_normalize(k): v for k, v in aliases.items()}
    fields_lower = [f.lower() for f in schema_field_names]

    result = ColumnMapping()
    taken_targets: set[str] = set()

    for header in headers:
        target: str | None = None
        tier: str | None = None

        h_lower = header.lower()
        h_norm = _normalize(header)

        # Tier 1: exact (case-insensitive)
        if h_lower in field_by_lower:
            target = field_by_lower[h_lower]
            tier = "exact"
        # Tier 2: normalized exact
        elif h_norm in field_by_norm:
            target = field_by_norm[h_norm]
            tier = "normalized"
        # Tier 3: curated alias dict
        elif h_norm in alias_by_norm:
            candidate = alias_by_norm[h_norm]
            # alias target must itself be a real schema field
            if candidate in schema_field_names:
                target = candidate
                tier = "alias"
        # Tier 4: fuzzy ratio ≥ threshold
        elif _HAS_RAPIDFUZZ:
            best_field, best_score = _best_fuzzy(h_lower, fields_lower, schema_field_names)
            if best_score >= fuzzy_threshold:
                target = best_field
                tier = f"fuzzy({best_score})"

        if target is None:
            result.unmapped.append(header)
            continue

        if target in taken_targets:
            result.collisions.append((header, target))
            result.unmapped.append(header)
            continue

        result.mapped[header] = target
        result.tier_used[header] = tier or ""
        taken_targets.add(target)

    return result


def _best_fuzzy(
    h_lower: str, fields_lower: list[str], fields_orig: list[str]
) -> tuple[str, float]:
    best_idx = -1
    best_score = -1.0
    for i, f in enumerate(fields_lower):
        score = fuzz.ratio(h_lower, f)
        if score > best_score:
            best_score = score
            best_idx = i
    return (fields_orig[best_idx] if best_idx >= 0 else "", best_score)


def apply_mapping(
    rows: list[dict[str, str]],
    mapping: ColumnMapping,
) -> list[dict[str, str]]:
    """Rename row keys per ``mapping.mapped``; unmapped columns kept verbatim.

    Output shape (a): one flat dict per row mixing canonical and original
    column names. Values pass through byte-exact.
    """
    rename = mapping.mapped
    out: list[dict[str, str]] = []
    for row in rows:
        new_row: dict[str, str] = {}
        for k, v in row.items():
            new_row[rename.get(k, k)] = v
        out.append(new_row)
    return out


# Canonical join-key priority. Earlier names win when multiple shared keys
# exist between two tables. ``sample_id`` is the most specific (per-sample
# row), then ``subject_id``, then ``ncbi_accession`` (per-library), then
# ``study_name`` (study-level constant; useful for broadcast joins).
DEFAULT_JOIN_KEY_PRIORITY: tuple[str, ...] = (
    "sample_id",
    "subject_id",
    "ncbi_accession",
    "study_name",
)

DEFAULT_OVERLAP_THRESHOLD = 0.9


@dataclass
class JoinPlan:
    """Records which table joined to which on which key, with overlap stats."""

    primary: str  # name of the anchor table
    joins: list[dict] = field(default_factory=list)
    # joins entries: {right: name, key: field, overlap: float, kept_rows: int}
    skipped: list[dict] = field(default_factory=list)
    # skipped entries: {right: name, reason: str}


def join_tables(
    mapped_tables: list[tuple[str, list[dict[str, str]]]],
    join_keys: tuple[str, ...] = DEFAULT_JOIN_KEY_PRIORITY,
    overlap_threshold: float = DEFAULT_OVERLAP_THRESHOLD,
) -> tuple[list[dict[str, str]], JoinPlan]:
    """Left-join a set of mapped tables on shared canonical key columns.

    Strategy:
      1. Pick a primary table — the first one that has the highest-priority
         join key. That table's rows anchor the output.
      2. For each remaining table, find the highest-priority join key that
         (a) exists in both tables and (b) has key-value overlap with the
         primary ≥ ``overlap_threshold``. Left-join on that key.
      3. Tables that share no usable key with the primary are skipped
         (their rows are not merged); they're recorded in
         ``JoinPlan.skipped`` so the caller can surface them.

    Conflicts on non-key columns: primary wins; the right-side value goes
    into ``__conflicts__`` on that row (a dict of conflicting column →
    right-side value) so curators can see disagreements.
    """
    if not mapped_tables:
        return [], JoinPlan(primary="")

    if len(mapped_tables) == 1:
        name, rows = mapped_tables[0]
        return list(rows), JoinPlan(primary=name)

    # Pick primary: table containing the highest-priority join key.
    primary_idx = _pick_primary(mapped_tables, join_keys)
    primary_name, primary_rows = mapped_tables[primary_idx]
    plan = JoinPlan(primary=primary_name)

    merged = [dict(r) for r in primary_rows]

    for i, (name, rows) in enumerate(mapped_tables):
        if i == primary_idx:
            continue
        key = _pick_shared_key(primary_rows, rows, join_keys)
        if key is None:
            plan.skipped.append({"right": name, "reason": "no shared canonical key"})
            continue
        overlap = _key_overlap(primary_rows, rows, key)
        if overlap < overlap_threshold:
            plan.skipped.append({
                "right": name,
                "reason": f"key {key!r} overlap {overlap:.2f} < {overlap_threshold}",
            })
            continue

        right_by_key: dict[str, dict[str, str]] = {}
        for r in rows:
            kv = r.get(key)
            if kv is None or kv == "":
                continue
            # First occurrence wins on the right side
            right_by_key.setdefault(str(kv), r)

        kept = 0
        for left in merged:
            kv = left.get(key)
            if kv is None or kv == "":
                continue
            right = right_by_key.get(str(kv))
            if right is None:
                continue
            kept += 1
            for k, v in right.items():
                if k == key:
                    continue
                if k in left and left[k] != v and left[k] not in ("", None):
                    left.setdefault("__conflicts__", {})[k] = v
                    continue
                left[k] = v

        plan.joins.append({
            "right": name,
            "key": key,
            "overlap": round(overlap, 3),
            "kept_rows": kept,
        })

    return merged, plan


def _pick_primary(
    mapped_tables: list[tuple[str, list[dict[str, str]]]],
    join_keys: tuple[str, ...],
) -> int:
    """Pick the index of the table whose available join keys rank highest."""
    best_idx = 0
    best_rank = len(join_keys)  # lower = better; len() = worst
    for i, (_name, rows) in enumerate(mapped_tables):
        if not rows:
            continue
        cols = set(rows[0].keys())
        for rank, k in enumerate(join_keys):
            if k in cols:
                if rank < best_rank:
                    best_rank = rank
                    best_idx = i
                break
    return best_idx


def _pick_shared_key(
    left: list[dict[str, str]],
    right: list[dict[str, str]],
    join_keys: tuple[str, ...],
) -> str | None:
    if not left or not right:
        return None
    lcols = set(left[0].keys())
    rcols = set(right[0].keys())
    for k in join_keys:
        if k in lcols and k in rcols:
            return k
    return None


def _key_overlap(
    left: list[dict[str, str]],
    right: list[dict[str, str]],
    key: str,
) -> float:
    """Fraction of left-side key values present in right side. 0 if either empty."""
    lvals = {str(r.get(key)) for r in left if r.get(key) not in (None, "")}
    rvals = {str(r.get(key)) for r in right if r.get(key) not in (None, "")}
    if not lvals:
        return 0.0
    return len(lvals & rvals) / len(lvals)
