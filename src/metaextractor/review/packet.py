"""Render one extraction as a self-contained HTML review packet.

:func:`build_packet` is a **pure function**: an extraction in, an HTML string
out. No network, no browser, no filesystem — so it is testable offline by
asserting on the returned string, which is how ``tests/test_review_packet.py``
checks it.

The HTML has no external references at all: CSS and JS are inline, there is no
CDN, no font, no image. A reviewer can be sent one file, open it offline, work
through it, and export a verdict JSON. Progress autosaves to ``localStorage``
keyed by the draft's SHA-256, so reloading does not lose work and opening a
*different* draft never shows another draft's answers.

What the packet is careful to represent honestly
------------------------------------------------

Two asymmetries in the data would be easy to paper over, and the packet shows
them as they are instead:

1. **Sample cells have no evidence quote.** ``FieldResult.evidence_quote`` is a
   study-level slot. A sample cell carries only a *source descriptor* string from
   ``sample_provenance``. So sample rows are presented with their source, not with
   a quote they do not have.
2. **That descriptor is column-level, not row-level.** ``last_table_sources`` maps
   a field to ``"table:<file>:<column>"`` once per run, so every sample shares one
   descriptor per field. The packet therefore says a value came from a named
   *column* of a named table — never from a row — because the row is not recorded.

Where a quote does exist, it is shown with a verbatim flag: whether that exact
string occurs in the paper text, when the paper text is supplied. That check is
:func:`metaextractor.evaluation` Tier-D logic, reimplemented here in two lines
rather than imported, so the review package stays clear of the gold firewall.
"""
from __future__ import annotations

import hashlib
import html
import json
from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Any

from metaextractor.output import ExtractionResult
from metaextractor.writers import cell_value

#: Verdicts offered for a unit. Kept in step with
#: ``schemas/review_verdict.schema.json``; ``gold_wrong`` is adjudication-only.
DRAFT_VERDICTS = ("supported", "unsupported", "wrong_value", "cannot_determine")
ADJUDICATION_VERDICTS = DRAFT_VERDICTS + ("gold_wrong",)

#: Rows of a sample table shown before the table is cut, to keep a packet openable.
MAX_SAMPLE_ROWS = 200


@dataclass
class PacketMeta:
    """Context shown in the packet header, none of it load-bearing for a verdict."""

    paper_id: str | None = None
    study: str | None = None
    model: str | None = None
    generated_utc: str | None = None
    #: Where the reviewer can read the source: a PMC or DOI URL per
    #: ``evaluation/extensions/PLAN.md`` decision 3(a), so adjudication measures
    #: whether the value is in the *paper*, not merely in what retrieval captured.
    source_links: dict[str, str] = dc_field(default_factory=dict)
    notes: str | None = None


