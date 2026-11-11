"""Socket-free PDF page rendering for the viewer's quote windows.

Shared by ``lit serve`` (:mod:`litgraph.serve`) and the electronic-lab-notebook plugin
(``litgraph_eln``) so the two serving layers render identically and can't drift — the drift
that once left the plugin without a ``/page`` route, so the quote window rendered nothing.
Pure functions over a PDF path, each with an mtime-keyed module cache; no server object, no
HTTP. The HTTP layers own only validation, routing, and caching headers.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import fitz  # pymupdf — a litgraph hard dependency

from .fulltext import repair_legacy_glyphs

PREVIEW_WIDTH = 552  # px (2x the ~276px tooltip box — crisp on retina, still tiny)
PAGE_WIDTH = 1600    # px — the widest rung: a desktop dock at full zoom
_MAX_PX = 4_000_000  # cap rasterized pixels (oversized-mediabox guard)

# The rungs a page may be rasterized at. The client asks for the width it will actually paint
# (CSS width × capped DPR — the viewer's `rung()`, whose RUNGS must mirror this list) and the
# server snaps *up* to a rung, so a 390px phone and a 412px phone share one cache entry and one
# render instead of each minting their own. 828 is the phone rung, 1100 a desktop dock's, and the
# ladder tops out where the old hardcoded PAGE_WIDTH was.
WIDTHS = (480, 640, 828, 1100, 1600)

# Rendered pages are photographs of text: PNG stores them losslessly and pays ~2.5x the bytes
# for it. JPEG at 82 is the knee of the quality/size curve here — measured on a text-heavy and a
# figure-heavy page, past 82 the size climbs faster than anything the eye picks up.
JPEG_QUALITY = 82

_PAGES: dict[tuple, tuple[float, bytes]] = {}   # (name, n, width, fmt) -> (mtime, image bytes)
_WORDS: dict[tuple, tuple[float, list]] = {}    # (name, n)             -> (mtime, [word,...])
_SIZES: dict[str, tuple[float, list]] = {}      # name                  -> (mtime, [[w,h],...])

# The raster cache is bounded by bytes, not entries, because entry size swings ~20x across rungs.
# It matters more than it used to: a page can now be cached at several widths and two formats, so
# a long session over a 20-paper worklist would otherwise grow without limit. Insertion order is
# the eviction order (dicts are ordered) and a hit moves its key to the end, giving a plain LRU.
_PAGE_BUDGET = 256 * 1024 * 1024
_pages_bytes = 0


def _cache_page(key: tuple, mtime: float, img: bytes) -> None:
    """Store a rendered page, evicting least-recently-used entries to stay under the budget."""
    global _pages_bytes
    old = _PAGES.pop(key, None)
    if old is not None:
        _pages_bytes -= len(old[1])
    _PAGES[key] = (mtime, img)
    _pages_bytes += len(img)
    while _pages_bytes > _PAGE_BUDGET and len(_PAGES) > 1:
        oldest = next(iter(_PAGES))
        _pages_bytes -= len(_PAGES.pop(oldest)[1])


def snap_width(width: int | None) -> int:
    """The ladder rung to render at for a requested ``width``: the narrowest rung that still
    covers it, or the widest rung if it overshoots. ``None`` (an unversioned client that sends no
    ``?w=``) gets :data:`PAGE_WIDTH`, so the old behaviour is the default. Snapping is what keeps
    the render cache from fragmenting across every distinct viewport on the network."""
    if width is None:
        return PAGE_WIDTH
    for rung in WIDTHS:
        if width <= rung:
            return rung
    return WIDTHS[-1]


def render_page(pdf: Path, n: int, width: int, fmt: str = "png") -> bytes:
    """Page ``n`` of ``pdf`` rendered to a ``width``-px image in ``fmt`` (``"png"`` or ``"jpg"``),
    cached until the file's mtime changes. n=0 + :data:`PREVIEW_WIDTH` is the tooltip thumbnail;
    any page feeds the floating quote window. Raises ``IndexError`` on an out-of-range page (the
    HTTP layer turns that into a 404)."""
    pdf = Path(pdf)
    mtime = pdf.stat().st_mtime
    key = (pdf.name, n, width, fmt)
    hit = _PAGES.get(key)
    if hit and hit[0] == mtime:
        _PAGES[key] = _PAGES.pop(key)      # touch: most-recently-used goes to the end
        return hit[1]
    with fitz.open(pdf) as doc:
        page = doc[n]
        zoom = width / page.rect.width
        # clamp total pixels so an oversized mediabox (poster/foldout) can't blow up into a
        # multi-second render — cap the raster, the window still zooms into the bitmap
        px = width * (page.rect.height * zoom)
        if px > _MAX_PX:
            zoom *= (_MAX_PX / px) ** 0.5
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        img = (pix.tobytes("jpg", jpg_quality=JPEG_QUALITY) if fmt == "jpg"
               else pix.tobytes("png"))
    _cache_page(key, mtime, img)
    return img


def page_sizes(pdf: Path) -> list[list[float]]:
    """Per-page point sizes ``[[w, h], ...]`` — the whole-document manifest the viewer uses to
    lay out (and lazily fill) one stacked page box per page. Cached until the PDF's mtime
    changes."""
    pdf = Path(pdf)
    mtime = pdf.stat().st_mtime
    hit = _SIZES.get(pdf.name)
    if hit and hit[0] == mtime:
        return hit[1]
    with fitz.open(pdf) as doc:
        sizes = [[p.rect.width, p.rect.height] for p in doc]
    _SIZES[pdf.name] = (mtime, sizes)
    return sizes


def page_words(pdf: Path, n: int) -> list[dict]:
    """Words of page ``n`` as page-fraction boxes for the selectable text overlay:
    ``[{t, x0,y0,x1,y1, ln}, ...]`` in reading order, ``ln`` a per-line ordinal so the client
    can keep line breaks. Same page.rect normalization as the highlight rects, so the overlay
    registers on the raster without re-derivation. Cached until the PDF's mtime changes."""
    pdf = Path(pdf)
    mtime = pdf.stat().st_mtime
    key = (pdf.name, n)
    hit = _WORDS.get(key)
    if hit and hit[0] == mtime:
        return hit[1]
    with fitz.open(pdf) as doc:
        out = words_of(doc[n])                # IndexError on an out-of-range page → 404 upstream
    _WORDS[key] = (mtime, out)
    return out


