"""Evaluate a MetaExtractor :class:`ExtractionResult` against a gold-standard
table (one row per sample, columns = field names).

The evaluator answers three orthogonal questions for every (sample, field) cell:

1. **Reporting** — did the extractor attempt this field at all? Classified as
   ``TN`` (both NR), ``FN`` (gold reported, extracted NR), ``FP`` (gold NR,
   extracted reported), or ``TP`` (both reported).
2. **Value correctness** — for ``TP`` cells, does the extracted value equal
   the gold value? Strings compared after lowercasing and stripping; numbers
   compared with relative tolerance after optional unit normalization.
3. **Faithfulness** — does each non-NR claim carry an ``evidence_quote`` and
   does that quote appear verbatim in the paper text? (The latter check
   requires the paper text to be supplied.)

Results are returned as a structured :class:`EvaluationResult` that callers
can read programmatically or render via :meth:`EvaluationResult.summary`.

Surface-form synonyms (e.g. ``QIAamp ↔ Qiagen``) are intentionally **not**
handled here — they would obscure real differences between extractor output
and the curator's encoding. Resolve those upstream with an ontology
crosswalk or a per-field normalization layer.
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Mapping

from metaextractor.output import ExtractionResult

Decision = Literal["TN", "TP_correct", "TP_wrong", "FN", "FP"]

NR_TOKENS: frozenset[str] = frozenset({"not_reported", "na", "n/a", "", "none", "null"})
DEFAULT_NUMERIC_TOLERANCE: float = 0.05  # 5% relative

#: Default month-→year normalization recipe. Maps a unit token (lowercased)
#: to a divisor that converts it into years. Extend if your schema uses
#: other time units.
DEFAULT_UNIT_TO_YEARS: Mapping[str, float] = {
    "month": 12.0,
    "months": 12.0,
    "day": 365.25,
    "days": 365.25,
    "week": 52.0,
    "weeks": 52.0,
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CellResult:
    """One (sample, field) comparison."""
    sample_idx: int
    ext_sample_id: str | None
    gold_sample_id: str | None
    field: str
    extracted: Any
    gold: Any
    decision: Decision


@dataclass
class FieldMetrics:
    """Confusion-matrix counts for a single field (or aggregated subset)."""
    label: str
    tn: int = 0
    tp_correct: int = 0
    tp_wrong: int = 0
    fn: int = 0
    fp: int = 0

    def add(self, decision: Decision) -> None:
        setattr(self, _DECISION_ATTR[decision], getattr(self, _DECISION_ATTR[decision]) + 1)

    @property
    def n(self) -> int:
        return self.tn + self.tp_correct + self.tp_wrong + self.fn + self.fp

    @property
    def tp(self) -> int:
        return self.tp_correct + self.tp_wrong

    @property
    def precision(self) -> float | None:
        d = self.tp + self.fp
        return self.tp / d if d else None

    @property
    def recall(self) -> float | None:
        d = self.tp + self.fn
        return self.tp / d if d else None

    @property
    def f1(self) -> float | None:
        p, r = self.precision, self.recall
        if p is None or r is None or (p + r) == 0:
            return None
        return 2 * p * r / (p + r)

    @property
    def value_accuracy(self) -> float | None:
        """Fraction of attempted-by-both cells where the value matched."""
        return self.tp_correct / self.tp if self.tp else None

    @property
    def total_accuracy(self) -> float | None:
        """Fraction of all cells that are correct (TP_correct or TN)."""
        return (self.tp_correct + self.tn) / self.n if self.n else None


_DECISION_ATTR: dict[Decision, str] = {
    "TN": "tn", "TP_correct": "tp_correct", "TP_wrong": "tp_wrong",
    "FN": "fn", "FP": "fp",
}


@dataclass
class FaithfulnessReport:
    """Tier-D checks that don't depend on the gold table."""
    contract_violations: list[dict[str, Any]] = field(default_factory=list)
    evidence_checked: int = 0
    evidence_matched: int = 0

    @property
    def evidence_match_rate(self) -> float | None:
        if not self.evidence_checked:
            return None
        return self.evidence_matched / self.evidence_checked


