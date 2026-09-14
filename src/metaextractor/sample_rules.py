"""Deterministic post-extraction rules applied to per-sample records.

Two rules live here, and both record what they did in
``ExtractionResult.sample_provenance`` (one ``{field: source}`` dict per sample):

* :func:`fan_out_fields_to_samples` — propagates study- and subgroup-level field
  values into sample rows, **only when the value is known to apply to that
  sample** (see the function docstring for the exact scoping rules).
* :func:`normalize_age_bounds` — fills per-subject ``age_min``/``age_max`` from a
  per-sample age or an age-group definition. It is **off unless configured**
  with :class:`AgeBoundRules`, and it only touches fields the target schema
  declares.

Source descriptors used in ``sample_provenance``:

``table:<table>:<column>`` / ``manifest:<table>:<column>``
    copied from a supplementary table / SRA-ENA run manifest cell
``llm_sample``
    emitted by the model as a per-sample value
``subgroup_fanout:<label>`` / ``study_fanout``
    propagated by :func:`fan_out_fields_to_samples`
``age_rule:specific_age`` / ``age_rule:age_group:<group>``
    derived by :func:`normalize_age_bounds`
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from metaextractor.output import ExtractionResult
from metaextractor.schema import Schema

PROPAGATED_PREFIXES = ("study_fanout", "subgroup_fanout")

_AGGREGATE_RE = re.compile(
    r"±|\+/-|\bmeans?\b|\bmedians?\b|\bs\.?d\.?\b|\biqr\b|\brange\b|\baverage\b"
    r"|\bn\s*=|\d\s*(?:-|–|—|to)\s*\d",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Value helpers
# ---------------------------------------------------------------------------


def is_nr(v: Any) -> bool:
    """Empty, None, or a case-variant of ``not_reported`` / ``not reported``."""
    if v is None:
        return True
    if isinstance(v, (list, dict)):
        return not v
    if isinstance(v, str):
        return v.strip().lower().replace(" ", "_") in ("", "not_reported")
    return False


def is_multi_valued(v: Any) -> bool:
    """A list of several items, or a ``;``/``|``-delimited string of several items."""
    if isinstance(v, (list, tuple, set)):
        return len([x for x in v if not is_nr(x)]) > 1
    if isinstance(v, str):
        return len([p for p in re.split(r"[;|]", v) if p.strip()]) > 1
    return False


def is_aggregate(v: Any) -> bool:
    """A cohort summary statistic (mean/median/SD/IQR/range/±/n=) rather than a value."""
    if isinstance(v, (list, tuple, set)):
        return any(is_aggregate(x) for x in v)
    return isinstance(v, str) and bool(_AGGREGATE_RE.search(v))


def stringify(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        return "; ".join(str(x) for x in v)
    return str(v)


def _normalize_subgroup(label: str) -> str:
    """Case- and plural-insensitive subgroup label ("mothers" ~ "Mother")."""
    s = label.strip().lower()
    if s.endswith("s") and len(s) > 1:
        s = s[:-1]
    return s


def ensure_provenance(result: ExtractionResult, default: str | None = None) -> None:
    """Make ``sample_provenance`` parallel to ``samples``.

    Missing entries are created; when ``default`` is given, every already
    reported cell without a recorded source is attributed to it.
    """
    prov = list(result.sample_provenance)
    prov += [{} for _ in range(len(result.samples) - len(prov))]
    prov = prov[: len(result.samples)]
    if default is not None:
        for s, p in zip(result.samples, prov):
            for k, v in s.items():
                if k not in p and not k.startswith("__") and not is_nr(v):
                    p[k] = default
    result.sample_provenance = prov


# ---------------------------------------------------------------------------
# Fan-out
# ---------------------------------------------------------------------------


def fan_out_fields_to_samples(result: ExtractionResult, schema: Schema | None = None) -> Counter:
    """Propagate study/subgroup field values into sample rows, conservatively.

    Values already present on a sample (e.g. from a table) are never
    overwritten. For each unfilled field on a sample:

    1. **Subgroup value.** The sample's subgroup is identified by matching its
       string values against ``result.subgroups`` (case/plural-insensitive).
       The match must be **unique** — a sample whose values match several
       subgroups gets none. When the field has a value for that subgroup, it is
       written, unless the field is not ``study``-scoped and the value is
       multi-valued or an aggregate statistic.
    2. **Study value**, depending on the field's schema ``scope``:

       * ``"study"`` — written as-is (the value describes every sample).
       * ``"sample"`` — written only when it is a single, non-aggregate value,
         the result declares no subgroups, and the field has no per-subgroup
         values (i.e. the model described a homogeneous cohort).
       * unset — written only when it is a single, non-aggregate value.

    A cohort list such as ``"Healthy; Hypertension; Pre-hypertension"`` or an
    aggregate such as ``"45 ± 12"`` is therefore never copied onto individual
    samples as if it were their own value.

    Returns a counter of written cells by rule and of blocked propagations.
    """
    counts: Counter = Counter()
    if not result.samples or not result.fields:
        return counts
    ensure_provenance(result)
    scope = {f.name: f.scope for f in schema.fields} if schema is not None else {}
    subgroup_norm = {_normalize_subgroup(s): s for s in (result.subgroups or [])}

    def sample_subgroup(sample: dict) -> str | None:
        found = {subgroup_norm[_normalize_subgroup(v)] for v in sample.values()
                 if isinstance(v, str) and _normalize_subgroup(v) in subgroup_norm}
        if len(found) > 1:
            counts["ambiguous_subgroup_samples"] += 1
            return None
        return next(iter(found), None)

    for sample, prov in zip(result.samples, result.sample_provenance):
        sg = sample_subgroup(sample)
        for fname, fr in result.fields.items():
            if not is_nr(sample.get(fname)):
                continue
            fscope = scope.get(fname)
            if sg and fr.by_subgroup and sg in fr.by_subgroup and not is_nr(fr.by_subgroup[sg]):
                v = fr.by_subgroup[sg]
                if fscope != "study" and (is_multi_valued(v) or is_aggregate(v)):
                    counts["blocked_subgroup_value"] += 1
                    continue
                sample[fname] = stringify(v)
                prov[fname] = f"subgroup_fanout:{sg}"
                counts["subgroup_fanout"] += 1
                continue
            v = fr.value
            if is_nr(v):
                continue
            if fscope != "study":
                if is_multi_valued(v):
                    counts["blocked_multi_valued"] += 1
                    continue
                if is_aggregate(v):
                    counts["blocked_aggregate"] += 1
                    continue
                if fscope == "sample" and (result.subgroups or fr.by_subgroup):
                    counts["blocked_sample_scope"] += 1
                    continue
            sample[fname] = stringify(v)
            prov[fname] = "study_fanout"
            counts["study_fanout"] += 1
    return counts


# ---------------------------------------------------------------------------
# Age bounds
# ---------------------------------------------------------------------------


DEFAULT_AGE_UNIT_TO_YEARS: dict[str, float] = {
    "year": 1.0, "years": 1.0, "yr": 1.0, "yrs": 1.0, "y": 1.0,
    "month": 12.0, "months": 12.0, "mo": 12.0,
    "week": 52.1775, "weeks": 52.1775, "wk": 52.1775,
    "day": 365.25, "days": 365.25, "d": 365.25,
}


@dataclass
class AgeBoundRules:
    """Configuration for :func:`normalize_age_bounds`.

    ``age_fields`` maps each per-subject age field to the field carrying its
    unit (``None`` = the field is already in years). ``group_bounds`` maps an
    age-group label to ``(min, max)`` in years; either bound may be ``None``
    (left unset). ``justification`` documents where the bounds come from.
    """

    min_field: str = "age_min"
    max_field: str = "age_max"
    age_fields: dict[str, str | None] = field(default_factory=lambda: {"age": "age_unit"})
    group_field: str | None = "age_group"
    group_bounds: dict[str, tuple[float | None, float | None]] = field(default_factory=dict)
    unit_to_years: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_AGE_UNIT_TO_YEARS))
    assume_years_when_unit_missing: bool = True
    justification: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AgeBoundRules":
        kw: dict[str, Any] = {k: d[k] for k in (
            "min_field", "max_field", "age_fields", "group_field",
            "assume_years_when_unit_missing", "justification") if k in d}
        if "group_bounds" in d:
            kw["group_bounds"] = {g: (b[0], b[1]) for g, b in d["group_bounds"].items()}
        if "unit_to_years" in d:
            kw["unit_to_years"] = {k.lower(): float(v) for k, v in d["unit_to_years"].items()}
        return cls(**kw)

    @classmethod
    def from_json(cls, path: str | Path) -> "AgeBoundRules":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def _num(v: Any) -> float | None:
    if is_nr(v):
        return None
    try:
        return float(str(v).strip())
    except ValueError:
        return None


def _fmt_age(x: float) -> str:
    """Whole numbers render as ints ('18'); fractional values keep up to 4 decimals."""
    return str(int(x)) if float(x).is_integer() else f"{x:.4f}".rstrip("0")


def normalize_age_bounds(
    result: ExtractionResult, rules: AgeBoundRules | None, schema: Schema | None = None
) -> int:
    """Fill ``age_min``/``age_max`` per the configured rules. Returns cells written.

    No-op when ``rules`` is ``None`` or when ``schema`` is given and does not
    declare both bound fields. Rules, per **sample** row:

    * A per-sample age (the first configured age field with a numeric value
      that was *not* propagated from a study/subgroup value, whose unit converts
      to years) sets **both** bounds to that age, as the cMD schema defines
      ("for specific age information, age_min and age_max are identical").
      If the age's unit is unknown, the row is left untouched.
    * Otherwise, when neither bound is numeric and the row's age group has
      configured bounds, the bounds are set from the group definition
      (a ``None`` bound is left unset).
    * Otherwise (a reported range) the row is left as-is.

    At the **study level** only the age-group rule applies, and only to bound
    fields the model already emitted; a study-level age may be a cohort summary
    and is never converted into individual bounds.
    """
    if rules is None:
        return 0
    declared = {f.name for f in schema.fields} if schema is not None else None
    if declared is not None and not {rules.min_field, rules.max_field} <= declared:
        return 0
    ensure_provenance(result)
    written = 0

    def to_years(value: float, unit: Any) -> float | None:
        if is_nr(unit):
            return value if rules.assume_years_when_unit_missing else None
        div = rules.unit_to_years.get(str(unit).strip().lower())
        return value / div if div else None

    def group_bounds(group: Any):
        if not isinstance(group, str) or rules.group_field is None:
            return None
        return rules.group_bounds.get(group.strip())

    for sample, prov in zip(result.samples, result.sample_provenance):
        spec: float | None = None
        unknown_unit = False
        for af, unit_field in rules.age_fields.items():
            if declared is not None and af not in declared:
                continue
            if str(prov.get(af, "")).startswith(PROPAGATED_PREFIXES):
                continue
            v = _num(sample.get(af))
            if v is None:
                continue
            years = to_years(v, sample.get(unit_field)) if unit_field else v
            if years is None:
                unknown_unit = True
                continue
            spec = years
            break
        if spec is not None:
            want = _fmt_age(spec)
            for b in (rules.min_field, rules.max_field):
                cur = _num(sample.get(b))
                if cur is None or abs(cur - spec) > 1e-9:
                    sample[b] = want
                    prov[b] = "age_rule:specific_age"
                    written += 1
            continue
        if unknown_unit:
            continue
        if _num(sample.get(rules.min_field)) is None and _num(sample.get(rules.max_field)) is None:
            gb = group_bounds(sample.get(rules.group_field)) if rules.group_field else None
            if gb:
                for b, val in zip((rules.min_field, rules.max_field), gb):
                    if val is None:
                        continue
                    sample[b] = _fmt_age(float(val))
                    prov[b] = f"age_rule:age_group:{sample.get(rules.group_field).strip()}"
                    written += 1

    # Study level: group rule only, onto already-emitted bound fields.
    fmin, fmax = result.fields.get(rules.min_field), result.fields.get(rules.max_field)
    fgroup = result.fields.get(rules.group_field) if rules.group_field else None
    if fmin is not None and fmax is not None and fgroup is not None:
        if _num(fmin.value) is None and _num(fmax.value) is None:
            gb = group_bounds(fgroup.value)
            if gb:
                for fr, val in zip((fmin, fmax), gb):
                    if val is None:
                        continue
                    fr.value = _fmt_age(float(val))
                    fr.extraction_type = "derived"
                    note = f"[set from age_group '{str(fgroup.value).strip()}' definition]"
                    fr.notes = f"{fr.notes} {note}" if fr.notes else note
                    written += 1
    return written


__all__ = [
    "AgeBoundRules",
    "DEFAULT_AGE_UNIT_TO_YEARS",
    "ensure_provenance",
    "fan_out_fields_to_samples",
    "is_aggregate",
    "is_multi_valued",
    "is_nr",
    "normalize_age_bounds",
]
