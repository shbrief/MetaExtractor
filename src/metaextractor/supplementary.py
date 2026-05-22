"""Supplementary materials fetcher and text extractor.

Downloads the supplementary-files ZIP from Europe PMC for a given PMCID,
then flattens any text-readable members (.xlsx, .csv, .tsv, .pdf, .txt)
into a single string. Image-only members (.eps, .gif, .jpg, .png) are
skipped because the extractor is text-only.
"""
from __future__ import annotations

import csv
import io
import urllib.request
import zipfile
from dataclasses import dataclass, field

EUROPEPMC_SUPP = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/supplementaryFiles"
USER_AGENT = "metaextractor/0.1 (+https://github.com/OmicsMLRepo)"

TEXT_EXTS = {".csv", ".tsv", ".txt"}
SKIP_EXTS = {".eps", ".gif", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".svg"}


@dataclass
class Supplementary:
    text: str  # concatenated, with per-file headers
    included: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (filename, reason)


def _http_get(url: str, timeout: float = 60.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _xlsx_to_text(blob: bytes) -> str:
    try:
        from openpyxl import load_workbook
    except ImportError as e:
        raise RuntimeError(
            "xlsx supplementary support requires the 'supplementary' extra: "
            "pip install 'metaextractor[supplementary]'"
        ) from e
    wb = load_workbook(io.BytesIO(blob), read_only=True, data_only=True)
    parts: list[str] = []
    for sn in wb.sheetnames:
        ws = wb[sn]
        parts.append(f"[sheet: {sn}]")
        for row in ws.iter_rows(values_only=True):
            cells = ["" if c is None else str(c) for c in row]
            if any(c.strip() for c in cells):
                parts.append("\t".join(cells))
    return "\n".join(parts)


def _csv_to_text(blob: bytes, delimiter: str) -> str:
    text = blob.decode("utf-8", errors="replace")
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    return "\n".join("\t".join(row) for row in reader)


def _pdf_to_text(blob: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise RuntimeError(
            "pdf supplementary support requires the 'pdf' extra: "
            "pip install 'metaextractor[pdf]'"
        ) from e
    reader = PdfReader(io.BytesIO(blob))
    return "\n\n".join(p.extract_text() or "" for p in reader.pages)


def fetch_supplementary(pmcid: str) -> Supplementary:
    """Download and convert all text-readable supplementary files for a PMCID."""
    bare = pmcid.upper().removeprefix("PMC")
    pmcid = f"PMC{bare}"
    url = EUROPEPMC_SUPP.format(pmcid=pmcid)

    try:
        zip_bytes = _http_get(url)
    except Exception as e:
        return Supplementary(text="", skipped=[("(download)", f"{type(e).__name__}: {e}")])

    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        return Supplementary(text="", skipped=[("(zip)", "response was not a valid ZIP")])

    blocks: list[str] = []
    included: list[str] = []
    skipped: list[tuple[str, str]] = []

    for name in sorted(zf.namelist()):
        ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
        if ext in SKIP_EXTS:
            skipped.append((name, f"image-only ({ext})"))
            continue
        blob = zf.read(name)
        try:
            if ext == ".xlsx":
                converted = _xlsx_to_text(blob)
            elif ext == ".csv":
                converted = _csv_to_text(blob, ",")
            elif ext == ".tsv":
                converted = _csv_to_text(blob, "\t")
            elif ext == ".pdf":
                converted = _pdf_to_text(blob)
            elif ext in TEXT_EXTS:
                converted = blob.decode("utf-8", errors="replace")
            else:
                skipped.append((name, f"unsupported extension ({ext or '?'})"))
                continue
        except Exception as e:
            skipped.append((name, f"convert failed: {type(e).__name__}: {e}"))
            continue
        blocks.append(f"--- SUPPLEMENTARY FILE: {name} ---\n{converted.strip()}")
        included.append(name)

    return Supplementary(text="\n\n".join(blocks), included=included, skipped=skipped)
