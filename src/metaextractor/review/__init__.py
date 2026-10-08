"""Human review of extractions: self-contained HTML packets and their verdicts.

Gold is imperfect and a draft for a study with no gold has no automatic score at
all, so some questions can only be answered by a person reading the paper. This
subpackage turns an :class:`~metaextractor.output.ExtractionResult` into one
self-contained HTML file a reviewer can open and fill in, and turns what they
return into an aggregate.

Two modes, one renderer. They differ only in what counts as a unit:

* **draft** — every extracted value is a unit. No gold is involved, which is what
  makes it usable on studies outside the benchmark.
* **adjudication** — units are sampled scored cells (``FP``, ``TP_wrong``, ``FN``,
  plus blinded ``TP_correct`` controls) shown against the source, which is the
  design in ``evaluation/extensions/PLAN.md``.

Reviewer verdicts are pinned to the draft by SHA-256 and are never mixed with the
held-out gold.

Nothing here imports the scoring modules at module level, so the review package
stays outside the gold firewall guarded by ``tests/test_gold_firewall.py``;
:mod:`metaextractor.review.report` imports ``evaluation`` lazily, inside the one
function that needs a cell decision type.
"""
from __future__ import annotations

from metaextractor.review.packet import PacketMeta, build_packet, draft_sha256
from metaextractor.review.report import ReviewReport, aggregate_verdicts, cohens_kappa
from metaextractor.review.verdicts import (
    VerdictError,
    VerdictFile,
    load_verdicts,
    validate_verdicts,
    verdict_schema,
)

__all__ = [
    "PacketMeta",
    "build_packet",
    "draft_sha256",
    "ReviewReport",
    "aggregate_verdicts",
    "cohens_kappa",
    "VerdictError",
    "VerdictFile",
    "load_verdicts",
    "validate_verdicts",
    "verdict_schema",
]