def draft_sha256(result: ExtractionResult) -> str:
    """Stable digest of an extraction, used to pin a verdict file to its draft.

    Canonical JSON (sorted keys, no insignificant whitespace) so that the same
    extraction always hashes the same way regardless of how it was serialized.
    """
    payload = json.dumps(result.model_dump(mode="json"), sort_keys=True,
                         separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _is_absent(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, (list, dict)):
        return not v
    return isinstance(v, str) and v.strip().lower().replace(" ", "_") in ("", "not_reported")


def _render_value(v: Any) -> str:
    v = cell_value(v)
    if v is None:
        return ""
    if isinstance(v, list):
        return "; ".join(_render_value(x) for x in v)
    return str(v)


def _e(s: Any) -> str:
    """Escape for HTML text and attribute content."""
    return html.escape("" if s is None else str(s), quote=True)


# ---------------------------------------------------------------------------
# Unit collection
# ---------------------------------------------------------------------------

def _study_units(result: ExtractionResult, paper_text: str | None) -> list[dict]:
    """One unit per reported study-level field."""
    units = []
    for name, fr in result.fields.items():
        if _is_absent(fr.value):
            continue
        quote = fr.evidence_quote
        verbatim: bool | None = None
        if paper_text is not None and quote:
            verbatim = quote.strip() in paper_text
        units.append({
            "unit_id": f"field:{name}",
            "field": name,
            "value": _render_value(fr.value),
            "quote": quote,
            "section": fr.section,
            "extraction_type": fr.extraction_type,
            "confidence": fr.confidence,
            "unit": fr.unit,
            "notes": fr.notes,
            "by_subgroup": fr.by_subgroup,
            "verbatim": verbatim,
        })
    return units


def _sample_rows(result: ExtractionResult) -> tuple[list[str], list[dict]]:
    """Sample columns and rows, each cell carrying its source descriptor."""
    if not result.samples:
        return [], []
    cols: list[str] = []
    for s in result.samples:
        for k in s:
            if not k.startswith("__") and k not in cols:
                cols.append(k)
    prov = list(result.sample_provenance) + [{}] * (
        len(result.samples) - len(result.sample_provenance))
    rows = []
    for i, (s, p) in enumerate(zip(result.samples[:MAX_SAMPLE_ROWS], prov)):
        rows.append({
            "index": i,
            "cells": [{"field": c,
                       "value": _render_value(s.get(c)),
                       "source": (p or {}).get(c, "")}
                      for c in cols],
        })
    return cols, rows


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

_CSS = """
:root{--bg:#fdfdfc;--fg:#1a1a18;--muted:#6b6b65;--line:#e2e1dc;--card:#fff;
--warn:#8a5a00;--warnbg:#fff8e8;--ok:#1d6b3f;--bad:#9a2430;--accent:#2b5c8a}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.55 -apple-system,
BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:1040px;margin:0 auto;padding-block:24px;padding-left:16px;padding-right:16px}
h1{font-size:20px;margin:0 0 4px}h2{font-size:16px;margin:28px 0 10px;
padding-bottom:6px;border-bottom:1px solid var(--line)}
.banner{background:var(--warnbg);border:1px solid #e8d9b0;color:var(--warn);
border-radius:6px;padding:10px 12px;margin:0 0 18px;font-size:13px}
.meta{color:var(--muted);font-size:12.5px;margin:0 0 16px}
.meta a{color:var(--accent)}
.unit{background:var(--card);border:1px solid var(--line);border-radius:6px;
padding:12px 14px;margin:0 0 10px}
.unit h3{font-size:14px;margin:0 0 6px;font-family:ui-monospace,SFMono-Regular,
Menlo,monospace}
.val{font-weight:600;word-break:break-word}
.q{margin:8px 0 0;padding:8px 10px;background:#f7f7f5;border-left:3px solid var(--line);
font-size:13px;white-space:pre-wrap;word-break:break-word}
.tags{margin:7px 0 0;font-size:12px;color:var(--muted)}
.tag{display:inline-block;border:1px solid var(--line);border-radius:10px;
padding:1px 8px;margin:0 5px 4px 0}
.tag.ok{color:var(--ok);border-color:#bfe0cc}.tag.bad{color:var(--bad);border-color:#eccbcf}
.choices{margin:9px 0 0;display:flex;flex-wrap:wrap;gap:4px 14px}
.choices label{font-size:13px;cursor:pointer;white-space:nowrap}
.cmt{margin:8px 0 0;width:100%;font:13px/1.4 inherit;padding:6px 8px;
border:1px solid var(--line);border-radius:4px;background:#fff;color:var(--fg)}
.tblwrap{overflow-x:auto;border:1px solid var(--line);border-radius:6px;background:var(--card)}
table{border-collapse:collapse;width:100%;font-size:12.5px}
th,td{text-align:left;padding:6px 9px;border-bottom:1px solid var(--line);
vertical-align:top;white-space:nowrap}
th{background:#f7f7f5;position:sticky;top:0}
.src{color:var(--muted);font-family:ui-monospace,SFMono-Regular,Menlo,monospace;
font-size:11.5px}
.bar{position:sticky;bottom:0;background:var(--card);border-top:1px solid var(--line);
padding:10px 16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
button{font:13px inherit;padding:6px 12px;border:1px solid var(--line);
border-radius:5px;background:#fff;color:var(--fg);cursor:pointer}
button.primary{background:var(--accent);border-color:var(--accent);color:#fff}
#count{color:var(--muted);font-size:12.5px}
.sub{font-size:12.5px;color:var(--muted);margin:4px 0 0}
details{margin:0 0 10px}summary{cursor:pointer;font-size:13px;color:var(--muted)}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
--bg:#1b1b19;--fg:#ececea;--muted:#9b9b94;--line:#343431;--card:#232321;
--warnbg:#302a1c;--warn:#e0bd77;--ok:#78c79a;--bad:#e59aa4;--accent:#79aed8}
:root:not([data-theme="light"]) .q,:root:not([data-theme="light"]) th{background:#2a2a27}
:root:not([data-theme="light"]) .cmt,:root:not([data-theme="light"]) button{
background:#232321}}
"""

_JS = """
(function(){
  var KEY = 'mx-review:' + DRAFT.sha256;
  var saved = {};
  try { saved = JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch (e) { saved = {}; }

  function restore(){
    document.querySelectorAll('[data-unit]').forEach(function(box){
      var id = box.getAttribute('data-unit'), s = saved[id];
      if (!s) return;
      if (s.verdict){
        var r = box.querySelector('input[type=radio][value="' + s.verdict + '"]');
        if (r) r.checked = true;
      }
      var c = box.querySelector('textarea');
      if (c && s.comment) c.value = s.comment;
    });
    count();
  }

  function collect(){
    var out = [];
    document.querySelectorAll('[data-unit]').forEach(function(box){
      var id = box.getAttribute('data-unit');
      var r = box.querySelector('input[type=radio]:checked');
      var c = box.querySelector('textarea');
      var comment = c && c.value.trim() ? c.value.trim() : null;
      if (r || comment) out.push({unit_id: id, verdict: r ? r.value : 'cannot_determine',
                                  comment: comment});
    });
    return out;
  }

  function persist(){
    var m = {};
    collect().forEach(function(v){ m[v.unit_id] = {verdict: v.verdict, comment: v.comment}; });
    saved = m;
    try { localStorage.setItem(KEY, JSON.stringify(m)); } catch (e) {}
    count();
  }

  function count(){
    var n = document.querySelectorAll('input[type=radio]:checked').length;
    var t = document.querySelectorAll('[data-unit]').length;
    var el = document.getElementById('count');
    if (el) el.textContent = n + ' of ' + t + ' units judged' +
      (n < t ? ' \\u2014 unjudged units are reported as unjudged, not as agreement' : '');
  }

  document.addEventListener('change', persist);
  document.addEventListener('input', function(e){
    if (e.target && e.target.tagName === 'TEXTAREA') persist();
  });

  function download(){
    var payload = {
      schema_version: 1,
      draft_sha256: DRAFT.sha256,
      paper_id: DRAFT.paper_id,
      mode: DRAFT.mode,
      reviewer: (document.getElementById('reviewer').value || '').trim() || 'unnamed',
      finished_utc: new Date().toISOString().replace(/\\.\\d{3}Z$/, 'Z'),
      notes: (document.getElementById('rnotes').value || '').trim() || null,
      verdicts: collect()
    };
    var txt = JSON.stringify(payload, null, 2);
    var ta = document.getElementById('out');
    ta.value = txt; ta.hidden = false; ta.focus(); ta.select();
    try {
      if (navigator.clipboard) navigator.clipboard.writeText(txt);
    } catch (e) {}
    var a = document.createElement('a');
    a.href = 'data:application/json;charset=utf-8,' + encodeURIComponent(txt);
    a.download = 'verdict-' + (DRAFT.study || DRAFT.paper_id || 'draft') + '.json';
    document.body.appendChild(a); a.click(); a.remove();
  }

  document.getElementById('export').addEventListener('click', download);
  document.getElementById('clear').addEventListener('click', function(){
    if (!confirm('Discard every verdict recorded in this browser for this draft?')) return;
    try { localStorage.removeItem(KEY); } catch (e) {}
    document.querySelectorAll('input[type=radio]:checked').forEach(function(r){
      r.checked = false; });
    document.querySelectorAll('textarea.cmt').forEach(function(t){ t.value = ''; });
    saved = {}; count();
  });
  restore();
})();
"""


def _unit_box(unit: dict, choices: tuple[str, ...]) -> str:
    uid = _e(unit["unit_id"])
    out = [f'<div class="unit" data-unit="{uid}">']
    out.append(f'<h3>{_e(unit["field"])}</h3>')
    out.append(f'<div class="val">{_e(unit["value"]) or "<em>(empty)</em>"}</div>')

    if unit.get("gold") is not None:
        out.append(f'<div class="sub">curated value: <strong>{_e(unit["gold"])}</strong></div>')
    if unit.get("by_subgroup"):
        pairs = ", ".join(f"{_e(k)}: {_e(_render_value(v))}"
                          for k, v in unit["by_subgroup"].items())
        out.append(f'<div class="sub">by subgroup — {pairs}</div>')

    if unit.get("quote"):
        out.append(f'<p class="q">{_e(unit["quote"])}</p>')
    elif unit.get("source"):
        out.append(f'<div class="sub">source: <code>{_e(unit["source"])}</code> '
                   "(a column, not a row — the source row is not recorded)</div>")

    tags = []
    for key in ("section", "extraction_type", "confidence", "unit"):
        if unit.get(key):
            tags.append(f'<span class="tag">{_e(key)}: {_e(unit[key])}</span>')
    if unit.get("decision"):
        tags.append(f'<span class="tag">scored: {_e(unit["decision"])}</span>')
    if unit.get("verbatim") is True:
        tags.append('<span class="tag ok">quote found in the paper text</span>')
    elif unit.get("verbatim") is False:
        tags.append('<span class="tag bad">quote NOT found in the paper text</span>')
    if tags:
        out.append('<div class="tags">' + "".join(tags) + "</div>")

    radios = "".join(
        f'<label><input type="radio" name="{uid}" value="{_e(c)}"> {_e(c.replace("_", " "))}'
        "</label>" for c in choices)
    out.append(f'<div class="choices">{radios}</div>')
    out.append('<textarea class="cmt" rows="1" placeholder="comment (optional)"></textarea>')
    out.append("</div>")
    return "".join(out)


def build_packet(
    result: ExtractionResult,
    *,
    meta: PacketMeta | None = None,
    paper_text: str | None = None,
    cells: list[dict] | None = None,
    sample_fields: list[str] | None = None,
) -> str:
    """Render ``result`` as one self-contained HTML review packet.

    Args:
        result: the extraction to review.
        meta: header context — study, model, and source links for the reviewer.
        paper_text: when given, each evidence quote is substring-checked against
            it and the result shown as a flag. This is the Tier-D verbatim check.
        cells: adjudication mode. A list of scored cells, each
            ``{"sample_idx", "field", "extracted", "gold", "decision"}`` as
            produced by ``metaextractor.evaluation.CellResult``. When given, the
            units are these cells rather than every extracted value, and
            ``gold_wrong`` joins the verdict choices. Pass ``None`` for draft mode.
        sample_fields: restrict the sample table to these columns.

    Returns:
        A complete HTML document body as a string. No external references.
    """
    meta = meta or PacketMeta()
    sha = draft_sha256(result)
    mode = "adjudication" if cells is not None else "draft"
    choices = ADJUDICATION_VERDICTS if cells is not None else DRAFT_VERDICTS

    if cells is not None:
        units = []
        for c in cells:
            quote = None
            fr = result.fields.get(c["field"])
            if fr is not None and fr.evidence_quote:
                quote = fr.evidence_quote
            verbatim = None
            if paper_text is not None and quote:
                verbatim = quote.strip() in paper_text
            units.append({
                "unit_id": f"cell:{c.get('sample_idx', 0)}:{c['field']}",
                "field": c["field"],
                "value": _render_value(c.get("extracted")),
                "gold": _render_value(c.get("gold")),
                "decision": c.get("decision"),
                "quote": quote,
                "verbatim": verbatim,
                "section": fr.section if fr else None,
                "extraction_type": fr.extraction_type if fr else None,
                "confidence": fr.confidence if fr else None,
            })
    else:
        units = _study_units(result, paper_text)

    cols, rows = _sample_rows(result)
    if sample_fields:
        keep = set(sample_fields)
        cols = [c for c in cols if c in keep]
        for r in rows:
            r["cells"] = [c for c in r["cells"] if c["field"] in keep]

    title = meta.study or meta.paper_id or result.paper_id or "extraction"
    H: list[str] = []
    H.append(f"<title>Review: {_e(title)}</title>")
    H.append(f"<style>{_CSS}</style>")
    H.append('<div class="wrap">')
    H.append(f"<h1>Review packet — {_e(title)}</h1>")
    H.append(
        '<div class="banner"><strong>This is machine output that no one has '
        "reviewed.</strong> Nothing in it has been verified. Judge each value "
        "against the published source, not against how plausible it looks."
        + ("" if cells is None else
           " Some units are controls; judge every unit the same way.")
        + "</div>"
    )

    bits = [f"draft <code>{_e(sha[:12])}</code>", f"mode <code>{_e(mode)}</code>",
            f"granularity <code>{_e(result.granularity)}</code>",
            f"{len(result.fields)} fields", f"{len(result.samples)} sample records"]
    if meta.model:
        bits.append(f"model <code>{_e(meta.model)}</code>")
    if meta.generated_utc:
        bits.append(f"generated {_e(meta.generated_utc)}")
    links = " · ".join(f'<a href="{_e(u)}" rel="noreferrer noopener" target="_blank">{_e(k)}</a>'
                       for k, u in (meta.source_links or {}).items())
    H.append(f'<p class="meta">{" · ".join(bits)}'
             + (f"<br>read the source: {links}" if links else "") + "</p>")
    if meta.notes:
        H.append(f'<p class="meta">{_e(meta.notes)}</p>')

    if result.subgroups:
        H.append(f'<p class="meta">subgroups reported: '
                 f'{", ".join(_e(s) for s in result.subgroups)}</p>')

    H.append(f"<h2>{'Cells to adjudicate' if cells is not None else 'Study-level values'} "
             f"({len(units)})</h2>")
    if not units:
        H.append('<p class="meta">No units.</p>')
    for u in units:
        H.append(_unit_box(u, choices))

    if rows:
        shown = len(rows)
        H.append(f"<h2>Sample records ({len(result.samples)})</h2>")
        H.append('<p class="meta">Sample cells carry a source descriptor rather than a '
                 "quote: evidence quotes are a study-level slot. A descriptor names the "
                 "column a value came from, not the row — the row is not recorded.</p>")
        if shown < len(result.samples):
            H.append(f'<p class="meta">Showing the first {shown} of '
                     f"{len(result.samples)} records.</p>")
        H.append('<div class="tblwrap"><table><thead><tr><th>#</th>'
                 + "".join(f"<th>{_e(c)}</th>" for c in cols)
                 + "</tr></thead><tbody>")
        for r in rows:
            H.append(f'<tr><td>{r["index"]}</td>'
                     + "".join(f'<td>{_e(c["value"])}'
                               + (f'<br><span class="src">{_e(c["source"])}</span>'
                                  if c["source"] else "")
                               + "</td>" for c in r["cells"])
                     + "</tr>")
        H.append("</tbody></table></div>")

    if result.table_selection:
        H.append("<h2>Tables considered</h2>")
        H.append('<p class="meta">Which supplementary tables were read, which were '
                 "rejected, and why. A value that should have come from a rejected "
                 "table is a retrieval problem, not an extraction one.</p>")
        H.append('<div class="tblwrap"><table><thead><tr><th>table</th><th>used</th>'
                 "<th>score</th><th>matrix</th><th>fields matched</th><th>reasons</th>"
                 "</tr></thead><tbody>")
        for t in result.table_selection:
            matched = ", ".join(f"{k} ← {v}" for k, v in (t.matched_fields or {}).items())
            H.append(f"<tr><td>{_e(t.name)}</td><td>{'yes' if t.selected else 'no'}</td>"
                     f"<td>{t.score:.3f}</td><td>{'yes' if t.is_matrix else ''}</td>"
                     f"<td>{_e(matched)}</td><td>{_e('; '.join(t.reasons or []))}</td></tr>")
        H.append("</tbody></table></div>")

    if result.extraction_warnings:
        H.append(f"<h2>Extraction warnings ({len(result.extraction_warnings)})</h2>")
        H.append("<details><summary>show</summary><ul>"
                 + "".join(f"<li>{_e(w)}</li>" for w in result.extraction_warnings)
                 + "</ul></details>")

    H.append("</div>")
    H.append('<div class="bar">'
             '<label>reviewer <input id="reviewer" placeholder="your name"></label>'
             '<label>notes <input id="rnotes" placeholder="about this draft"></label>'
             '<button class="primary" id="export">Export verdict JSON</button>'
             '<button id="clear">Clear</button>'
             '<span id="count"></span></div>'
             '<div class="wrap"><textarea id="out" class="cmt" rows="8" hidden '
             'aria-label="verdict JSON"></textarea></div>')

    draft_js = json.dumps({"sha256": sha, "paper_id": result.paper_id or meta.paper_id,
                           "study": meta.study, "mode": mode})
    H.append(f"<script>var DRAFT={draft_js};{_JS}</script>")
    return "\n".join(H)
