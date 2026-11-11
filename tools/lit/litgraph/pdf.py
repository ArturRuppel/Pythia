"""PDF reading: DOI, title, and author-role markers (spec §4 Stage A/B).

Marker parsing is anchored on the OpenAlex family names (authoritative): for each known
family we locate it in the page text and read the superscript symbols that follow, then
classify them via the page's symbol legend (`*For correspondence`, `†...contributed
equally`). This avoids brittle author-block segmentation.
"""

from __future__ import annotations

import re
import unicodedata

import pymupdf as fitz  # pymupdf

from .citekey import fold_ascii
from .roles import AuthorMarkers

# Superscript marker glyphs used in bylines.
_SYMS = "*†‡§¶#"
_DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"<>]+", re.IGNORECASE)


def _open(path: str) -> fitz.Document:
    return fitz.open(path)


def extract_text(path: str, max_pages: int | None = None) -> str:
    """Concatenated text of the first `max_pages` pages (all pages if None)."""
    doc = _open(path)
    pages = range(len(doc)) if max_pages is None else range(min(max_pages, len(doc)))
    return "\n".join(doc[i].get_text() for i in pages)


def _clean_doi(raw: str) -> str:
    """Trim trailing punctuation that regex greedily grabbed."""
    return raw.rstrip(").,;:")


def find_doi(haystack: str) -> str | None:
    """Pick the focal DOI from text: prefer one following a 'doi' label, else the most
    frequent candidate (ties broken by first appearance)."""
    labeled = re.search(r"doi[:\s/]*?(" + _DOI_RE.pattern + ")", haystack, re.IGNORECASE)
    if labeled:
        return _clean_doi(labeled.group(1))
    cands = [_clean_doi(m.group(0)) for m in _DOI_RE.finditer(haystack)]
    if not cands:
        return None
    freq: dict[str, int] = {}
    for c in cands:
        freq[c] = freq.get(c, 0) + 1
    return max(freq, key=lambda c: (freq[c], -cands.index(c)))


def extract_doi(path: str) -> str | None:
    """Best-effort focal DOI from the first two pages + embedded metadata."""
    doc = _open(path)
    text = "\n".join(doc[i].get_text() for i in range(min(2, len(doc))))
    meta_blob = " ".join(str(v) for v in doc.metadata.values()) if doc.metadata else ""
    return find_doi(text + "\n" + meta_blob)


def extract_title(path: str) -> str | None:
    """Best-effort title from PDF metadata, else the largest-font text on page 1.

    Used only for the OpenAlex title-search fallback when no DOI resolves.
    """
    doc = _open(path)
    if doc.metadata and doc.metadata.get("title", "").strip():
        return doc.metadata["title"].strip()
    if len(doc) == 0:
        return None

    # Largest-font run of spans on page 1.
    spans: list[tuple[float, str]] = []
    data = doc[0].get_text("dict")
    for block in data.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                txt = span.get("text", "").strip()
                if txt:
                    spans.append((round(span.get("size", 0), 1), txt))
    if not spans:
        return None
    max_size = max(s for s, _ in spans)
    title_parts = [t for s, t in spans if s == max_size]
    title = " ".join(title_parts).strip()
    title = re.sub(r"\s+", " ", title.replace("­", "").replace("​", ""))
    return title or None


def _legend_symbols(text: str, phrase_pattern: str) -> set[str]:
    """Symbols that label `phrase_pattern` in the page text (e.g. corresponding/equal)."""
    found: set[str] = set()
    for m in re.finditer(r"([" + re.escape(_SYMS) + r"]+)\s*" + phrase_pattern, text, re.IGNORECASE):
        found.update(m.group(1))
    return found


def _marker_symbols_for(text: str, family: str) -> set[str]:
    """Superscript symbols attached to `family` in the byline (requires the affiliation
    digit that distinguishes the byline occurrence from running-head mentions)."""
    syms: set[str] = set()
    pat = re.escape(unicodedata.normalize("NFC", family)) + r"[0-9][0-9,]*([" + re.escape(_SYMS) + r"]*)"
    for m in re.finditer(pat, text):
        syms.update(m.group(1))
    return syms


def extract_author_markers(text: str, families: list[str]) -> AuthorMarkers:
    """Classify each known family as corresponding / equal-contribution from the page text.

    `families` are the OpenAlex family names (authoritative author list).
    """
    text = unicodedata.normalize("NFC", text)
    corr_syms = _legend_symbols(text, r"For\s+correspondence")
    if not corr_syms and re.search(r"For\s+correspondence", text, re.IGNORECASE):
        corr_syms = {"*"}  # legend present but glyph not captured → the near-universal '*'
    equal_syms = _legend_symbols(text, r"(?:These\s+authors\s+)?contributed\s+equally")

    corresponding: set[str] = set()
    equal: set[str] = set()
    for fam in families:
        syms = _marker_symbols_for(text, fam)
        key = fold_ascii(fam).lower().strip()
        if syms & corr_syms:
            corresponding.add(key)
        if syms & equal_syms:
            equal.add(key)
    return AuthorMarkers(corresponding_families=corresponding, equal_contrib_families=equal)
