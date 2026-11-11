"""Quote polishing for display + integrity flagging (SCHEMA §6.4).

The stored `quote` is the *tight verbatim anchor* a curator welds to the paper's `.md`.
For the viewer we derive a `quote_display`: the anchor grown out to its enclosing
sentence(s) and stripped of citation / figure-callout artifacts. Nothing here mutates the
YAML — the anchor stays exactly as authored, and if the stripper improves, every quote
upgrades on the next build with no data migration.

Two tiers, exactly as SCHEMA §6.4 anticipates:
  * a plain anchor is located verbatim in the `.md`, expanded, stripped  -> status "verbatim"
  * an authored `[...]` join is non-contiguous by construction, so it is polished
    segment-by-segment and flagged for review  -> status "joined". Every segment must be
    found verbatim, *in order*: segment k is searched only after segment k-1's match, so a
    join cannot stitch passages out of sequence and a segment missing from the paper is not
    excused by its neighbours.
A quote that can't be located (for a join: any one segment, in order) is flagged
 -> status "not_found".

Stripping is deliberately conservative: a parenthetical is deleted only when it reads as a
citation (a Capitalized name followed by a year, nothing but name/year/punctuation inside),
so content parentheticals — (N = 16), (CeNuS), (tumor diameter, tumor grade, ...) — survive.
Clause-level trimming ("as illustrated in Fig. 3") is a curator judgement, authored via the
`[...]` join; it is never done automatically.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import fitz  # pymupdf — a litgraph hard dependency

from .fulltext import _normalize, repair_legacy_glyphs

JOIN = "[...]"          # authored non-contiguous marker in a stored quote (SCHEMA §6.4)
JOIN_DISPLAY = " […] "  # how a join reads in the polished text

# --- artifact stripping --------------------------------------------------------------

_BRACKET_NUM = re.compile(r"\s*\[\d+(?:[–,\-]\s*\d+)*\]")   # [1], [3-5], [3, 7]
_CALLOUT = re.compile(                                          # (Fig. 3b), (Table 1), (see Methods)
    r"\s*\((?:Fig(?:ure)?|Table|Eq(?:uation)?|Ref|see)\.?\s*[^)]*\)", re.I)
_EMPHASIS = re.compile(r"_?\*\*(.+?)\*\*_?")                    # _**...**_, **...** (markdown cite wrap)
_YEAR = re.compile(r"\b(?:19|20)\d{2}[a-z]?\b")
_CITEISH = re.compile(r"^[A-Za-zÀ-ÿ0-9'.,;:&\s\-–]+$")  # only name/year/punct chars
_NAME_THEN_YEAR = re.compile(r"[A-Z][A-Za-z'\-]+.*?\b(?:19|20)\d{2}")  # a Capitalized name ... then a year


def _drop_cite_paren(m: "re.Match[str]") -> str:
    """Delete a parenthetical iff it reads as an author-year citation; keep it otherwise."""
    inner = m.group(1)
    if _YEAR.search(inner) and _CITEISH.match(inner) and _NAME_THEN_YEAR.search(inner):
        return ""
    return m.group(0)


def strip_artifacts(text: str) -> str:
    """Remove inline citation / figure-callout noise from a sentence, delete-only."""
    # 1. Unwrap markdown emphasis — itself a rendering artifact, and it hides the
    #    author-year cites underneath from the paren scan below.
    text = _EMPHASIS.sub(r"\1", text)
    # 2. Close the whitespace seams the unwrap opens, so parens/commas read cleanly.
    text = re.sub(r"\(\s+", "(", text)
    text = re.sub(r"\s+\)", ")", text)
    text = re.sub(r"\s+([;,])", r"\1", text)
    # 3. Numeric-bracket cites and figure/table callouts.
    text = _BRACKET_NUM.sub("", text)
    text = _CALLOUT.sub("", text)
    # 4. Author-year parentheticals (semantic test — any chain length, keeps content parens).
    text = re.sub(r"\s*\(([^)]*)\)", _drop_cite_paren, text)
    # 5. Tidy the seams left behind.
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


# --- sentence expansion --------------------------------------------------------------

# Abbreviations whose trailing "." must NOT count as a sentence boundary.
_ABBR = (r"(?:Fig|Figs|Eq|Eqs|Ref|Refs|No|Nos|Dr|Mr|Ms|Prof|Inc|Ltd|St|vs|cf|ca|approx|"
         r"e\.g|i\.e|et al|resp|ca|Suppl|Vol)")
_ABBR_END = re.compile(_ABBR + r"$")

# A numeric bracket-cite carries no sentence-boundary information, but glued to a terminal
# period ("fibrosis.[16] Underlying") it hides the boundary from the scan below. Blank it to
# equal-length spaces in a scan-only copy so offsets stay valid and the period reads as an end.
_CITE_BLANK = re.compile(r"\[\d+(?:[–,\-]\s*\d+)*\]")


def _blank_cites(text: str) -> str:
    return _CITE_BLANK.sub(lambda m: " " * len(m.group(0)), text)


def _sentence_span(text: str, lo: int, hi: int) -> tuple[int, int]:
    """Grow [lo, hi) out to the enclosing sentence boundaries within `text`.

    A boundary is `.`/`!`/`?` followed by whitespace (not after a known abbreviation), or a
    blank line, or the text edge."""
    start = lo
    while start > 0:
        c = text[start - 1]
        if c == "\n" and start >= 2 and text[start - 2] == "\n":
            break
        if c in ".!?" and start < len(text) and text[start] in " \n":
            if not _ABBR_END.search(text[max(0, start - 6):start - 1]):
                break
        start -= 1
    end = hi
    while end < len(text):
        c = text[end]
        if c in ".!?":
            nxt = text[end + 1] if end + 1 < len(text) else " "
            if nxt in " \n" and not _ABBR_END.search(text[max(0, end - 6):end]):
                return start, end + 1
        if c == "\n" and end + 1 < len(text) and text[end + 1] == "\n":
            break
        end += 1
    return start, end


def _pattern(needle: str) -> "re.Pattern[str]":
    """`needle` as a regex tolerant of runs of whitespace differing (newline vs space)."""
    return re.compile(re.sub(r"(?:\\ )+", r"\\s+", re.escape(needle)))


def _locate(text: str, needle: str) -> tuple[int | None, int | None]:
    """Find `needle` in `text`, tolerant of runs of whitespace differing (newline vs space)."""
    i = text.find(needle)
    if i >= 0:
        return i, i + len(needle)
    m = _pattern(needle).search(text)
    return (m.start(), m.end()) if m else (None, None)


def _locate_in_order(text: str, segs: list[str]) -> list[tuple[int, int] | None]:
    """Place each segment of a join in `text`, in order: segment k only counts if it occurs
    after segment k-1's match. Returns one (start, end) per segment, or None for a segment with
    no occurrence after the previous placed one (the search for the next resumes after the last
    segment that *was* placed).

    A forward pass takes the earliest occurrence of each segment — for "do they occur in this
    order at all" that greedy choice is never wrong. It can, though, pin an early segment to a
    first-match artefact (the same phrase in the abstract) far from where the passage really is,
    so a backward pass then slides each placed segment to its *latest* occurrence still ending
    before the next one starts. The order is unchanged; the gaps it reports are the tightest
    reading of the join, which is what a reviewer needs to judge whether it is honest."""
    occ = [[(m.start(), m.end()) for m in _pattern(seg).finditer(text)] if text else []
           for seg in segs]
    spans: list[tuple[int, int] | None] = []
    at = 0
    for hits in occ:
        hit = next((h for h in hits if h[0] >= at), None)
        spans.append(hit)
        if hit:
            at = hit[1]
    limit: int | None = None          # the start of the next placed segment; the last stays put
    for k in range(len(segs) - 1, -1, -1):
        if spans[k] is None:
            continue
        if limit is not None:
            spans[k] = [h for h in occ[k] if spans[k][0] <= h[0] and h[1] <= limit][-1]
        limit = spans[k][0]
    return spans


# --- top-level polish ----------------------------------------------------------------

def _expand(fulltext: str, span: tuple[int, int] | None, anchor: str) -> str:
    """The display text for one located anchor: grown out to its sentence(s) and stripped. An
    anchor that was not located (`span` None) is stripped but not expanded."""
    if span is None:
        return strip_artifacts(anchor)
    # Detect boundaries on a cite-blanked copy (offsets preserved); slice the original.
    s0, s1 = _sentence_span(_blank_cites(fulltext), *span)
    return strip_artifacts(" ".join(fulltext[s0:s1].split()))


@dataclass
class Polished:
    """What `polish` learned about one quote. `status` is 'verbatim' | 'joined' | 'not_found'.
    For a join, `segments` counts its non-empty segments, `missing` lists the 1-based numbers of
    those not found in order, and `gaps` holds the characters of full text cut between each
    consecutive pair (only when every segment was found)."""
    display: str
    status: str
    segments: int = 1
    missing: list[int] = field(default_factory=list)
    gaps: list[int] = field(default_factory=list)


def polish_quote(quote: str, fulltext: str) -> Polished:
    """Polish a stored quote for display and check it against the paper's `.md` (SCHEMA §6.4).
    `fulltext` is the normalized `.md` ("" if unavailable — then every quote is stripped but not
    expanded, and reported not_found). A join is not_found unless every segment occurs in order."""
    anchor = " ".join(quote.split())
    if JOIN not in anchor:
        lo, hi = _locate(fulltext, anchor) if fulltext else (None, None)
        span = None if lo is None else (lo, hi)
        return Polished(_expand(fulltext, span, anchor), "verbatim" if span else "not_found")
    segs = [seg for seg in (part.strip() for part in anchor.split(JOIN)) if seg]
    spans = _locate_in_order(fulltext, segs)
    display = JOIN_DISPLAY.join(_expand(fulltext, sp, seg) for seg, sp in zip(segs, spans))
    missing = [k + 1 for k, sp in enumerate(spans) if sp is None]
    if missing:
        return Polished(display, "not_found", len(segs), missing)
    gaps = [b[0] - a[1] for a, b in zip(spans, spans[1:])]
    return Polished(display, "joined", len(segs), [], gaps)


def polish(quote: str, fulltext: str) -> tuple[str, str]:
    """`polish_quote` reduced to (quote_display, status)."""
    p = polish_quote(quote, fulltext)
    return p.display, p.status


# --- graph integration ---------------------------------------------------------------

def _read_fulltext(pdf_dir: Path | None, citekey: str) -> str:
    """The paper's normalized `.md` full text, or "" if there is no `.md` for it."""
    if pdf_dir is None:
        return ""
    f = Path(pdf_dir) / f"{citekey}.md"
    if not f.is_file():
        return ""
    return _normalize(f.read_text(encoding="utf-8"))


