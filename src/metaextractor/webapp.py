"""MetaExtractor web app (Streamlit).

Three key inputs, matching the CLI:
  1. Target study   — a PMID/PMCID (fetched from NCBI) or a pasted/uploaded paper.
  2. Target schema  — a schema bundled with the package, or one you upload.
  3. API key        — your Anthropic API key (kept in session, never written to disk).

Launch with::

    metaextract-app                          # console script (added by pyproject)
    # or, pointing streamlit at this file directly:
    streamlit run src/metaextractor/webapp.py
"""
from __future__ import annotations

import io
import os
import tempfile

import streamlit as st

from metaextractor.extractor import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_MAX_TOKENS,
    DEFAULT_MIN_TABLE_RELEVANCE,
    ExtractionError,
    MetaExtractor,
    estimate_cost_usd,
)
from metaextractor.fetcher import FetchError, fetch_paper
from metaextractor.keys import ApiKeyError, key_fingerprint, resolve_api_key
from metaextractor.schema import Schema
from metaextractor.schema_loader import (
    SchemaLoadError,
    bundled_schemas,
    load_schema_from_text,
)
from metaextractor.writers import to_csv

MODEL_CHOICES = [
    "claude-sonnet-4-6",
    "claude-opus-4-7",
    "claude-haiku-4-5",
]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _read_upload_as_text(upload) -> str:
    """Decode an uploaded paper file to text (PDF via pypdf if available)."""
    name = upload.name.lower()
    data = upload.getvalue()
    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
        except ImportError as e:
            raise RuntimeError(
                "PDF upload requires the 'pdf' extra: pip install 'metaextractor[pdf]'"
            ) from e
        reader = PdfReader(io.BytesIO(data))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    return data.decode("utf-8", errors="replace")


def _schema_preview(schema: Schema):
    rows = []
    for f in schema.fields:
        rows.append(
            {
                "field": f.name,
                "type": f.type,
                "required": f.required,
                "allowed_values": ", ".join(f.allowed_values or [])[:60]
                + ("…" if f.allowed_values and len(", ".join(f.allowed_values)) > 60 else ""),
                "description": (f.description or "")[:80],
            }
        )
    return rows


def _fields_to_rows(result) -> list[dict]:
    rows = []
    for name, fr in result.fields.items():
        rows.append(
            {
                "field": name,
                "value": fr.value,
                "extraction_type": fr.extraction_type,
                "confidence": fr.confidence,
                "evidence": fr.evidence_quote,
                "section": fr.section,
            }
        )
    return rows


