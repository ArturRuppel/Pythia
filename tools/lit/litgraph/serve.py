# litgraph/serve.py
"""`lit serve`: the viewer over HTTP — live rebuild + PDF preview/open.

`lit build` emits a self-contained file for sharing; serving adds the two things a static
file can't do. (1) Every page load re-reads the data repo's YAML and rebuilds the graph,
so refresh-after-edit is the curation loop — an edit that breaks validation returns the
BuildError as a 500 (the server survives; fix the YAML and refresh). (2) The curated PDFs
(`<citekey>.pdf` in `pdf_dir`) are exposed as `pdfs.json` (which citekeys have one),
`/pdf/<citekey>.pdf` (the file) and `/preview/<citekey>.png` (its first page rendered
server-side — an <img> previews everywhere, unlike embedding a PDF), which the viewer
tooltip upgrades on: hover previews the paper, click opens it. A loopback convenience
for one curator, not a deployment server.

Serving pages to a phone is a bandwidth problem, so three things are negotiated rather than
fixed. `/page/<citekey>/<n>.<png|jpg>?w=` lets the client name the width it will actually paint
(snapped to a `pdfview.WIDTHS` rung) and pick JPEG, which together cut a page from ~1.1 MB to
~165 KB; every PDF-derived body carries an mtime-keyed ETag so a revisit costs a bodiless 304
instead of the whole document again; and text bodies gzip on demand, which matters most for the
~2 MB graph page itself. Omitting `?w=` and asking for `.png` reproduces the old behaviour
exactly, so a static `lit build` artifact and any cached older viewer keep working."""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import fitz  # pymupdf — already a hard dependency (litgraph.pdf)

from litgraph import config, endpoints, pdfview, store
from litgraph.build import render_html
from litgraph.config import load_config
from litgraph.graph import BuildError, build_graph
from litgraph.preview import isolate, isolate_proposal, narrative_key
from litgraph.quotes import JOIN
from litgraph.sources.openalex import OpenAlex

# strictly <citekey>.<ext> — one flat name, no separators, so /pdf/ can't traverse out
_PDF_NAME = re.compile(r"^[A-Za-z0-9]+\.pdf$")
_PNG_NAME = re.compile(r"^[A-Za-z0-9]+\.png$")
_CITEKEY = re.compile(r"^[A-Za-z0-9]+$")
_SLICE_ID = re.compile(r"^(?:oq|[bcqm])\d+$")   # SCHEMA §3; `oq` alternates ahead of the class
_PAGE_REQ = re.compile(r"^/page/([A-Za-z0-9]+)/(\d+)\.(png|jpg)$")
_WORDS_REQ = re.compile(r"^/words/([A-Za-z0-9]+)/(\d+)\.json$")
_PAGES_REQ = re.compile(r"^/pages/([A-Za-z0-9]+)\.json$")
_SEARCH_REQ = re.compile(r"^/search/([A-Za-z0-9]+)\.json$")

# Page rasters, word geometry and the size manifest are all pure functions of the PDF's bytes, so
# they're cacheable for a good long while — a day, then one cheap ETag revalidation that comes
# back 304 with an empty body. (Before this they carried max-age=600, which meant a phone that
# came back after lunch re-downloaded and re-rendered the entire document.) The ETag is keyed on
# the PDF's mtime plus the render parameters, so re-ingesting a PDF invalidates it immediately
# and a revalidation inside the day still gets the right answer.
_IMG_CACHE = "public, max-age=86400"
# The manifest and home-screen icons are tiny and change when the brand does; a day of
# max-age kept a phone on a superseded icon after it was redrawn, so they always revalidate.
_PWA_CACHE = "no-cache"

# Content types worth gzipping: markup, JSON, plain text. PNG/JPEG/PDF are already compressed and
# would only burn CPU to get marginally bigger.
_TEXTISH = re.compile(r"^(text/|application/(json|manifest\+json|javascript))")
_VIEWER_ASSETS = Path(__file__).parent / "viewer"