def polish_graph(graph, pdf_dir: Path | None) -> list[str]:
    """Set `quote_display` on every quoted slice of every curated paper, reading each
    paper's `.md` from `pdf_dir`. Returns human-readable flags (SCHEMA §6.4) for quotes
    that need curator review: anchors not found verbatim (for a join: any segment not found
    in order, named by number), and authored `[...]` joins whose segments all were, with the
    characters cut between them so stitching across distant sections stands out.

    `lit build`, `lit preview` (including `--scratch`, at proposition time) and the servers all
    run this one function, so the three cannot disagree about which quote is verbatim."""
    warnings: list[str] = []
    for ck, p in graph.papers.items():
        if not p.curated or not any(s.quote for s in p.slices):
            continue
        fulltext = _read_fulltext(pdf_dir, ck)
        for s in p.slices:
            if not s.quote:
                continue
            r = polish_quote(s.quote, fulltext)
            s.quote_display = r.display
            if r.status == "not_found":
                where = f" (no {ck}.md)" if not fulltext else ""
                if not where and r.missing:
                    nums = ", ".join(str(k) for k in r.missing)
                    which = "segment" if len(r.missing) == 1 else "segments"
                    where = f": [...] {which} {nums} of {r.segments} (searched in order)"
                warnings.append(f"{ck}:{s.id} quote not found verbatim in the full text{where}")
            elif r.status == "joined":
                cut = " + ".join(f"{g:,}" for g in r.gaps)
                warnings.append(f"{ck}:{s.id} authored [...] join — verify the segments "
                                f"({r.segments} found in order; chars cut: {cut})")
    return warnings


