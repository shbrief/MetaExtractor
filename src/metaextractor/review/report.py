"""Aggregate reviewer verdicts into the numbers a paper can cite.

Three things come out of a set of verdict files:

* **Per-field and overall support rates** — of the units a reviewer judged, what
  fraction the source bore out. This is the figure that can stand in for an
  accuracy claim on studies with no gold.
* **Inter-reviewer agreement** — Cohen's κ over the units two reviewers both
  judged, which is what makes a support rate more than one person's opinion.
* **What was not judged** — counted and reported, never imputed. An unjudged unit
  is not agreement.

Deliberate choices
------------------

``cannot_determine`` is held apart from both the numerator and the denominator of
the support rate, and reported on its own line. It is the honest answer when a
value lives in a supplement retrieval never fetched, and folding it into either
side would turn a retrieval limitation into an accuracy claim. The rate is
therefore over *determinable* units, with the abstention rate beside it.

κ is reported with its observed and expected agreement, and suppressed with a
stated reason when the overlap is too small or degenerate (one category used by
both reviewers makes κ undefined, not 1.0).
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from dataclasses import field as dc_field
from itertools import combinations

from metaextractor.review.verdicts import VerdictFile

#: Verdicts that count as the source bearing the extraction out.
SUPPORTING = frozenset({"supported"})
#: Verdicts that count against it. ``gold_wrong`` is *not* here: it says the
#: extraction was right and the curated value was not.
REFUTING = frozenset({"unsupported", "wrong_value"})
#: Held out of the rate entirely, and reported separately.
ABSTAIN = frozenset({"cannot_determine"})


@dataclass
class KappaResult:
    """Cohen's κ for one pair of reviewers, or the reason there isn't one."""

    reviewer_a: str
    reviewer_b: str
    n_overlap: int
    kappa: float | None = None
    observed_agreement: float | None = None
    expected_agreement: float | None = None
    note: str | None = None


@dataclass
class ReviewReport:
    """Everything aggregated from a set of verdict files."""

    n_files: int = 0
    reviewers: list[str] = dc_field(default_factory=list)
    drafts: list[str] = dc_field(default_factory=list)
    modes: list[str] = dc_field(default_factory=list)
    counts: Counter = dc_field(default_factory=Counter)
    per_field: dict[str, Counter] = dc_field(default_factory=dict)
    kappas: list[KappaResult] = dc_field(default_factory=list)
    #: Units the packet offered, **per draft**. Coverage is measured against this
    #: times the number of verdict files, since each file is one reviewer's pass
    #: over one draft -- two reviewers judging 23 units each is 46 judgments of a
    #: possible 46, not 46 of 23.
    n_units_total: int | None = None

    @property
    def n_judged(self) -> int:
        """Judgments recorded, summed over reviewers."""
        return sum(self.counts.values())

    @property
    def n_expected(self) -> int | None:
        """Judgments there would be if every reviewer judged every unit."""
        if self.n_units_total is None:
            return None
        return self.n_units_total * max(self.n_files, 1)

    @property
    def n_unjudged(self) -> int | None:
        """Judgments not recorded. Never negative: a reviewer cannot judge a unit
        twice, so an excess means ``n_units_total`` was miscounted, and the
        summary says so rather than printing a negative number."""
        if self.n_expected is None:
            return None
        return max(0, self.n_expected - self.n_judged)

    @property
    def n_determinable(self) -> int:
        return sum(n for v, n in self.counts.items() if v in SUPPORTING | REFUTING)

    @property
    def support_rate(self) -> float | None:
        """Supported / determinable. ``None`` when nothing was determinable."""
        d = self.n_determinable
        if not d:
            return None
        return sum(n for v, n in self.counts.items() if v in SUPPORTING) / d

    @property
    def abstention_rate(self) -> float | None:
        """``cannot_determine`` / judged — how often the evidence did not settle it."""
        if not self.n_judged:
            return None
        return sum(n for v, n in self.counts.items() if v in ABSTAIN) / self.n_judged

    def summary(self) -> str:
        """A plain-text report, in the style of ``evaluation.EvaluationResult.summary``."""
        L: list[str] = []
        L.append("=== HUMAN REVIEW ===")
        L.append(f"files      : {self.n_files}")
        L.append(f"reviewers  : {', '.join(self.reviewers) or '-'}")
        L.append(f"drafts     : {', '.join(d[:12] for d in self.drafts) or '-'}")
        L.append(f"modes      : {', '.join(self.modes) or '-'}")
        if self.n_units_total is not None:
            L.append(f"units      : {self.n_units_total} per draft, "
                     f"{self.n_files} reviewer pass(es) -> {self.n_expected} possible")
            L.append(f"judged     : {self.n_judged} "
                     f"({self.n_unjudged} unjudged, reported as unjudged)")
            if self.n_judged > self.n_expected:
                L.append("             [warning: more judgments than units x passes; "
                         "the unit count given does not match these files]")
        else:
            L.append(f"judged     : {self.n_judged}")
        L.append("")
        for v in ("supported", "unsupported", "wrong_value", "cannot_determine",
                  "gold_wrong"):
            if self.counts.get(v):
                L.append(f"  {v:<18} {self.counts[v]}")
        L.append("")
        sr, ar = self.support_rate, self.abstention_rate
        L.append(f"support rate    : {'n/a' if sr is None else f'{sr:.3f}'} "
                 f"(supported / determinable, n={self.n_determinable})")
        L.append(f"abstention rate : {'n/a' if ar is None else f'{ar:.3f}'} "
                 "(cannot_determine / judged)")
        if self.counts.get("gold_wrong"):
            L.append(f"gold disputed   : {self.counts['gold_wrong']} unit(s) where the "
                     "reviewer judged the extraction right and the curated value wrong")

        if self.per_field:
            L.append("")
            L.append(f"{'field':<34}{'n':>5}{'supported':>11}{'rate':>8}")
            for name, c in sorted(self.per_field.items()):
                det = sum(n for v, n in c.items() if v in SUPPORTING | REFUTING)
                sup = sum(n for v, n in c.items() if v in SUPPORTING)
                rate = f"{sup / det:.3f}" if det else "-"
                L.append(f"{name[:33]:<34}{sum(c.values()):>5}{sup:>11}{rate:>8}")

        if self.kappas:
            L.append("")
            L.append("=== AGREEMENT ===")
            for k in self.kappas:
                if k.kappa is None:
                    L.append(f"  {k.reviewer_a} vs {k.reviewer_b}: no kappa "
                             f"(n={k.n_overlap}) — {k.note}")
                else:
                    L.append(f"  {k.reviewer_a} vs {k.reviewer_b}: kappa={k.kappa:.3f} "
                             f"(n={k.n_overlap}, observed={k.observed_agreement:.3f}, "
                             f"expected={k.expected_agreement:.3f})")
        return "\n".join(L)


def cohens_kappa(a: dict[str, str], b: dict[str, str], *,
                 min_overlap: int = 10) -> KappaResult:
    """Cohen's κ over the units both reviewers judged.

    Returns a result carrying ``kappa=None`` and a stated ``note`` rather than a
    misleading number when the overlap is too small, or when both reviewers used
    a single category (which makes expected agreement 1.0 and κ undefined — not
    perfect agreement).
    """
    shared = sorted(set(a) & set(b))
    n = len(shared)
    res = KappaResult(reviewer_a="a", reviewer_b="b", n_overlap=n)
    if n < min_overlap:
        res.note = f"fewer than {min_overlap} shared units"
        return res

    agree = sum(1 for u in shared if a[u] == b[u])
    po = agree / n
    ca, cb = Counter(a[u] for u in shared), Counter(b[u] for u in shared)
    pe = sum((ca[k] / n) * (cb[k] / n) for k in set(ca) | set(cb))
    res.observed_agreement = po
    res.expected_agreement = pe
    if abs(1.0 - pe) < 1e-12:
        res.note = ("both reviewers used a single category, so expected agreement is "
                    "1.0 and kappa is undefined")
        return res
    res.kappa = (po - pe) / (1.0 - pe)
    return res


def _field_of(unit_id: str) -> str:
    """Field name from a unit id (``field:x``, ``sample:3:x``, ``cell:3:x``)."""
    parts = unit_id.split(":")
    return parts[-1] if len(parts) > 1 else unit_id


def aggregate_verdicts(files: list[VerdictFile], *,
                       n_units_total: int | None = None,
                       min_overlap: int = 10) -> ReviewReport:
    """Aggregate verdict files into a :class:`ReviewReport`.

    Args:
        files: validated verdict files, from :func:`~.verdicts.load_verdicts`.
        n_units_total: how many units the packet offered, so unjudged units can be
            counted rather than ignored.
        min_overlap: below this many shared units, κ is reported as unavailable.
    """
    rep = ReviewReport(n_files=len(files), n_units_total=n_units_total)
    rep.reviewers = sorted({f.reviewer for f in files})
    rep.drafts = sorted({f.draft_sha256 for f in files})
    rep.modes = sorted({f.mode for f in files})

    per_field: dict[str, Counter] = defaultdict(Counter)
    for f in files:
        for uid, entry in f.verdicts.items():
            v = entry.get("verdict")
            rep.counts[v] += 1
            per_field[_field_of(uid)][v] += 1
    rep.per_field = dict(per_field)

    by_reviewer: dict[str, dict[str, str]] = defaultdict(dict)
    for f in files:
        for uid, entry in f.verdicts.items():
            # Namespace by draft so the same unit id in two drafts is not conflated.
            by_reviewer[f.reviewer][f"{f.draft_sha256}:{uid}"] = entry.get("verdict")

    for ra, rb in combinations(sorted(by_reviewer), 2):
        k = cohens_kappa(by_reviewer[ra], by_reviewer[rb], min_overlap=min_overlap)
        k.reviewer_a, k.reviewer_b = ra, rb
        rep.kappas.append(k)

    return rep