# The alternative renderings (docs/2026-08-05-additive-graph-views.md), served from the repo's
# `prototypes/` tree at /views/<name>/. They are **serve-only**: a static `lit build` artifact is
# one self-contained file and could not carry them, so the HUD's dropdown is gated on the `views`
# payload key below, which only this server ever sets. Missing tree → no key → no dropdown, which
# is also what happens when litgraph is installed away from a checkout.
_PROTOTYPES = Path(__file__).resolve().parents[3] / "prototypes"
_VIEWS = (("paper-graph", "paper graph", "papers as circles — grounding and co-support"),
          ("claim-graph", "claim graph (flat)", "the support skeleton, layered by distance to floor"),
          ("claim-sphere", "claim sphere (3D)",
           "generality as radius, family as direction — three readings, one panel"),
          ("claim-map", "claim map (overview)",
           "the broad claims on one page — when their evidence landed, how general they are"))
_VIEW_TYPES = {".html": "text/html; charset=utf-8", ".js": "application/javascript",
               ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8"}


def _available_views() -> list[dict]:
    """The prototype views actually present on disk, for the HUD dropdown."""
    if not _PROTOTYPES.is_dir():
        return []
    return [{"slug": s, "label": lab, "note": note} for s, lab, note in _VIEWS
            if (_PROTOTYPES / s / "index.html").is_file()]


# A stored quote is not always one contiguous run of PDF text, and the two ways it breaks both
# have to be split on before matching or the whole anchor matches nothing:
#   * an authored `[...]` join (SCHEMA §6.4) — the curator deliberately elided the middle;
#   * a `<sup>30–32</sup>` citation marker carried in from the `.md`, which the PDF's text layer
#     renders as bare inline numerals ("adhesion30–32, thereby"). Keeping the markup folds to
#     `sup3032sup` and matches nothing; dropping it folds to `adhesionthereby` and *still* misses,
#     because the numerals really are in the PDF stream. Treating it as a boundary is the only
#     reading that matches either way.
# Segments below the floor are dropped rather than searched: a 2–3 character fragment matches
# half the paper, and a junk rect on a highlight is worse than a slightly short one.
_SUP_MARKER = re.compile(r"<sup>.*?</sup>", re.S)
_MIN_SEGMENT_FOLDED = 8


def _segments(anchor: str) -> list[str]:
    """Split a stored quote into the runs that should each match the PDF contiguously."""
    parts: list[str] = []
    for chunk in anchor.split(JOIN):
        parts.extend(_SUP_MARKER.split(chunk))
    segs = [p.strip() for p in parts if len(pdfview.fold(p)) >= _MIN_SEGMENT_FOLDED]
    # An anchor that is *entirely* below the floor still deserves its old one-shot attempt.
    return segs or ([anchor.strip()] if anchor.strip() else [])


def _needles(anchor: str) -> list[str]:
    """Search strings for an anchor, longest → shortest, so a precise full-phrase match is
    always preferred over a short ambiguous one. Two robustness moves: a hyphen-seam variant
    (`"long- ranged"` → `"long-ranged"`, undoing a line-break hyphenation the PDF keeps
    glued) and leading-window backoff (the tail of a sentence often line-wraps or column-
    breaks where `search_for` can't follow)."""
    a = re.sub(r"\s+", " ", anchor).strip()
    variants = [a]
    glued = re.sub(r"-\s+", "-", a)
    if glued != a:
        variants.append(glued)
    maxw = max(len(v.split(" ")) for v in variants)
    out: list[str] = []
    seen: set[str] = set()
    for n in [maxw, 16, 12, 10, 8, 6, 5, 4, 3, 2]:
        if n > maxw:
            continue
        for v in variants:
            words = v.split(" ")
            if n > len(words):
                continue
            needle = " ".join(words[:n])
            if needle not in seen:
                seen.add(needle)
                out.append(needle)
    return out


def locate_quote(pdf: "Path | str", anchor: str) -> dict | None:
    """Best PDF location of `anchor` as {page, rects} with rects page fractions (0..1). Prefers
    the full-coverage word-geometry match (`pdfview.word_hits`: a folded character stream over the
    page's words, so a line-wrapped or hyphenated sentence still matches in *full* — unlike
    `search_for`, which often only matches a leading fragment); only if that fails on every page
    does it fall back to the `search_for` needle backoff, which may cover just that fragment. The
    matcher is shared with the viewer's find bar so a quote can't land where a search sees
    nothing, and it reads through pdfview's mtime-keyed word cache.

    A quote that breaks into several segments (`_segments`: an authored `[...]` join, a `<sup>`
    citation marker) is placed segment by segment and its rects unioned, because no contiguous
    match for the whole string exists — the gap is *the curator's own elision*. Matching the
    joined string as one needle used to fail on every page and drop to the fragment backoff
    below, which highlights the leading run and silently drops the rest: the half of the sentence
    carrying the claim would not light up at all. The page placing the most segments wins, since
    `quote_loc` holds a single page; a segment stranded on another page contributes nothing
    rather than dragging the highlight away from the bulk of the quote."""
    segments = _segments(anchor)
    if not segments:
        return None
    best: tuple[int, int, list[list[float]]] | None = None
    for n in range(len(pdfview.page_sizes(pdf))):
        words = pdfview.page_words(pdf, n)
        rects: list[list[float]] = []
        placed = 0
        for seg in segments:
            hits = pdfview.word_hits(words, seg, limit=1)
            if hits:
                placed += 1
                rects.extend(hits[0])
        if placed and (best is None or placed > best[0]):
            best = (placed, n, rects)
        if placed == len(segments):        # every segment on one page — nothing left to improve
            break
    if best:
        return {"page": best[1], "rects": best[2]}
    with fitz.open(pdf) as doc:
        pages = list(doc)
        for needle in _needles(anchor):            # fragment fallback — rare, better than nothing
            for n, page in enumerate(pages):
                hits = page.search_for(needle)
                if hits:
                    w, h = page.rect.width, page.rect.height
                    return {"page": n, "rects": [[r.x0 / w, r.y0 / h, r.x1 / w, r.y1 / h] for r in hits]}
    return None


def _valid_rects(rects) -> bool:
    """A non-empty list of 4-number boxes, each coordinate a fraction in [0, 1]."""
    if not isinstance(rects, list) or not rects:
        return False
    for r in rects:
        if not (isinstance(r, list) and len(r) == 4):
            return False
        if not all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in r):
            return False
    return True


