"""Identity alignment of extracted sample records to gold rows.

Positional scoring (sample *i* ↔ gold row *i*) cannot establish that a value is
compared against the same physical sample. :func:`align_by_identity` instead
joins records on a shared identifier and **only accepts one-to-one matches**:

* Each identifier cell is split into a token set (``"SRR1; SRR2"`` →
  ``{"SRR1", "SRR2"}``), so pooled accessions are represented explicitly
  rather than truncated to their first token.
* A key candidate may be compound — ``"subject_id+body_site+timepoint"`` — when
  a single column does not identify a sample (e.g. subjects with several
  timepoints or body sites). A compound token requires every part to be present.
* A gold row is **matched** when its tokens hit exactly one extracted record,
  that record is hit by no other gold row, and no token is shared by several
  extracted records.
* A gold row whose tokens hit several extracted records is **pooled** when each
  token identifies a distinct record (one gold row = several deposited runs), or
  **ambiguous** when a token is duplicated across extracted records or several
  gold rows claim the same record. Neither is silently resolved.
* Among the candidate keys, the one yielding the most one-to-one matches is used
  for the whole study (ties go to the earlier candidate).

The result carries full diagnostics — matched, unmatched, pooled, ambiguous,
duplicate keys, and extra extracted records with/without a key — so that
end-to-end metrics can count unmatched gold rows as misses and extra records can
be reported separately.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

NR_KEY_TOKENS = frozenset({"", "na", "nan", "none", "null", "not_reported", "n/a"})
_SPLIT = re.compile(r"[;,\s]+")


def _cell(v: Any) -> Any:
    if isinstance(v, dict) and "value" in v:
        return v.get("value")
    return v


def _atoms(v: Any) -> set[str]:
    """Split one identifier cell into its non-empty tokens."""
    v = _cell(v)
    if v is None:
        return set()
    items = v if isinstance(v, (list, tuple, set)) else [v]
    out: set[str] = set()
    for item in items:
        for tok in _SPLIT.split(str(item).strip()):
            if tok and tok.lower() not in NR_KEY_TOKENS:
                out.add(tok)
    return out


def key_tokens(row: Mapping[str, Any], key: str) -> set[str]:
    """Token set for ``row`` under a single or ``+``-compound ``key``."""
    parts = [p.strip() for p in key.split("+") if p.strip()]
    if len(parts) == 1:
        return _atoms(row.get(parts[0]))
    values = []
    for p in parts:
        raw = _cell(row.get(p))
        s = "" if raw is None else str(raw).strip()
        if s.lower() in NR_KEY_TOKENS:
            return set()
        values.append(s)
    return {"\x1f".join(values)}


def parse_key_candidates(key: str | Iterable[str]) -> list[str]:
    """Accept ``"a,b+c"`` or ``["a", "b+c"]``; return the ordered candidates."""
    items = key.split(",") if isinstance(key, str) else list(key)
    return [k.strip() for k in items if k and k.strip()]


@dataclass
class AlignmentResult:
    """Outcome of aligning one study's extracted records to its gold rows."""

    key_used: str | None
    n_gold: int
    n_ext: int
    #: (gold_idx, ext_idx) one-to-one pairs, in gold order.
    pairs: list[tuple[int, int]] = field(default_factory=list)
    unmatched_gold: list[int] = field(default_factory=list)
    pooled_gold: list[int] = field(default_factory=list)
    ambiguous_gold: list[int] = field(default_factory=list)
    #: Extracted records whose key token is shared with another extracted record.
    duplicate_ext_records: int = 0
    #: Extracted records not paired, with a key that no gold row references
    #: (e.g. deposited runs outside the curated subset).
    unmatched_ext_with_key: int = 0
    #: Extracted records not paired and carrying no usable key value.
    unmatched_ext_without_key: int = 0
    #: Extracted records referenced by a gold row but left unpaired
    #: (pooled or ambiguous).
    ext_in_conflict: int = 0
    #: One-to-one match count for every candidate key that was tried.
    candidate_matches: dict[str, int] = field(default_factory=dict)

    @property
    def matched(self) -> int:
        return len(self.pairs)

    def end_to_end_lists(
        self, gold_rows: Sequence[Mapping[str, Any]], ext_samples: Sequence[Mapping[str, Any]]
    ) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any] | None]]:
        """All gold rows, with the paired extracted record or ``None``.

        Passing these to :func:`metaextractor.evaluation.evaluate` scores every
        gold row: an unmatched, pooled, or ambiguous gold row reports nothing,
        so each of its gold-populated cells is a false negative.
        """
        by_gold = dict(self.pairs)
        return list(gold_rows), [ext_samples[by_gold[g]] if g in by_gold else None
                                 for g in range(len(gold_rows))]

    def matched_lists(
        self, gold_rows: Sequence[Mapping[str, Any]], ext_samples: Sequence[Mapping[str, Any]]
    ) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
        """Only the one-to-one matched pairs (conditional scoring)."""
        return ([gold_rows[g] for g, _ in self.pairs],
                [ext_samples[e] for _, e in self.pairs])

    def to_dict(self) -> dict[str, Any]:
        return {
            "key_used": self.key_used,
            "n_gold": self.n_gold,
            "n_ext": self.n_ext,
            "matched": self.matched,
            "unmatched_gold": len(self.unmatched_gold),
            "pooled_gold": len(self.pooled_gold),
            "ambiguous_gold": len(self.ambiguous_gold),
            "duplicate_ext_records": self.duplicate_ext_records,
            "unmatched_ext_with_key": self.unmatched_ext_with_key,
            "unmatched_ext_without_key": self.unmatched_ext_without_key,
            "ext_in_conflict": self.ext_in_conflict,
            "candidate_matches": dict(self.candidate_matches),
        }