@dataclass
class EvaluationResult:
    per_field: dict[str, FieldMetrics]
    per_cell: list[CellResult]
    by_extraction_type: dict[str, FieldMetrics]
    by_confidence: dict[str, FieldMetrics]
    aggregate: FieldMetrics
    faithfulness: FaithfulnessReport

    # --- rendering ---------------------------------------------------------

    def summary(self, *, max_mismatches: int = 20) -> str:
        """Return a human-readable text report."""
        lines = []
        lines.append("=" * 84)
        lines.append("MetaExtractor evaluation")
        lines.append("=" * 84)
        lines.append("")
        lines.append("## Tier A+B  Per-field reporting + value correctness")
        lines.append("")
        lines.append("  TN = both NR (correct abstention)")
        lines.append("  TPc = both reported, values match  /  TPw = both reported, mismatch")
        lines.append("  FN = gold reported, extracted NR (omission)")
        lines.append("  FP = gold NR, extracted reported (over-claim)")
        lines.append("")
        for fm in self.per_field.values():
            lines.append("  " + _format_row(fm))
        lines.append("")
        lines.append("  " + _format_row(self.aggregate))
        lines.append("")

        if self.by_extraction_type:
            lines.append("## Tier C  Stratification by extraction_type (study-level)")
            lines.append("")
            for fm in self.by_extraction_type.values():
                lines.append("  " + _format_row(fm))
            lines.append("")

        if self.by_confidence:
            lines.append("## Tier C  Stratification by confidence band")
            lines.append("")
            for band in ("high", "medium", "low"):
                if band in self.by_confidence:
                    lines.append("  " + _format_row(self.by_confidence[band]))
            lines.append("")

        lines.append("## Tier D  Faithfulness / contract violations")
        lines.append("")
        rate = self.faithfulness.evidence_match_rate
        if rate is not None:
            lines.append(
                f"  evidence_quote verbatim match: "
                f"{self.faithfulness.evidence_matched}/{self.faithfulness.evidence_checked} "
                f"= {rate:.2%}"
            )
        else:
            lines.append("  (evidence-quote check skipped: no paper text provided)")
        lines.append(f"  contract violations: {len(self.faithfulness.contract_violations)}")
        for v in self.faithfulness.contract_violations[:8]:
            lines.append(f"    - {v['field']}: {v['issue']} "
                         f"(value={v['value']!r}, extraction_type={v['extraction_type']})")
        if len(self.faithfulness.contract_violations) > 8:
            lines.append(f"    … +{len(self.faithfulness.contract_violations) - 8} more")
        lines.append("")

        flagged = [c for c in self.per_cell if c.decision in ("TP_wrong", "FN", "FP")]
        lines.append(f"## Mismatches (TPw + FN + FP, first {max_mismatches} of {len(flagged)})")
        lines.append("")
        for c in flagged[:max_mismatches]:
            lines.append(
                f"  [{c.decision:<10}] sample={c.sample_idx:>2}  "
                f"field={c.field:<22} "
                f"ext={str(c.extracted)[:30]!r:<32} gold={str(c.gold)[:30]!r}"
            )
        lines.append("")
        return "\n".join(lines)

    def to_cells_tsv(self, path: str | Path) -> None:
        """Write per-cell results as a tab-separated table for downstream review."""
        rows = [
            {
                "sample_idx": c.sample_idx,
                "ext_sample_id": c.ext_sample_id,
                "gold_sample_id": c.gold_sample_id,
                "field": c.field,
                "extracted": c.extracted,
                "gold": c.gold,
                "decision": c.decision,
            }
            for c in self.per_cell
        ]
        with open(path, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), delimiter="\t")
            w.writeheader()
            w.writerows(rows)


# ---------------------------------------------------------------------------
# Comparators
# ---------------------------------------------------------------------------


def is_not_reported(value: Any) -> bool:
    """Treat ``None``, empty containers, and conventional NR strings as NR."""
    if value is None:
        return True
    if isinstance(value, list) and not value:
        return True
    if isinstance(value, str) and value.strip().lower() in NR_TOKENS:
        return True
    return False