# --------------------------------------------------------------------------- #
# App
# --------------------------------------------------------------------------- #
def main() -> None:
    st.set_page_config(page_title="MetaExtractor", page_icon="🧬", layout="wide")
    st.title("🧬 MetaExtractor")
    st.caption(
        "LLM-backed biomedical metadata extraction with verbatim provenance — "
        "no fabrication, no outside knowledge."
    )

    # ---- Sidebar: API key + model + advanced options --------------------- #
    with st.sidebar:
        st.header("① API key")
        env_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY")
        api_key_ref = st.text_input(
            "Anthropic API key",
            type="password",
            value=env_key or "",
            help="Paste the literal key, or a reference: 'file:PATH' to read it "
            "from a file, or 'env:VARNAME' from an environment variable. "
            "Kept in this session only; never written to disk. Falls back to "
            "ANTHROPIC_API_KEY / CLAUDE_API_KEY if left blank.",
        )
        if env_key:
            st.caption("Prefilled from environment.")
        else:
            st.caption("Tip: paste `file:~/path/to/keyfile` to read the key from a file.")

        st.divider()
        st.header("Model & options")
        model = st.selectbox("Model", MODEL_CHOICES, index=0)
        with st.expander("Advanced"):
            batch_size = st.number_input(
                "Batch size", min_value=1, value=DEFAULT_BATCH_SIZE,
                help="Auto-batch schemas larger than this many fields.",
            )
            max_tokens = st.number_input(
                "Max tokens / batch", min_value=256, value=DEFAULT_MAX_TOKENS, step=256,
            )
            include_supplementary = st.checkbox(
                "Fetch supplementary materials (PMID mode)", value=True,
            )
            sample_discovery = st.checkbox(
                "Sample discovery pass", value=True,
                help="Enumerate sample IDs before per-batch field extraction.",
            )
            min_table_relevance = st.slider(
                "Min table relevance", 0.0, 1.0, DEFAULT_MIN_TABLE_RELEVANCE, 0.05,
            )

    # ---- Main: study + schema ------------------------------------------- #
    col_study, col_schema = st.columns(2)

    with col_study:
        st.header("② Target study")
        input_mode = st.radio(
            "Input mode",
            ["PMID / PMCID (fetch)", "Paste text", "Upload file"],
            horizontal=False,
        )
        paper_id = None
        pasted_text = None
        upload = None
        if input_mode == "PMID / PMCID (fetch)":
            paper_id = st.text_input(
                "PMID or PMCID", placeholder="29795809  or  PMC5837013",
            )
        elif input_mode == "Paste text":
            paper_id = st.text_input("Paper ID (optional label)", placeholder="PMID:29795809")
            pasted_text = st.text_area("Paper text", height=220)
        else:
            paper_id = st.text_input("Paper ID (optional label)", placeholder="PMID:29795809")
            upload = st.file_uploader("Paper file", type=["txt", "md", "pdf"])

    with col_schema:
        st.header("③ Target schema")
        bundled = bundled_schemas()
        options = [f"📦 {s.label}" for s in bundled] + ["⬆️ Upload a schema…"]
        choice = st.selectbox("Schema source", options, index=0 if bundled else len(options) - 1)

        schema_text = None
        schema_filename = "schema.json"
        class_name = None
        if choice.startswith("📦"):
            selected = bundled[options.index(choice)]
            schema_text = selected.text
            schema_filename = selected.key
            st.caption(selected.description)
        else:
            schema_upload = st.file_uploader(
                "Schema file (JSON, YAML, or LinkML YAML)",
                type=["json", "yaml", "yml"],
            )
            if schema_upload is not None:
                schema_text = schema_upload.getvalue().decode("utf-8", errors="replace")
                schema_filename = schema_upload.name
            class_name = st.text_input(
                "LinkML class (optional)",
                help="Only needed when a LinkML schema declares multiple classes.",
            ) or None

        schema_obj = None
        if schema_text:
            try:
                schema_obj = load_schema_from_text(
                    schema_text, filename=schema_filename, class_name=class_name
                )
                st.success(f"Schema OK — {len(schema_obj.fields)} fields.")
                with st.expander("Preview fields"):
                    st.dataframe(_schema_preview(schema_obj), width="stretch")
            except SchemaLoadError as e:
                st.error(f"Schema error: {e}")

    st.divider()
    run = st.button("Extract metadata", type="primary", width="stretch")

    if not run:
        return

    # ---- Validate inputs ------------------------------------------------- #
    try:
        api_key = resolve_api_key(api_key_ref)
    except ApiKeyError as e:
        st.error(f"API key: {e}")
        return
    st.caption(f"Using API key: {key_fingerprint(api_key)}")
    if schema_obj is None:
        st.error("Provide a valid schema.")
        return

    # Fail fast on a bad key with a clear message, before the (slow) fetch and
    # any billable extraction call. models.list() spends no tokens.
    from anthropic import Anthropic, AuthenticationError

    try:
        Anthropic(api_key=api_key).models.list(limit=1)
    except AuthenticationError:
        st.error(
            f"The Anthropic API rejected this key (401). Resolved key: "
            f"{key_fingerprint(api_key)}. Check that this matches a working "
            f"key — e.g. paste `file:PATH` to read it from your key file."
        )
        return
    except Exception:
        # Network/other issues: don't block; the extraction call will surface it.
        pass

    tables: list = []
    fetch_notes: list[str] = []
    try:
        if input_mode == "PMID / PMCID (fetch)":
            if not paper_id:
                st.error("Enter a PMID or PMCID.")
                return
            with st.spinner(f"Fetching {paper_id} from NCBI…"):
                fetched = fetch_paper(paper_id, include_supplementary=include_supplementary)
            paper_text = fetched.text
            tables.extend(fetched.supplementary_tables or [])
            fetch_notes.append(f"Source: {fetched.source}")
            if fetched.source == "pubmed_abstract":
                fetch_notes.append(
                    "No PMC full text — only the PubMed abstract was retrieved."
                )
            if fetched.supplementary_included:
                fetch_notes.append(
                    f"Supplementary included: {', '.join(fetched.supplementary_included)}"
                )
            if fetched.supplementary_tables:
                fetch_notes.append(
                    f"Supplementary tables parsed: {len(fetched.supplementary_tables)}"
                )
        elif input_mode == "Paste text":
            if not pasted_text or not pasted_text.strip():
                st.error("Paste the paper text.")
                return
            paper_text = pasted_text
        else:
            if upload is None:
                st.error("Upload a paper file.")
                return
            paper_text = _read_upload_as_text(upload)
    except FetchError as e:
        st.error(f"Fetch failed: {e}")
        return
    except RuntimeError as e:
        st.error(str(e))
        return

    if fetch_notes:
        st.info("  \n".join(fetch_notes))

    # ---- Extract --------------------------------------------------------- #
    extractor = MetaExtractor(
        model=model,
        max_tokens=int(max_tokens),
        batch_size=int(batch_size),
        sample_discovery=sample_discovery,
        api_key=api_key,
        min_table_relevance=float(min_table_relevance),
    )
    try:
        with st.spinner("Extracting… (this calls the Anthropic API)"):
            result = extractor.extract(
                paper_text, schema_obj, paper_id=paper_id or None, tables=tables or None
            )
    except ExtractionError as e:
        st.error(f"Extraction failed: {e}")
        if e.raw_response:
            with st.expander("Raw model response"):
                st.code(e.raw_response)
        return
    except Exception as e:  # API/auth/network errors
        st.error(f"Error: {e}")
        return

    # ---- Results --------------------------------------------------------- #
    st.success("Extraction complete.")
    usage = extractor.last_usage
    cost = estimate_cost_usd(usage, model)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Granularity", result.granularity)
    m2.metric("Fields", len(result.fields))
    m3.metric("Samples", len(result.samples or []))
    m4.metric(
        "Est. cost",
        cost.get("note", f"${cost.get('total_usd', 0):.4f}"),
    )
    st.caption(
        f"{usage['n_calls']} call(s) · input {usage['input_tokens']:,} · "
        f"cache_read {usage['cache_read_input_tokens']:,} · "
        f"output {usage['output_tokens']:,}"
    )

    if result.extraction_warnings:
        with st.expander(f"⚠️ Warnings ({len(result.extraction_warnings)})"):
            for w in result.extraction_warnings:
                st.write(f"- {w}")

    tab_fields, tab_samples, tab_json = st.tabs(["Fields", "Samples", "Raw JSON"])
    with tab_fields:
        st.dataframe(_fields_to_rows(result), width="stretch")
    with tab_samples:
        if result.samples:
            st.dataframe(result.samples, width="stretch")
        else:
            st.caption("No sample-level rows for this extraction.")
    with tab_json:
        st.code(result.model_dump_json(indent=2), language="json")

    # ---- Downloads ------------------------------------------------------- #
    json_payload = result.model_dump_json(indent=2)
    with tempfile.NamedTemporaryFile(
        "w+", suffix=".csv", delete=False, encoding="utf-8"
    ) as tmp:
        csv_path = tmp.name
    try:
        to_csv(result, csv_path, include_provenance=True)
        csv_text = open(csv_path, encoding="utf-8").read()
    finally:
        os.unlink(csv_path)
    stem = (paper_id or "extraction").replace(":", "_").replace("/", "_")
    d1, d2 = st.columns(2)
    d1.download_button(
        "⬇️ Download JSON", json_payload, file_name=f"{stem}.json", mime="application/json",
        width="stretch",
    )
    d2.download_button(
        "⬇️ Download CSV", csv_text, file_name=f"{stem}.csv", mime="text/csv",
        width="stretch",
    )


if __name__ == "__main__":
    main()