def words_of(page: "fitz.Page") -> list[dict]:
    """The uncached body of :func:`page_words`, for a caller already holding an open page. The
    one word extractor behind both ends of a ``quote_loc``: ``lit locate`` builds each rect as
    the bounding box of matched words from it, and the build's coverage check
    (``quotes.verify_quote_locs_graph``) reads the text back by selecting words from it whose
    centre lies inside the rect — so a rect always reads back as the words that made it."""
    w, h = page.rect.width, page.rect.height
    raw = page.get_text("words")              # (x0, y0, x1, y1, text, block, line, word_no)
    out = []
    for x0, y0, x1, y1, t, block, line, _wn in sorted(raw, key=lambda o: (o[5], o[6], o[7])):
        t = "".join(c for c in t if not unicodedata.category(c).startswith("C"))  # strip control/zero-width
        if not t.strip():                     # nothing visible left → not a selectable word
            continue
        out.append({"t": t, "x0": x0 / w, "y0": y0 / h, "x1": x1 / w, "y1": y1 / h,
                    "ln": block * 10000 + line})
    return out


def preview(pdf: Path) -> bytes:
    """First page of ``pdf`` as a PNG for the tooltip thumbnail."""
    return render_page(pdf, 0, PREVIEW_WIDTH)


# ── text matching ────────────────────────────────────────────────────────────────────────────
# One folded-stream matcher serves both readers of this module: the quote resolver placing a
# weld's highlight (`serve.locate_quote`) and the viewer's find bar (:func:`search`). They ask
# different questions of it — "where is this one sentence" vs "where is every occurrence of
# this" — but must agree on what *counts* as a match, or a quote would land where a search says
# there is nothing.