def _etag(pdf: Path, kind: str, *params) -> str:
    """A validator for anything derived from `pdf`: its mtime + size, plus whatever render
    parameters distinguish this body from its siblings. Cheap (one stat) and exact — re-ingesting
    a PDF changes the mtime, so every derived raster, word list and manifest invalidates at once."""
    st = pdf.stat()
    bits = "-".join(str(p) for p in params)
    return f'"{kind}-{st.st_mtime_ns:x}-{st.st_size:x}{"-" + bits if bits else ""}"'


def _int_param(url: str, name: str) -> int | None:
    """A non-negative integer query parameter, or None when absent or malformed. Callers treat
    None as "client didn't say", never as zero."""
    raw = parse_qs(urlparse(url).query).get(name, [""])[0]
    return int(raw) if raw.isdigit() else None


def _source_version(root: Path, pdf_dir: Path) -> tuple[int, int]:
    """Everything `payload_dict` reads, as a cheap (max mtime ns, file count) fingerprint —
    curated/|claims/|questions/|methods/|topics/, programme/aims/, config.toml's active list,
    and the `.md` full text quotes are polished against.

    The count rides along because a deletion *lowers* the max mtime, so mtime alone would call
    a shrunken repo unchanged. ~600 stats, a millisecond, against a rebuild costing a second."""
    latest, n = 0, 0
    globs = [(root / d, "*.yaml") for d in
             ("curated", "claims", "questions", "methods", "topics")]
    globs.append((root / "programme" / "aims", "*.yaml"))
    globs.append((root / "programme" / "narrative", "*.yaml"))
    globs.append((pdf_dir, "*.md"))
    paths = [root / "stubs.yaml", root / "config.toml"]
    for d, pat in globs:
        try:
            paths.extend(d.glob(pat))
        except OSError:
            pass          # a missing optional dir just contributes nothing
    for p in paths:
        try:
            latest, n = max(latest, p.stat().st_mtime_ns), n + 1
        except OSError:
            pass          # removed mid-glob: the next request restats and settles
    return latest, n


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, root: Path, pdf_dir: Path, read_only: bool = False):
        self.root = Path(root)
        self.pdf_dir = Path(pdf_dir)
        # A mirror serves a checkout it does not own — one `git pull` away from having any local
        # edit clobbered. Read-only refuses the one endpoint that writes synced content (see the
        # `_MUTATING` note below) rather than letting it write into a tree that will be overwritten.
        self.read_only = read_only
        # the built graph.json body, memoized against `_source_version`. `lit serve` rebuilds
        # from YAML on every request by design — that is what makes edit-and-refresh work — but
        # an unchanged repo rebuilding is pure waste, and on a small always-on host it is the
        # difference between an instant refresh and a visible pause. The lock keeps a cold cache
        # from being rebuilt once per concurrent request.
        self._payload_cache: tuple[tuple[int, int], str] | None = None
        self._payload_lock = threading.Lock()
        # stub abstracts: fetched from OpenAlex on hover, memoized for the session (citekey ->
        # abstract str | None). Never persisted — the diffable stubs.yaml stays abstract-free.
        self._abs_cache: dict[str, str | None] = {}
        self._oa = None                 # lazily built OpenAlex client (polite pool via config mailto)
        super().__init__(address, _Handler)


