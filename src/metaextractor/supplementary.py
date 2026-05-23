"""Supplementary materials fetcher and text extractor.

Resolves supplementary files for a PMCID through a layered chain of sources:
  1. PMC AWS S3 open-data bucket (canonical, anonymous, no anti-bot gating),
     keyed by the filenames discovered in the JATS XML.
  2. The Europe PMC supplementaryFiles ZIP bundle (fallback).
Text-readable members (.xlsx, .csv, .tsv, .pdf, .txt) are converted into a
single string. Image-only members are skipped because the extractor is
text-only. Also supports local files supplied via the CLI.
"""
from __future__ import annotations

import csv
import io
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

EUROPEPMC_SUPP = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/supplementaryFiles"
PMC_S3_LIST = "https://pmc-oa-opendata.s3.amazonaws.com/?list-type=2&prefix={prefix}&delimiter=/"
PMC_S3_FILE = "https://pmc-oa-opendata.s3.amazonaws.com/{key}"
S3_NS = "{http://s3.amazonaws.com/doc/2006-03-01/}"
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


def _file_to_text(name: str, blob: bytes) -> str:
    """Convert one file's bytes to text using extension-based dispatch.

    Raises ValueError when the extension is image-only or unsupported.
    Lower-level converters may raise their own exceptions on parse failure.
    """
    ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
    if ext in SKIP_EXTS:
        raise ValueError(f"image-only ({ext})")
    if ext == ".xlsx":
        return _xlsx_to_text(blob)
    if ext == ".csv":
        return _csv_to_text(blob, ",")
    if ext == ".tsv":
        return _csv_to_text(blob, "\t")
    if ext == ".pdf":
        return _pdf_to_text(blob)
    if ext in TEXT_EXTS:
        return blob.decode("utf-8", errors="replace")
    raise ValueError(f"unsupported extension ({ext or '?'})")


def _block(name: str, source: str, text: str) -> str:
    return f"--- SUPPLEMENTARY FILE: {name} (source: {source}) ---\n{text.strip()}"


def _latest_s3_version_prefix(bare: str) -> str | None:
    """Return the highest-numbered version prefix (e.g. ``PMC5264247.1``)
    available in the PMC AWS S3 open-data bucket, or None if absent.
    """
    url = PMC_S3_LIST.format(prefix=f"PMC{bare}.")
    try:
        body = _http_get(url)
    except Exception:
        return None
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return None
    versions: list[tuple[int, str]] = []
    for cp in root.findall(f"{S3_NS}CommonPrefixes/{S3_NS}Prefix"):
        if cp.text is None:
            continue
        head = cp.text.rstrip("/")
        if not head.startswith(f"PMC{bare}."):
            continue
        tail = head.rsplit(".", 1)[1]
        if tail.isdigit():
            versions.append((int(tail), head))
    if not versions:
        return None
    return max(versions)[1]


def fetch_supplementary(
    pmcid: str,
    jats_hrefs: list[tuple[str, str]] | None = None,
) -> Supplementary:
    """Resolve supplementary files for a PMCID through a layered source chain.

    Sources, in order:
      1. PMC AWS S3 (``pmc-oa-opendata``), keyed by filenames discovered in
         the JATS XML. Open, anonymous, no anti-bot gating.
      2. Europe PMC's supplementaryFiles ZIP for the article.

    Files are deduplicated by lowercased basename; later sources do not
    re-add filenames an earlier source already supplied.
    """
    bare = pmcid.upper().removeprefix("PMC")
    blocks: list[str] = []
    included: list[str] = []
    skipped: list[tuple[str, str]] = []
    seen: set[str] = set()

    # Source 1: PMC AWS S3, addressed by JATS-declared filenames.
    if jats_hrefs:
        version_prefix = _latest_s3_version_prefix(bare)
        if version_prefix is None and jats_hrefs:
            skipped.append((f"PMC{bare}", "s3: no version prefix found in pmc-oa-opendata"))
        elif version_prefix is not None:
            for name, _orig_url in jats_hrefs:
                key = name.lower()
                if key in seen:
                    continue
                ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
                if ext in SKIP_EXTS:
                    skipped.append((name, f"image-only ({ext})"))
                    seen.add(key)
                    continue
                s3_url = PMC_S3_FILE.format(key=f"{version_prefix}/{name}")
                try:
                    blob = _http_get(s3_url)
                    text = _file_to_text(name, blob)
                except Exception as e:
                    skipped.append((name, f"s3: {type(e).__name__}: {e}"))
                    continue
                blocks.append(_block(name, "s3", text))
                included.append(name)
                seen.add(key)

    # Source 2: Europe PMC supplementaryFiles ZIP.
    europepmc_url = EUROPEPMC_SUPP.format(pmcid=f"PMC{bare}")
    zf: zipfile.ZipFile | None = None
    try:
        zip_bytes = _http_get(europepmc_url)
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        skipped.append(("(europepmc zip)", "response was not a valid ZIP"))
    except Exception as e:
        # Only surface the network failure when nothing else worked, so a
        # successful S3 pass isn't drowned out by a routine EuropePMC 404.
        if not included:
            skipped.append(("(europepmc download)", f"{type(e).__name__}: {e}"))

    if zf is not None:
        for name in sorted(zf.namelist()):
            base = name.rsplit("/", 1)[-1]
            key = base.lower()
            if key in seen:
                continue
            try:
                blob = zf.read(name)
                text = _file_to_text(base, blob)
            except Exception as e:
                skipped.append((name, f"europepmc: {type(e).__name__}: {e}"))
                continue
            blocks.append(_block(name, "europepmc", text))
            included.append(name)
            seen.add(key)

    return Supplementary(text="\n\n".join(blocks), included=included, skipped=skipped)


def supplementary_from_local(paths: list[Path]) -> Supplementary:
    """Build a Supplementary record from user-supplied local files."""
    blocks: list[str] = []
    included: list[str] = []
    skipped: list[tuple[str, str]] = []
    for path in paths:
        try:
            blob = path.read_bytes()
            text = _file_to_text(path.name, blob)
        except Exception as e:
            skipped.append((str(path), f"local: {type(e).__name__}: {e}"))
            continue
        blocks.append(_block(path.name, "local", text))
        included.append(str(path))
    return Supplementary(text="\n\n".join(blocks), included=included, skipped=skipped)