# --- quote_loc coverage (SCHEMA §6.4 / the silent-re-parenting failure mode) ----------

_LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl"}


def _fold(text: str) -> str:
    """Fold text for tolerant `quote_loc` comparison: casefold, expand ligatures, drop every
    hyphen and run of whitespace. This is deliberately the same kind of aggressive fold as the
    PDF word-geometry matcher uses to *place* a quote_loc in the first place (pdfview.fold)
    — the two should agree on what "the same text" means. NFKD alone already expands the named
    ligatures (they carry a compatibility decomposition), the explicit table is just insurance for
    any that a given Unicode version doesn't decompose that way.

    The legacy repair runs for the same reason it runs in `pdfview.fold`: this fold compares a
    quote against text pulled straight from the PDF, which on a pre-2005 publisher PDF still
    carries the raw glyph slots that ingest already repaired in the `.md`."""
    text = repair_legacy_glyphs(text)[0]
    for lig, expansion in _LIGATURES.items():
        text = text.replace(lig, expansion)
    text = unicodedata.normalize("NFKD", text)
    text = text.casefold()
    return re.sub(r"[\s\-]+", "", text)


def _rect_text(page: "fitz.Page", rect: list[float]) -> str:
    """Text inside one `quote_loc` rect (a page-fraction box) on `page`."""
    w, h = page.rect.width, page.rect.height
    x0, y0, x1, y1 = rect
    clip = fitz.Rect(x0 * w, y0 * h, x1 * w, y1 * h)
    return page.get_text("text", clip=clip)