class _Handler(BaseHTTPRequestHandler):
    server_version = "litserve"

    def _send(self, status: int, ctype: str, body: bytes, cache: str = "no-store",
              etag: str | None = None) -> None:
        # The graph page is ~2 MB of HTML-wrapped JSON and it's `no-store`, so a phone re-downloads
        # all of it on every refresh. It gzips ~4x for ~30 ms of CPU, which over anything but
        # loopback is a trade worth making every time. Images are already compressed — skip them.
        enc = None
        if (len(body) > 1024 and _TEXTISH.match(ctype)
                and "gzip" in self.headers.get("Accept-Encoding", "")):
            body, enc = gzip.compress(body, 6), "gzip"
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if enc:
            self.send_header("Content-Encoding", enc)
            self.send_header("Vary", "Accept-Encoding")
        # HTML/JSON are live-rebuilt → never cache; page/preview images are immutable until the
        # PDF changes → let the browser reuse them so reopening a window doesn't refetch/redecode
        self.send_header("Cache-Control", cache)
        if etag:
            self.send_header("ETag", etag)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_cached(self, ctype: str, body_fn, etag: str, cache: str = _IMG_CACHE) -> None:
        """Serve a PDF-derived body under an ETag, answering a matching `If-None-Match` with a
        bodiless 304. `body_fn` is called only on a miss, so a revalidation costs neither the
        render nor the bytes — the difference between a phone re-fetching 15 MB of page rasters on
        every reopen and it fetching nothing at all."""
        if self.headers.get("If-None-Match") == etag:
            self.send_response(HTTPStatus.NOT_MODIFIED)
            self.send_header("ETag", etag)
            self.send_header("Cache-Control", cache)
            self.end_headers()
            return
        self._send(HTTPStatus.OK, ctype, body_fn(), cache=cache, etag=etag)

    def _payload_dict(self, include_aims: bool = True) -> dict:
        """graph.json as a dict, rebuilt from the repo's YAML on every request (may raise
        BuildError) — the shared `endpoints.payload_dict`, which the labbook plugin calls too.

        `views` is assembled here because only this server has it: the alternative renderings
        live at /views/ and need a server to answer for them. Aims (and the narrative axis that
        orders them) default ON here, same as `lit build` (build.emit): `/graph.json` carries the
        programme lane's data in its own "papers" entries / "narrative" key, and the paper-
        centric `order` — the landing column's actual sort — stays exactly as it was, since
        `graph.order` never reads either axis. The preview routes below pass `include_aims=True`
        explicitly too, which is now redundant with the default but kept for clarity at the
        call site: each still means "this route needs the programme layer" on its own terms."""
        return endpoints.payload_dict(self.server.root, self.server.pdf_dir,
                                      include_aims=include_aims, views=_available_views())

    def _isolated(self, key: str) -> dict | None:
        """The isolated payload behind both preview routes, or None when `key` names nothing.

        Two kinds of key, one door: `~<grant>` is a whole proposal (the narrative plus the aims
        under it — preview.isolate_proposal), anything else is a single container. Resolving
        both here is what keeps /preview.html and /preview.json from drifting: `lit preview`
        and the served page must render exactly the same isolated subgraph."""
        full = self._payload_dict(include_aims=True)
        if key.startswith("~"):
            try:
                return isolate_proposal(full, key)
            except KeyError:
                return None
        return isolate(full, key) if key in full["papers"] else None

    def _preview_404(self, raw_path: str):
        key = parse_qs(urlparse(raw_path).query).get("key", [""])[0]
        return self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8",
                          f"nothing to preview: {key}\n".encode())

    def _payload(self) -> str:
        """`_payload_dict` serialized — the graph.json body served at `/` and `/graph.json`.

        Memoized on `_source_version`: a refresh with no edit behind it reuses the string, an
        edit rebuilds. Only this path caches. The preview routes call `_payload_dict` directly
        and stay uncached — they hand the dict to `isolate`, which is free to mutate it, and a
        shared cached dict would leak one preview's edits into the next request."""
        version = _source_version(self.server.root, self.server.pdf_dir)
        with self.server._payload_lock:
            cached = self.server._payload_cache
            if cached is not None and cached[0] == version:
                return cached[1]
            body = json.dumps(self._payload_dict(), ensure_ascii=False)
            self.server._payload_cache = (version, body)
            return body

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        path = unquote(urlparse(self.path).path)
        try:
            if path in ("/", "/index.html"):
                body = render_html(self._payload()).encode()
                return self._send(HTTPStatus.OK, "text/html; charset=utf-8", body)
            if path in ("/manifest.webmanifest", "/icon-192.png", "/icon-512.png",
                        "/apple-touch-icon.png"):
                asset = _VIEWER_ASSETS / path.lstrip("/")
                ctype = ("application/manifest+json" if path.endswith(".webmanifest")
                         else "image/png")
                return self._send(HTTPStatus.OK, ctype, asset.read_bytes(), cache=_PWA_CACHE)
            if path == "/graph.json":
                return self._send(HTTPStatus.OK, "application/json; charset=utf-8",
                                  self._payload().encode())
            if path.startswith("/views/"):
                # An alternative rendering from `prototypes/`. Each one fetches a *relative*
                # `graph.json`, which lands here as /views/<name>/graph.json — so it is answered
                # with this server's live payload rather than a file, and the views read the same
                # rebuilt-from-YAML graph as the board instead of a stale dist artifact.
                parts = path[len("/views/"):].split("/", 1)
                name, rest = parts[0], (parts[1] if len(parts) > 1 else "")
                if name not in {v["slug"] for v in _available_views()}:
                    return self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8",
                                      f"no such view: {name}\n".encode())
                if rest == "graph.json":
                    return self._send(HTTPStatus.OK, "application/json; charset=utf-8",
                                      self._payload().encode())
                base = (_PROTOTYPES / name).resolve()
                target = (base / (rest or "index.html")).resolve()
                # containment check: a crafted `rest` must not escape the view's own directory
                if not target.is_file() or base not in target.parents:
                    return self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8",
                                      b"not found\n")
                ctype = _VIEW_TYPES.get(target.suffix, "application/octet-stream")
                return self._send(HTTPStatus.OK, ctype, target.read_bytes())
            if path == "/preview.html":
                # one container's local subgraph in isolation — the exact `lit preview` view
                # (real `isolate()` + the shared template), for reviewing an in-progress paper
                # from the main viewer. `.html` (not `/preview/…`, taken by PNG thumbnails)
                # keeps the base dir at `/` so the isolated page's own live PDF features resolve.
                # A `~<grant>` key is the whole PROPOSAL page (isolate_proposal): the narrative
                # and the aims under it, which is where the programme layer is read now that it
                # no longer stands as a lane on the board.
                mini = self._isolated(parse_qs(urlparse(self.path).query).get("key", [""])[0])
                if mini is None:
                    return self._preview_404(self.path)
                return self._send(HTTPStatus.OK, "text/html; charset=utf-8",
                                  render_html(json.dumps(mini, ensure_ascii=False)).encode())
            if path == "/preview.json":
                # the isolated subgraph as JSON — same resolution as /preview.html, sans the
                # template. A plain read API for a paper's local subgraph: useful to a script or
                # an agent inspecting `curated/<citekey>.yaml`'s emergent shape without parsing
                # HTML.
                mini = self._isolated(parse_qs(urlparse(self.path).query).get("key", [""])[0])
                if mini is None:
                    return self._preview_404(self.path)
                return self._send(HTTPStatus.OK, "application/json; charset=utf-8",
                                  json.dumps(mini, ensure_ascii=False).encode())
            if path == "/aims.json":
                # the programme index behind the HUD's "programme" pill: one row per thing you
                # can open, each linking to its page at /preview.html?key=<slug>. Proposals lead
                # — a `~<grant>` row is the narrative AND the aims under it, which is how the
                # programme is meant to be read — with the aims listed after, each still openable
                # on its own. The counts are the signals worth seeing without opening a row
                # (programme design §8); for a proposal that is its size, since its assumptions
                # are the aims' and already stated on their rows.
                graph = build_graph(self.server.root)
                rows = [{"slug": narrative_key(grant), "kind": "proposal", "title": n.title or grant,
                         "sections": len(n.sections),
                         "bullets": sum(len(sec.bullets) for sec in n.sections)}
                        for grant, n in sorted(graph.narrative.items())]
                rows += [{"slug": slug, "kind": "aim", "title": a.title, "slices": len(a.slices),
                          "assumptions": sum(1 for s in a.slices if s.load_bearing),
                          "at_risk": sum(1 for s in a.slices
                                         if s.kind == "test" and s.at_risk)}
                         for slug, a in sorted(graph.aims.items())]
                return self._send(HTTPStatus.OK, "application/json; charset=utf-8",
                                  json.dumps(rows).encode())
            if path == "/pdfs.json":
                keys = (sorted(f.stem for f in self.server.pdf_dir.glob("*.pdf"))
                        if self.server.pdf_dir.is_dir() else [])
                return self._send(HTTPStatus.OK, "application/json; charset=utf-8",
                                  json.dumps(keys).encode())
            if path == "/stub-abstract":
                # bib peek for an uncurated stub: OpenAlex abstract by DOI, memoized per session
                # (never persisted — stubs.yaml stays abstract-free). null when there's no DOI,
                # no match, or the lookup fails; the viewer degrades to the bib-only note.
                key = parse_qs(urlparse(self.path).query).get("key", [""])[0]
                if not _CITEKEY.match(key):
                    return self._send(HTTPStatus.BAD_REQUEST, "application/json", b"null")
                return self._send(HTTPStatus.OK, "application/json; charset=utf-8",
                                  json.dumps({"abstract": self._stub_abstract(key)}).encode())
            if path.startswith("/pdf/"):
                name = path[len("/pdf/"):]
                f = self.server.pdf_dir / name
                if not _PDF_NAME.match(name) or not f.is_file():
                    return self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8",
                                      f"no PDF: {name}\n".encode())
                return self._send(HTTPStatus.OK, "application/pdf", f.read_bytes())
            if path.startswith("/preview/"):
                name = path[len("/preview/"):]
                pdf = self.server.pdf_dir / (name[:-4] + ".pdf")
                if not _PNG_NAME.match(name) or not pdf.is_file():
                    return self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8",
                                      f"no preview: {name}\n".encode())
                try:
                    return self._send_cached("image/png", lambda: pdfview.preview(pdf),
                                             _etag(pdf, "preview"))
                except Exception:
                    return self._send(HTTPStatus.INTERNAL_SERVER_ERROR,
                                      "text/plain; charset=utf-8",
                                      f"preview failed: {name}\n".encode())
            m = _PAGE_REQ.match(path)
            if m:
                pdf = self.server.pdf_dir / (m.group(1) + ".pdf")
                if not pdf.is_file():
                    return self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8",
                                      f"no PDF: {m.group(1)}\n".encode())
                n, fmt = int(m.group(2)), m.group(3)
                # `?w=` is the client telling us the width it will actually paint; we snap it to a
                # ladder rung. No `?w=` (a static build, or a cached older viewer) keeps the old
                # full-width render, so the route stays backward compatible.
                width = pdfview.snap_width(_int_param(self.path, "w"))
                ctype = "image/jpeg" if fmt == "jpg" else "image/png"
                try:
                    # bound-check off the cached manifest, so an out-of-range page 404s without
                    # paying for a render (and a revalidation never renders at all)
                    if n >= len(pdfview.page_sizes(pdf)):
                        raise IndexError(n)
                    return self._send_cached(
                        ctype, lambda: pdfview.render_page(pdf, n, width, fmt),
                        _etag(pdf, "page", n, width, fmt))
                except Exception:
                    return self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8",
                                      b"no such page\n")
            m = _PAGES_REQ.match(path)
            if m:
                pdf = self.server.pdf_dir / (m.group(1) + ".pdf")
                if not pdf.is_file():
                    return self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8",
                                      f"no PDF: {m.group(1)}\n".encode())
                try:
                    return self._send_cached(
                        "application/json; charset=utf-8",
                        lambda: json.dumps(pdfview.page_sizes(pdf)).encode(),
                        _etag(pdf, "pages"))
                except Exception:
                    return self._send(HTTPStatus.INTERNAL_SERVER_ERROR, "text/plain; charset=utf-8",
                                      f"page manifest failed: {m.group(1)}\n".encode())
            m = _SEARCH_REQ.match(path)
            if m:
                # the viewer's find bar: every occurrence of `?q=` in the whole document, as page
                # + highlight rects. Derived from the PDF's bytes and the query alone, so it caches
                # exactly like a page render — retyping a query costs one 304.
                pdf = self.server.pdf_dir / (m.group(1) + ".pdf")
                if not pdf.is_file():
                    return self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8",
                                      f"no PDF: {m.group(1)}\n".encode())
                q = parse_qs(urlparse(self.path).query).get("q", [""])[0]
                digest = hashlib.sha1(pdfview.fold(q).encode()).hexdigest()[:12]
                try:
                    return self._send_cached(
                        "application/json; charset=utf-8",
                        lambda: json.dumps(pdfview.search(pdf, q)).encode(),
                        _etag(pdf, "search", digest))
                except Exception:
                    return self._send(HTTPStatus.INTERNAL_SERVER_ERROR, "text/plain; charset=utf-8",
                                      f"search failed: {m.group(1)}\n".encode())
            m = _WORDS_REQ.match(path)
            if m:
                pdf = self.server.pdf_dir / (m.group(1) + ".pdf")
                if not pdf.is_file():
                    return self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8",
                                      f"no PDF: {m.group(1)}\n".encode())
                n = int(m.group(2))
                try:
                    return self._send_cached(
                        "application/json; charset=utf-8",
                        lambda: json.dumps(pdfview.page_words(pdf, n)).encode(),
                        _etag(pdf, "words", n))
                except Exception:
                    return self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8",
                                      b"no such page\n")
            return self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8",
                              b"not found\n")
        except BuildError as e:
            # a mid-edit repo is a normal state — report, keep serving
            return self._send(HTTPStatus.INTERNAL_SERVER_ERROR, "text/plain; charset=utf-8",
                              f"build error: {e}\n".encode())

    def _stub_abstract(self, key: str) -> str | None:
        """OpenAlex abstract for a stub, by its DOI; memoized on the server for the session.
        None when the stub has no DOI, OpenAlex has no match, or the lookup fails (offline)."""
        srv = self.server
        if key in srv._abs_cache:
            return srv._abs_cache[key]
        doi = store.load_taken(srv.root).get(key)  # citekey -> DOI (curated stems + stubs.yaml)
        abstract: str | None = None
        if doi:
            try:
                if srv._oa is None:
                    srv._oa = OpenAlex(mailto=load_config(srv.root).mailto)
                work = srv._oa.fetch_work(doi)
                abstract = work.abstract if work else None
            except Exception:
                abstract = None
        srv._abs_cache[key] = abstract
        return abstract

    def _read_json(self) -> dict:
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    # What a mirror must refuse: /quote_loc writes curated/*.yaml, which is *synced* content —
    # an edit there survives only until the next push overwrites it.
    #
    # /active is deliberately NOT here, though it writes too. It writes config.toml, which every
    # sync excludes precisely because it is host-local, so a mirror's reading list is its own and
    # nothing clobbers it. The reading list is viewer state, not library content, and being able
    # to shuffle it from the couch is most of why the mirror exists.
    #
    # /resolve is absent for a different reason: it's a pure function of a PDF, nothing to guard.
    _MUTATING = frozenset({"/quote_loc"})

    def do_POST(self) -> None:  # noqa: N802 (http.server API)
        path = unquote(urlparse(self.path).path)
        if self.server.read_only and path in self._MUTATING:
            return self._send(HTTPStatus.METHOD_NOT_ALLOWED, "text/plain; charset=utf-8",
                              f"read-only server: {path} is disabled\n".encode())
        try:
            if path == "/resolve":
                body = self._read_json()
                key, anchor = body.get("citekey", ""), body.get("quote", "")
                pdf = self.server.pdf_dir / (key + ".pdf")
                if not _CITEKEY.match(key) or not pdf.is_file() or not anchor:
                    return self._send(HTTPStatus.NOT_FOUND, "application/json", b"null")
                loc = locate_quote(pdf, anchor)
                return self._send(HTTPStatus.OK, "application/json; charset=utf-8",
                                  json.dumps(loc).encode())
            if path == "/quote_loc":
                body = self._read_json()
                key, sid = body.get("citekey", ""), body.get("slice_id", "")
                page, rects = body.get("page"), body.get("rects")
                if not (_CITEKEY.match(key) and _SLICE_ID.match(sid)
                        and isinstance(page, int) and _valid_rects(rects)):
                    return self._send(HTTPStatus.BAD_REQUEST, "text/plain; charset=utf-8",
                                      b"bad quote_loc payload\n")
                try:
                    store.write_quote_loc(self.server.root, key, sid, page, rects)
                except (FileNotFoundError, KeyError) as e:
                    return self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8",
                                      f"{e}\n".encode())
                return self._send(HTTPStatus.OK, "application/json", b'{"ok":true}')
            if path == "/active":
                # the move: add/remove a paper from the reading list (`[curation] active` in
                # config.toml). Curated-only for now — a stub has no local subgraph to curate
                # (stub promotion is a later item). The write is picked up on the next rebuild.
                body = self._read_json()
                key, active = body.get("citekey", ""), body.get("active")
                curated = self.server.root / "curated" / f"{key}.yaml"
                if not _CITEKEY.match(key) or not isinstance(active, bool):
                    return self._send(HTTPStatus.BAD_REQUEST, "text/plain; charset=utf-8",
                                      b"bad active payload\n")
                if active and not curated.is_file():
                    return self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8",
                                      f"not a curated paper: {key}\n".encode())
                new_active = config.set_active(self.server.root, key, active)
                return self._send(HTTPStatus.OK, "application/json; charset=utf-8",
                                  json.dumps({"ok": True, "active": list(new_active)}).encode())
            return self._send(HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8",
                              b"not found\n")
        except (ValueError, json.JSONDecodeError):
            return self._send(HTTPStatus.BAD_REQUEST, "text/plain; charset=utf-8",
                              b"bad request\n")

    do_HEAD = do_GET


def make_server(root: Path, pdf_dir: Path, host: str = "127.0.0.1",
                port: int = 0, read_only: bool = False) -> _Server:
    """Bind (port 0 = ephemeral) but don't serve yet — the caller runs serve_forever()."""
    return _Server((host, port), root=root, pdf_dir=pdf_dir, read_only=read_only)


def serve(root: Path, pdf_dir: Path, host: str = "127.0.0.1", port: int = 8000,
          read_only: bool = False) -> None:
    """Serve until interrupted, announcing the URL. Raises OSError if the port is taken.

    `read_only` is the mirror's mode: a host serving a checkout it does not author. It refuses
    the state-changing POSTs that would write into a tree the next `git pull` overwrites (see
    `_Handler._MUTATING`)."""
    srv = make_server(root, pdf_dir, host=host, port=port, read_only=read_only)
    bound = srv.server_address
    print(f"serving {Path(root).resolve()} at http://{bound[0]}:{bound[1]}/")
    print(f"PDFs from {Path(pdf_dir).resolve()} — Ctrl-C to stop")
    if read_only:
        print("  read-only — the /quote_loc endpoint is disabled")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        srv.server_close()