def _normalize_string(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(sorted(str(x).strip().lower() for x in value))
    return str(value).strip().lower()


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _convert_to_years(value: float, unit: str | None, unit_to_years: Mapping[str, float]) -> float:
    if unit is None:
        return value
    divisor = unit_to_years.get(unit.strip().lower())
    return value / divisor if divisor else value


def values_match(
    extracted: Any,
    gold: Any,
    *,
    numeric_tolerance: float = DEFAULT_NUMERIC_TOLERANCE,
    ext_unit: str | None = None,
    gold_unit: str | None = None,
    unit_to_years: Mapping[str, float] = DEFAULT_UNIT_TO_YEARS,
) -> bool:
    """Strict equality after type-aware normalization.

    Numeric values are compared with relative tolerance after converting
    to a common base unit (years, when ``ext_unit``/``gold_unit`` are
    supplied). String values are compared after lowercasing, stripping, and
    sorting (for lists). No synonym table — surface-form differences are
    reported as ``TP_wrong``.
    """
    e_num, g_num = _to_float(extracted), _to_float(gold)
    if e_num is not None and g_num is not None:
        e_num = _convert_to_years(e_num, ext_unit, unit_to_years)
        g_num = _convert_to_years(g_num, gold_unit, unit_to_years)
        if g_num == 0:
            return abs(e_num) < 1e-9
        return abs(e_num - g_num) / max(abs(g_num), 1e-9) <= numeric_tolerance

    return _normalize_string(extracted) == _normalize_string(gold)


def classify_cell(
    extracted: Any,
    gold: Any,
    *,
    numeric_tolerance: float = DEFAULT_NUMERIC_TOLERANCE,
    ext_unit: str | None = None,
    gold_unit: str | None = None,
    unit_to_years: Mapping[str, float] = DEFAULT_UNIT_TO_YEARS,
) -> Decision:
    e_nr, g_nr = is_not_reported(extracted), is_not_reported(gold)
    if e_nr and g_nr:
        return "TN"
    if e_nr:
        return "FN"
    if g_nr:
        return "FP"
    matched = values_match(
        extracted, gold,
        numeric_tolerance=numeric_tolerance,
        ext_unit=ext_unit, gold_unit=gold_unit,
        unit_to_years=unit_to_years,
    )
    return "TP_correct" if matched else "TP_wrong"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def evaluate(
    extraction: ExtractionResult | Mapping[str, Any],
    gold_rows: list[Mapping[str, Any]],
    field_map: Mapping[str, str],
    *,
    paper_text: str | None = None,
    numeric_tolerance: float = DEFAULT_NUMERIC_TOLERANCE,
    unit_fields: Mapping[str, str] | None = None,
    unit_to_years: Mapping[str, float] = DEFAULT_UNIT_TO_YEARS,
    skip_fields: set[str] | None = None,
    count_missing_gold_as_fn: bool = False,
) -> EvaluationResult:
    """Compare an extraction result against gold rows aligned by position.

    Parameters
    ----------
    extraction:
        ``ExtractionResult`` (pydantic) or the equivalent dict.
    gold_rows:
        Sequence of dicts, one per sample. Must be ordered to align
        positionally with ``extraction.samples``. Use
        :func:`load_gold_tsv` for cMD-style TSVs.
    field_map:
        Mapping from extractor field names to gold column names. Only
        fields present in this map are evaluated.
    paper_text:
        If supplied, each non-empty ``evidence_quote`` is checked for a
        verbatim substring match in the paper text (Tier-D faithfulness).
    numeric_tolerance:
        Relative tolerance for numeric comparisons (default 5%).
    unit_fields:
        For numeric fields whose value depends on a unit, names the
        companion field that carries the unit string. Example:
        ``{"age_max": "age_unit", "age_min": "age_unit"}``.
    unit_to_years:
        Crosswalk from unit token → divisor that converts the value to
        years. Override for non-time units.
    skip_fields:
        Field names to skip entirely (e.g. constructed identifiers whose
        formats are not directly comparable to gold).
    count_missing_gold_as_fn:
        By default the positional join scores only the overlap
        ``min(n_extracted, n_gold)``, so gold rows the extraction never
        produced (an under- or un-enumerated study) are silently excluded
        from the denominator rather than penalized. When ``True``, scoring
        ranges over *all* gold rows: each gold row with no corresponding
        extracted sample contributes a cell per field, counted as ``FN``
        where gold reported a value and ``TN`` where it did not. This yields
        a **coverage-aware recall** that reflects per-sample enumeration
        coverage. Precision/FP are unaffected — a missing (phantom) sample
        asserts nothing, so it can only add ``FN``/``TN``, never ``FP``.
        Study-level fan-out is *not* applied to phantom rows: a sample the
        extraction never enumerated is treated as reporting nothing.
    """
    data = extraction.model_dump() if isinstance(extraction, ExtractionResult) else dict(extraction)
    samples: list[dict[str, Any]] = list(data.get("samples", []))
    study_fields: dict[str, Any] = data.get("fields", {})
    skip_fields = skip_fields or set()
    unit_fields = unit_fields or {}

    n_overlap = min(len(samples), len(gold_rows))
    # Default: score only the overlap (positional join). With
    # ``count_missing_gold_as_fn`` we range over every gold row so that
    # un/under-enumerated samples count as FN rather than being dropped.
    n = len(gold_rows) if count_missing_gold_as_fn else n_overlap

    per_field: dict[str, FieldMetrics] = {f: FieldMetrics(label=f) for f in field_map}
    per_cell: list[CellResult] = []
    by_extype: dict[str, FieldMetrics] = defaultdict(lambda: FieldMetrics(label=""))
    by_conf: dict[str, FieldMetrics] = defaultdict(lambda: FieldMetrics(label=""))

    for i in range(n):
        # ``sample is None`` marks a phantom row: a gold sample the extraction
        # never enumerated (only reachable when count_missing_gold_as_fn=True).
        # It reports nothing — no study-level fan-out — so every gold-reported
        # cell becomes FN.
        sample = samples[i] if i < len(samples) else None
        gold = gold_rows[i]
        for ef, gf in field_map.items():
            if ef in skip_fields:
                continue
            ev = _per_sample_value(study_fields, sample, ef) if sample is not None else None
            gv = gold.get(gf)

            kw: dict[str, Any] = {}
            if ef in unit_fields:
                ucol = unit_fields[ef]
                sv = sample.get(ucol) if sample is not None else None
                ext_u = sv if isinstance(sv, str) else None
                gold_u = gold.get(ucol)
                if gold_u in (None, "NA", ""):
                    gold_u = None
                kw = {"ext_unit": ext_u, "gold_unit": gold_u}

            decision = classify_cell(
                ev, gv, numeric_tolerance=numeric_tolerance,
                unit_to_years=unit_to_years, **kw,
            )
            per_field[ef].add(decision)
            per_cell.append(CellResult(
                sample_idx=i,
                ext_sample_id=_as_str(sample.get("sample_id")) if sample is not None else None,
                gold_sample_id=_as_str(gold.get("sample_id")),
                field=ef,
                extracted=ev,
                gold=gv,
                decision=decision,
            ))

            meta = study_fields.get(ef)
            if meta is not None:
                et = meta.get("extraction_type")
                cf = meta.get("confidence")
                if et:
                    by_extype[et].label = et
                    by_extype[et].add(decision)
                if cf:
                    by_conf[cf].label = cf
                    by_conf[cf].add(decision)

    aggregate = FieldMetrics(label="[AGGREGATE micro]")
    for fm in per_field.values():
        aggregate.tn += fm.tn
        aggregate.tp_correct += fm.tp_correct
        aggregate.tp_wrong += fm.tp_wrong
        aggregate.fn += fm.fn
        aggregate.fp += fm.fp

    faithfulness = _faithfulness_checks(study_fields, paper_text)

    return EvaluationResult(
        per_field=per_field,
        per_cell=per_cell,
        by_extraction_type=dict(by_extype),
        by_confidence=dict(by_conf),
        aggregate=aggregate,
        faithfulness=faithfulness,
    )


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------


def load_gold_tsv(path: str | Path) -> list[dict[str, str]]:
    """Load a tab-separated gold table (one row per sample) as a list of dicts."""
    with open(path) as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def load_extraction(path: str | Path) -> ExtractionResult:
    """Load an extraction result JSON and validate it against the schema."""
    return ExtractionResult.model_validate_json(Path(path).read_text())


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _per_sample_value(study_fields: Mapping[str, Any], sample: Mapping[str, Any], field: str) -> Any:
    """Sample value wins; fall back to study-level so each sample inherits study facts."""
    if field in sample:
        return sample[field]
    study = study_fields.get(field)
    return study.get("value") if isinstance(study, Mapping) else None


def _faithfulness_checks(study_fields: Mapping[str, Any], paper_text: str | None) -> FaithfulnessReport:
    report = FaithfulnessReport()
    paper_lc = paper_text.lower() if paper_text else None

    for fname, f in study_fields.items():
        if not isinstance(f, Mapping):
            continue
        value = f.get("value")
        evidence = (f.get("evidence_quote") or "").strip()
        et = f.get("extraction_type")

        if not is_not_reported(value) and not evidence:
            report.contract_violations.append({
                "field": fname,
                "issue": "non-NR value without evidence_quote",
                "extraction_type": et,
                "value": value,
            })

        if paper_lc and evidence:
            report.evidence_checked += 1
            if evidence.lower() in paper_lc:
                report.evidence_matched += 1

    return report


def _as_str(v: Any) -> str | None:
    return str(v) if v is not None else None


def _format_row(fm: FieldMetrics) -> str:
    def fmt(x: float | None) -> str:
        return f"{x:.2f}" if x is not None else " nan"
    return (
        f"{fm.label:<22} N={fm.n:<3} TN={fm.tn:<3} TPc={fm.tp_correct:<3} TPw={fm.tp_wrong:<3} "
        f"FN={fm.fn:<3} FP={fm.fp:<3}  P={fmt(fm.precision)} R={fmt(fm.recall)} "
        f"F1={fmt(fm.f1)} valAcc={fmt(fm.value_accuracy)} totalAcc={fmt(fm.total_accuracy)}"
    )


__all__ = [
    "CellResult",
    "FieldMetrics",
    "FaithfulnessReport",
    "EvaluationResult",
    "evaluate",
    "values_match",
    "classify_cell",
    "is_not_reported",
    "load_gold_tsv",
    "load_extraction",
    "DEFAULT_NUMERIC_TOLERANCE",
    "DEFAULT_UNIT_TO_YEARS",
]