def _align_on(
    ext_samples: Sequence[Mapping[str, Any]], gold_rows: Sequence[Mapping[str, Any]], key: str
) -> AlignmentResult:
    ext_tokens = [key_tokens(s, key) for s in ext_samples]
    token_to_ext: dict[str, set[int]] = {}
    for i, toks in enumerate(ext_tokens):
        for t in toks:
            token_to_ext.setdefault(t, set()).add(i)
    dup_ext = {i for idxs in token_to_ext.values() if len(idxs) > 1 for i in idxs}

    res = AlignmentResult(key_used=key, n_gold=len(gold_rows), n_ext=len(ext_samples),
                          duplicate_ext_records=len(dup_ext))
    candidate: dict[int, int] = {}  # gold_idx -> ext_idx
    referenced: set[int] = set()
    for g, row in enumerate(gold_rows):
        toks = key_tokens(row, key)
        hit_sets = [token_to_ext[t] for t in toks if t in token_to_ext]
        hits = set().union(*hit_sets) if hit_sets else set()
        referenced |= hits
        if not hits:
            res.unmatched_gold.append(g)
        elif any(len(s) > 1 for s in hit_sets):
            res.ambiguous_gold.append(g)
        elif len(hits) > 1:
            res.pooled_gold.append(g)
        else:
            candidate[g] = next(iter(hits))

    claims: dict[int, list[int]] = {}
    for g, e in candidate.items():
        claims.setdefault(e, []).append(g)
    for e, gs in claims.items():
        if len(gs) == 1:
            res.pairs.append((gs[0], e))
        else:
            res.ambiguous_gold.extend(gs)
    res.pairs.sort()
    res.ambiguous_gold.sort()

    paired_ext = {e for _, e in res.pairs}
    for i, toks in enumerate(ext_tokens):
        if i in paired_ext:
            continue
        if i in referenced:
            res.ext_in_conflict += 1
        elif toks:
            res.unmatched_ext_with_key += 1
        else:
            res.unmatched_ext_without_key += 1
    return res


def align_by_identity(
    ext_samples: Sequence[Mapping[str, Any]],
    gold_rows: Sequence[Mapping[str, Any]],
    key_candidates: str | Iterable[str],
) -> AlignmentResult:
    """Align extracted records to gold rows one-to-one on a shared identifier.

    ``key_candidates`` is an ordered list (or comma-separated string) of single
    or ``+``-compound column names. Every candidate is tried; the one with the
    most one-to-one matches is used for the whole study (then the one with the
    most gold rows referencing any record, so pooled/ambiguous diagnostics are
    kept). When no candidate references any record, ``key_used`` is ``None``
    and every gold row is unmatched.
    """
    candidates = parse_key_candidates(key_candidates)
    best: AlignmentResult | None = None
    best_rank = (0, 0)
    tried: dict[str, int] = {}
    for key in candidates:
        r = _align_on(ext_samples, gold_rows, key)
        tried[key] = r.matched
        # Rank by one-to-one matches, then by gold rows that hit any record
        # (so a key whose only overlaps are pooled/ambiguous keeps its diagnostics).
        rank = (r.matched, r.matched + len(r.pooled_gold) + len(r.ambiguous_gold))
        if rank > best_rank:
            best, best_rank = r, rank
    if best is None:
        with_key = sum(1 for s in ext_samples if any(key_tokens(s, k) for k in candidates))
        best = AlignmentResult(
            key_used=None, n_gold=len(gold_rows), n_ext=len(ext_samples),
            unmatched_gold=list(range(len(gold_rows))),
            unmatched_ext_with_key=with_key,
            unmatched_ext_without_key=len(ext_samples) - with_key,
        )
    best.candidate_matches = tried
    return best


__all__ = ["AlignmentResult", "align_by_identity", "key_tokens", "parse_key_candidates"]