# A search that scanned the whole of a long PDF for a two-letter query would return thousands of
# boxes nobody will walk. Cap it, and say so, rather than pretending the list is complete.
SEARCH_LIMIT = 300


def fold(s: str) -> str:
    """Fold text for matching: NFKD (splits ligatures), lowercase, then keep only alphanumerics —
    dropping whitespace, hyphens and punctuation. That is what lets a match survive a line break,
    a hyphenation seam or an ``ﬁ`` ligature, none of which the reader can see in the text. It also
    makes matching substring-wise (``cell`` is inside ``excellent``) and drops non-Latin script
    entirely, so a query of only Greek folds to nothing.

    Legacy glyph slots are repaired first (:func:`fulltext.repair_legacy_glyphs`). The ``.md`` a
    quote was welded from has that repair applied at ingest, but the PDF this fold matches against
    still carries the raw slots — without it a quote containing "fixed" folds to ``fixed`` on one
    side and ``xed`` on the other (``®`` has no NFKD decomposition, so it is dropped as
    punctuation), and every quote_loc on such a paper would silently fail to place."""
    s = repair_legacy_glyphs(s)[0]
    return re.sub(r"[^0-9a-z]+", "", unicodedata.normalize("NFKD", s).lower())


def word_hits(words: list[dict], query: str, limit: int | None = None) -> list[list[list[float]]]:
    """Every occurrence of ``query`` in one page's :func:`page_words` output, in reading order,
    each as the list of rects covering it — one per layout line, so a hit that wraps or breaks
    across a column comes back boxed in both places. Coordinates are page fractions, inherited
    from ``page_words``. Occurrences don't overlap: the scan resumes past the hit it just found."""
    q = fold(query)
    if not q or not words:
        return []
    stream, owner = [], []          # owner[i] = which word contributed folded character i
    for i, w in enumerate(words):
        folded = fold(w["t"])
        stream.append(folded)
        owner.extend([i] * len(folded))
    hay = "".join(stream)
    out: list[list[list[float]]] = []
    at = 0
    while limit is None or len(out) < limit:
        at = hay.find(q, at)
        if at < 0:
            break
        lines: dict = {}
        for wi in sorted(set(owner[at:at + len(q)])):
            lines.setdefault(words[wi]["ln"], []).append(words[wi])
        out.append([[min(w["x0"] for w in ws), min(w["y0"] for w in ws),
                     max(w["x1"] for w in ws), max(w["y1"] for w in ws)] for ws in lines.values()])
        at += len(q)
    return out


def search(pdf: Path, query: str, limit: int = SEARCH_LIMIT) -> dict:
    """Find ``query`` across a whole PDF: ``{"hits": [{"page", "rects"}, ...], "truncated": bool}``
    in document order, rects page fractions. Backs the viewer's find bar — the page is a raster, so
    the browser's own find-in-page can only see the lazily-built text overlay and would report a
    fraction of the document as all of it. Fed by the mtime-keyed ``page_words`` cache, so the
    second search of a paper pays for no text extraction at all. A query folding to fewer than two
    characters finds nothing (one letter matches half the paper; punctuation alone matches
    nothing)."""
    q = fold(query)
    if len(q) < 2:
        return {"hits": [], "truncated": False}
    hits: list[dict] = []
    for n in range(len(page_sizes(pdf))):
        # ask for one past the cap, so "exactly `limit` hits" isn't reported as "and more"
        for rects in word_hits(page_words(pdf, n), q, limit=limit + 1 - len(hits)):
            hits.append({"page": n, "rects": rects})
        if len(hits) > limit:
            return {"hits": hits[:limit], "truncated": True}
    return {"hits": hits, "truncated": False}