def quote_loc_covers(extracted: str, quote: str, window: int = 16, scan: int = 60,
                      floor: int = 6) -> bool:
    """Does the text PyMuPDF extracts from a `quote_loc`'s rects plausibly cover `quote`?

    Both sides are folded (casefold, ligatures expanded, hyphens/whitespace dropped) so
    end-of-line hyphenation ("three-dimen- sional"), ligatures ("ﬂuid-like" vs "fluid-like"),
    and arbitrary line-wrap whitespace never cause a false flag. A watermark ("Downloaded
    from ...") printed diagonally across the page can intrude a few junk glyphs (e.g. "gpg",
    "ygyy") at the start of an extracted rect — sometimes that rect is itself short (a single
    short line), so the junk can be a large fraction of the whole extraction — so instead of
    anchoring at the extracted text's own start we slide a window across it (up to `window`
    wide, shrinking near the end) and ask whether *any* slide of at least `floor` characters
    occurs in the folded quote: a healthy run of genuine overlap anywhere near the front,
    tolerant of a corrupted prefix of any length up to `scan` characters.

    Deliberately permissive: inputs too short to fingerprint reliably (or empty) are treated as
    inconclusive and NOT flagged — a check that flags a correct weld is worse than useless.
    """
    ext = _fold(extracted)
    quo = _fold(quote)
    if not ext or not quo or len(ext) < floor or len(quo) < floor:
        return True
    w = min(window, len(quo))
    limit = min(scan, len(ext) - floor)
    for i in range(limit + 1):
        seg = ext[i:i + w]
        if len(seg) < floor:
            continue
        if seg in quo:
            return True
    return False


def _open_pdf(pdf_dir: Path | None, citekey: str) -> "fitz.Document | None":
    if pdf_dir is None:
        return None
    f = Path(pdf_dir) / f"{citekey}.pdf"
    if not f.is_file():
        return None
    try:
        return fitz.open(f)
    except Exception:
        return None


def verify_quote_locs_graph(graph, pdf_dir: Path | None) -> list[str]:
    """Check every curated slice's `quote_loc` against its own `quote` (SCHEMA §6.4): does the
    PDF text under the stored rects, on the stored page, actually plausibly read as the quote?

    This catches a `quote_loc` that has been mis-parented onto the wrong slice (a stale or
    re-parented block silently welded to the wrong sentence — see store._place_quote_loc) or
    has simply gone stale (the quote text was edited after locating). `lit build` sees valid
    YAML and, on its own, has no way to notice the mismatch — this is the automated stand-in
    for eyeballing every highlight against its PDF. Non-fatal: returns human-readable
    "quote-flag:"-style warnings for the curator, same shape as `polish_graph`'s."""
    warnings: list[str] = []
    for ck, p in graph.papers.items():
        if not p.curated or not any(s.quote and s.quote_loc for s in p.slices):
            continue
        doc = _open_pdf(pdf_dir, ck)
        if doc is None:
            continue
        try:
            for s in p.slices:
                if not s.quote or not s.quote_loc:
                    continue
                page_no = s.quote_loc.get("page")
                rects = s.quote_loc.get("rects") or []
                if page_no is None or not rects:
                    continue
                if not (0 <= page_no < len(doc)):
                    warnings.append(f"{ck}:{s.id} quote_loc page {page_no} out of range")
                    continue
                page = doc[page_no]
                extracted = " ".join(_rect_text(page, r) for r in rects)
                if not quote_loc_covers(extracted, s.quote):
                    warnings.append(f"{ck}:{s.id} quote_loc does not cover its quote")
        finally:
            doc.close()
    return warnings
