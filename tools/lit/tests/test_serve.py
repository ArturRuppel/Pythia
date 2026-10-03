# tests/test_serve.py
"""`lit serve` — loopback only: every request hits 127.0.0.1, no external network."""
import gzip
import http.client
import json
import os
import shutil
import threading
from pathlib import Path

import fitz
import pytest

from litgraph import pdfview
from litgraph.serve import make_server

EXAMPLE = Path(__file__).resolve().parents[3] / "example"


def _tiny_pdf() -> bytes:
    """A real one-page PDF, generated offline — /preview must be able to render it."""
    with fitz.open() as doc:
        doc.new_page().insert_text((72, 100), "fixture paper")
        return doc.tobytes()


FAKE_PDF = _tiny_pdf()


@pytest.fixture()
def repo(tmp_path):
    root = tmp_path / "repo"
    shutil.copytree(EXAMPLE, root)
    (root / "pdfs").mkdir()
    (root / "pdfs" / "Chen2021Sys.pdf").write_bytes(FAKE_PDF)
    return root


@pytest.fixture()
def srv(repo):
    s = make_server(repo, repo / "pdfs")            # port 0 -> ephemeral
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield s
    s.shutdown()
    s.server_close()


def get(srv, path, method="GET", headers=None):
    """Raw request (no client-side path normalization — traversal reaches the server)."""
    conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
    conn.request(method, path, headers=headers or {})
    r = conn.getresponse()
    body = r.read()
    conn.close()
    return r.status, dict(r.getheaders()), body


def post(srv, path, obj):
    """POST a JSON body to the loopback server; return (status, parsed-or-bytes)."""
    conn = http.client.HTTPConnection("127.0.0.1", srv.server_address[1], timeout=5)
    conn.request("POST", path, json.dumps(obj))
    r = conn.getresponse()
    body = r.read()
    conn.close()
    ctype = r.getheader("Content-Type", "")
    return r.status, (json.loads(body) if ctype.startswith("application/json") else body)


def test_index_serves_viewer_with_live_rebuild_headers(srv):
    status, headers, body = get(srv, "/")
    assert status == 200
    assert headers["Content-Type"].startswith("text/html")
    assert headers["Cache-Control"] == "no-store"    # refresh must re-read the YAML
    text = body.decode()
    assert "Chen2021Sys" in text and "__GRAPH_JSON__" not in text


def test_pwa_manifest_and_phone_icons_are_served(srv):
    status, headers, body = get(srv, "/manifest.webmanifest")
    assert status == 200
    assert headers["Content-Type"] == "application/manifest+json"
    manifest = json.loads(body)
    assert manifest["display"] == "standalone" and manifest["start_url"] == "./"
    for name in ("icon-192.png", "icon-512.png", "apple-touch-icon.png"):
        status, headers, body = get(srv, f"/{name}")
        assert status == 200 and headers["Content-Type"] == "image/png"
        assert body.startswith(b"\x89PNG\r\n\x1a\n")


def test_wip_row_click_finds_the_paper_on_the_board(srv):
    # The cockpit's three-window launch (card + PDF popup + terminal) is retired: a reading-list
    # row click now just runs the board's own gotoPaper, same as a search result or a library row.
    text = get(srv, "/")[2].decode()
    enter = text.split("function enter(k){", 1)[1].split("async function returnToGraph", 1)[0]
    assert "gotoPaper(k)" in enter
    assert "window.open(" not in enter
    assert 'fetch("term"' not in enter and "PHONE_LAUNCH" not in enter


def test_the_pdf_split_follows_the_window_shape_in_every_mode(srv):
    """Landscape docks the PDF on the right, portrait stacks it underneath, and no rule is scoped
    to a mode class — every window gets the identical split."""
    text = get(srv, "/")[2].decode()
    portrait = text.split("@media (orientation:portrait){", 1)[1].split("\n  }", 1)[0]
    for sel in ("#board", "#dockEmpty", ".pw-side", "#dockGrip"):
        assert f"body.dock-open {sel}" in portrait, sel
    # each axis keeps its own persisted fraction, so a rotate restores that shape's ratio
    assert "--dock-w:44%;--dock-h:52%" in text
    assert '{w: "lit.dock.w", h: "lit.dock.h"}' in text
    assert 'const ax = portrait() ? "h" : "w";' in text


def test_the_hud_slides_away_on_scroll_without_moving_the_board(srv):
    """The bar is a transform, not a layout change: the board is full-height and the stage pads its
    own top by the measured bar height, so hiding the bar can't reflow the graph or jump the
    scroll. The clearance divides by the board zoom: it is a distance on the glass, not on the
    stage, so it must stay the bar's height however far back the camera stands."""
    text = get(srv, "/")[2].decode()
    assert "body.hud-off #hud{transform:translateY(-100%)}" in text
    assert "#board{position:absolute;inset:0;overflow:auto}" in text
    assert "padding:calc(var(--hud-h) / var(--bz) + 34px)" in text
    assert "body{--hud-h:46px;--hud-top:var(--hud-h)}" in text
    assert "body.hud-off{--hud-top:0px}" in text          # the dock grows into the space too
    assert "top:var(--hud-top)" in text
    # Serve-only controls are revealed after the initial measurement. If that makes the HUD wrap,
    # its own resize (not merely a window resize) must refresh the board's protected top inset.
    assert 'new ResizeObserver(measure).observe(hud)' in text


def test_the_board_and_the_pdf_zoom_separately(srv):
    """Two surfaces read side by side at two distances — a page at 200% beside a board at 60% is
    the ordinary way to curate — so they share no control and no stored state."""
    text = get(srv, "/")[2].decode()
    # the board is a camera: one transform over a stage, so zooming re-wraps nothing
    assert "#stage{position:absolute;top:0;left:0;transform:scale(var(--bz));" in text
    assert 'KEY = "lit.board.zoom"' in text
    # …and the PDF keeps its own, restored on every re-aim rather than reset to fit-width
    assert 'KEY = "lit.pdf.zoom"' in text
    assert '<span class="pw-zoom" hidden' in text        # revealed by wireZoom, per mount
    assert 'id="bzoom"' in text                          # the board's lives in the HUD instead
    # both are sliders over a log-spaced track: zoom multiplies, so half and double have to sit
    # the same distance either side of 100%
    assert text.count('<input type="range" min="0" max="1000" step="1"') == 2
    assert "toZoom(v, min, max)" in text


def test_graph_json_endpoint(srv):
    status, headers, body = get(srv, "/graph.json")
    assert status == 200 and headers["Content-Type"].startswith("application/json")
    assert "Chen2021Sys" in json.loads(body)["papers"]


def test_preview_html_isolates_one_curated_paper(srv):
    status, headers, body = get(srv, "/preview.html?key=Chen2021Sys")
    assert status == 200 and headers["Content-Type"].startswith("text/html")
    # the same viewer template, inlined with the isolate()'d single-paper payload
    assert b'"order": ["Chen2021Sys"]' in body


def test_preview_html_rejects_unknown_and_stub_keys(srv):
    # a citekey with no curated file
    assert get(srv, "/preview.html?key=NoSuchPaper2099")[0] == 404
    # a stub (uncurated container) is not previewable — only curated papers isolate
    assert get(srv, "/preview.html?key=Bench2016Tools")[0] == 404


def test_preview_json_isolates_one_curated_paper(srv):
    # the JSON twin of /preview.html: same isolated payload, sans the HTML template
    status, headers, body = get(srv, "/preview.json?key=Chen2021Sys")
    assert status == 200 and headers["Content-Type"].startswith("application/json")
    mini = json.loads(body)
    assert mini["order"] == ["Chen2021Sys"] and "Chen2021Sys" in mini["papers"]


def test_preview_json_rejects_unknown_and_stub_keys(srv):
    assert get(srv, "/preview.json?key=NoSuchPaper2099")[0] == 404
    assert get(srv, "/preview.json?key=Bench2016Tools")[0] == 404


def test_pdf_manifest_and_fetch(srv):
    status, _, body = get(srv, "/pdfs.json")
    assert status == 200
    assert json.loads(body) == ["Chen2021Sys"]       # only papers with a PDF on disk
    status, headers, body = get(srv, "/pdf/Chen2021Sys.pdf")
    assert status == 200
    assert headers["Content-Type"] == "application/pdf"
    assert body == FAKE_PDF
    # HEAD: headers only
    status, headers, body = get(srv, "/pdf/Chen2021Sys.pdf", method="HEAD")
    assert status == 200 and body == b""
    assert headers["Content-Length"] == str(len(FAKE_PDF))


def test_preview_renders_first_page_png_and_caches(srv):
    status, headers, body = get(srv, "/preview/Chen2021Sys.png")
    assert status == 200
    assert headers["Content-Type"] == "image/png"
    assert body.startswith(b"\x89PNG\r\n")            # real pixels, not a stub
    assert get(srv, "/preview/Chen2021Sys.png")[2] == body   # mtime-cached


def test_preview_missing_or_corrupt(srv, repo):
    assert get(srv, "/preview/Nope2020Xyz.png")[0] == 404
    (repo / "pdfs" / "Bad2020Jrnl.pdf").write_bytes(b"not a pdf at all")
    assert get(srv, "/preview/Bad2020Jrnl.png")[0] == 500    # named, server survives
    assert get(srv, "/pdfs.json")[0] == 200


def test_pdf_missing_is_404(srv):
    status, _, _ = get(srv, "/pdf/Nope2020Xyz.pdf")
    assert status == 404


def test_pdf_traversal_is_rejected(srv):
    # only a flat <citekey>.<ext> name is servable — separators and dotfiles never resolve
    for path in ("/pdf/../stubs.yaml", "/pdf/..%2fstubs.yaml",
                 "/pdf/%2e%2e/curated/Chen2021Sys.yaml", "/pdf/sub/dir.pdf",
                 "/pdf/.hidden.pdf", "/preview/../stubs.yaml", "/preview/a/b.png"):
        status, _, _ = get(srv, path)
        assert status == 404, path


def test_unknown_path_is_404(srv):
    assert get(srv, "/etc/passwd")[0] == 404


def test_refresh_rebuilds_from_yaml(srv, repo):
    f = repo / "curated" / "Chen2021Sys.yaml"
    f.write_text(f.read_text().replace(
        "Batching improves throughput", "Batching improves LIVE-EDITED throughput"))
    status, _, body = get(srv, "/")
    assert status == 200 and "LIVE-EDITED" in body.decode()


def test_broken_edit_returns_500_and_recovers(srv, repo):
    f = repo / "curated" / "Chen2021Sys.yaml"
    good = f.read_text()
    f.write_text(good.replace("grounded_in:  [m1]", "grounded_in:  [m99]", 1))
    status, _, body = get(srv, "/")
    assert status == 500 and "m99" in body.decode()   # names the offender, server survives
    f.write_text(good)
    assert get(srv, "/")[0] == 200


# ── PDF quote windows: any-page render, search_for resolver, quote_loc write-back ─────────

from litgraph.serve import _needles


def test_needles_prefers_long_then_backs_off_with_hyphen_variant():
    ns = _needles("Fast and long- ranged propagation of mechanical force here")
    # the full phrase (whitespace-normalized) leads; a hyphen-glued variant appears
    assert ns[0] == "Fast and long- ranged propagation of mechanical force here"
    assert "Fast and long-ranged propagation of mechanical force here" in ns
    # leading-window backoff, longest → shortest, down to two words
    assert ns[-1] == "Fast and"
    assert ns.index("Fast and long-") < ns.index("Fast and") or "Fast and long-" not in ns


def test_locate_quote_covers_a_hyphenated_line_break(tmp_path):
    # the word-geometry matcher must cover the WHOLE quote even where a word is hyphenated
    # across a line break — exactly where `search_for` fails and the old resolver boxed only a
    # leading fragment (SCHEMA §6 full-coverage anchors)
    from litgraph.serve import locate_quote
    p = tmp_path / "hyph.pdf"
    with fitz.open() as doc:
        pg = doc.new_page()
        pg.insert_text((72, 100), "mechano-")        # a word split across the line break …
        pg.insert_text((72, 120), "structural coupling")
        doc.save(str(p))
    loc = locate_quote(p, "mechanostructural coupling")   # … re-joined in the .md-derived quote
    assert loc and loc["page"] == 0
    assert len(loc["rects"]) == 2                    # both lines boxed, head + tail
    assert fitz.open(p)[0].search_for("mechanostructural coupling") == []  # search_for alone can't


def test_segments_splits_authored_joins_and_sup_markers():
    from litgraph.serve import _segments
    # an authored [...] elision is a boundary: the halves are separated in the PDF
    assert _segments("the first half here [...] and the second half here") == [
        "the first half here", "and the second half here"]
    # a <sup> citation marker is one too — the PDF's text layer carries the numerals inline,
    # so neither keeping nor dropping the markup yields a contiguous match
    assert _segments("focal adhesion<sup>30-32</sup> , thereby indicating something") == [
        "focal adhesion", ", thereby indicating something"]
    # a plain contiguous quote is unchanged (one segment, matched exactly as before)
    assert _segments("one plain contiguous sentence") == ["one plain contiguous sentence"]
    # fragments too short to fingerprint are dropped rather than searched …
    assert _segments("a long enough leading segment here [...] of") == [
        "a long enough leading segment here"]
    # … unless that leaves nothing, in which case the whole anchor still gets its one attempt
    assert _segments("of") == ["of"]


def test_locate_quote_unions_the_rects_of_a_joined_quote(tmp_path):
    # a [...] join has NO contiguous match, so the whole-anchor matcher failed on every page and
    # the old resolver fell through to the fragment backoff — boxing only the leading run and
    # silently dropping the half of the sentence that carries the claim
    from litgraph.serve import locate_quote
    p = tmp_path / "joined.pdf"
    with fitz.open() as doc:
        pg = doc.new_page()
        pg.insert_text((72, 100), "Even where no backbone permeates")
        pg.insert_text((72, 140), "the tissue self-organizes a tension network")
        doc.save(str(p))
    q = "Even where no backbone permeates [...] the tissue self-organizes a tension network"
    loc = locate_quote(p, q)
    assert loc and loc["page"] == 0
    assert len(loc["rects"]) == 2                     # BOTH segments boxed, not just the first
    page = fitz.open(p)[0]
    w, h = page.rect.width, page.rect.height
    covered = " ".join(page.get_textbox(fitz.Rect(r[0] * w, r[1] * h, r[2] * w, r[3] * h))
                       for r in loc["rects"])
    assert "backbone" in covered and "tension network" in covered


def test_locate_quote_prefers_the_page_carrying_the_most_segments(tmp_path):
    # quote_loc holds ONE page, so a join straddling a page break cannot be fully represented.
    # The bulk of the quote wins; a stranded segment contributes nothing rather than dragging
    # the highlight onto a page the reader is not looking at.
    from litgraph.serve import locate_quote
    p = tmp_path / "split.pdf"
    with fitz.open() as doc:
        one = doc.new_page()
        one.insert_text((72, 100), "the leading claim segment sits here")
        one.insert_text((72, 140), "and a second segment joins it here")
        two = doc.new_page()
        two.insert_text((72, 100), "a lone trailing segment over here")
        doc.save(str(p))
    loc = locate_quote(p, "the leading claim segment sits here [...] and a second segment joins "
                          "it here [...] a lone trailing segment over here")
    assert loc and loc["page"] == 0 and len(loc["rects"]) == 2


def test_search_finds_every_occurrence_including_across_a_line_break(tmp_path):
    # the find bar's matcher IS the quote resolver's, so a hyphenation seam and a line break are
    # invisible to it — and unlike the resolver it must return every occurrence, in document order
    p = tmp_path / "many.pdf"
    with fitz.open() as doc:
        pg = doc.new_page()
        pg.insert_text((72, 100), "traction force here")
        pg.insert_text((72, 140), "and traction-")           # … split across the line break
        pg.insert_text((72, 160), "force again")
        doc.new_page().insert_text((72, 100), "traction force on page two")
        doc.save(str(p))
    res = pdfview.search(p, "Traction Force")                # case folds away too
    assert res["truncated"] is False
    assert [h["page"] for h in res["hits"]] == [0, 0, 1]     # document order
    assert len(res["hits"][1]["rects"]) == 2                 # the split hit is boxed on both lines
    for h in res["hits"]:
        assert all(len(r) == 4 and all(0 <= v <= 1 for v in r) for r in h["rects"])
    assert res["hits"][0]["rects"] != res["hits"][1]["rects"]


def test_search_truncates_rather_than_overstating(tmp_path):
    # a two-letter query over a real paper matches thousands of times; the cap is honest about it
    p = tmp_path / "rep.pdf"
    with fitz.open() as doc:
        doc.new_page().insert_text((72, 100), "cell cell cell cell cell")
        doc.save(str(p))
    capped = pdfview.search(p, "cell", limit=3)
    assert capped["truncated"] is True and len(capped["hits"]) == 3
    full = pdfview.search(p, "cell", limit=10)
    assert full["truncated"] is False and len(full["hits"]) == 5   # exactly 5 is not "5 and more"
    assert pdfview.search(p, "cell", limit=5)["truncated"] is False
    # too short to be worth thousands of boxes; punctuation alone folds to nothing at all
    assert pdfview.search(p, "c") == {"hits": [], "truncated": False}
    assert pdfview.search(p, "— ") == {"hits": [], "truncated": False}


def test_search_endpoint_serves_hits_and_revalidates_per_query(srv):
    status, headers, body = get(srv, "/search/Chen2021Sys.json?q=fixture")
    assert status == 200 and headers["Content-Type"].startswith("application/json")
    assert "max-age" in headers["Cache-Control"]             # a function of the PDF and the query
    res = json.loads(body)
    assert res["truncated"] is False and len(res["hits"]) == 1
    assert res["hits"][0]["page"] == 0 and res["hits"][0]["rects"]
    # the ETag keys on the query: retyping one costs a 304, a different one can't collide with it
    tag = headers["ETag"]
    assert get(srv, "/search/Chen2021Sys.json?q=fixture",
               headers={"If-None-Match": tag})[0] == 304
    assert get(srv, "/search/Chen2021Sys.json?q=paper")[1]["ETag"] != tag
    assert json.loads(get(srv, "/search/Chen2021Sys.json?q=absent")[2])["hits"] == []
    assert get(srv, "/search/Nope2020Xyz.json?q=x")[0] == 404


def test_the_find_bar_searches_the_whole_document_not_the_lazy_text_overlay(srv):
    """The browser's own Ctrl+F can only see the transparent word overlay, and that is built
    lazily for pages already visited in text mode — it would search a fraction of the paper and
    report it as all of it. The find bar asks the server for the whole document instead."""
    text = get(srv, "/")[2].decode()
    assert "search/${key}.json?q=${encodeURIComponent(q)}" in text
    assert "attachFind(win, key, {body, pages, view});" in text
    # the chrome is built with every window but only the whole-document mount unhides it, so the
    # single-page fallback can't offer a search over one page of twenty
    assert 'data-t="find"' in text and "hidden>🔍" in text
    assert "btn.hidden = false;" in text
    # ctrl/⌘-F is taken only while a PDF is actually on screen — otherwise the browser keeps it
    assert 'const w = document.querySelector(".pw");' in text
    # a search hit never wears the authored quote's yellow: its own blue, orange for the current
    assert ".pw-fh{" in text and ".pw-fh.on{" in text and ".pw-hl{" in text


def test_page_render_any_page_and_out_of_range(srv):
    status, headers, body = get(srv, "/page/Chen2021Sys/0.png")
    assert status == 200 and headers["Content-Type"] == "image/png"
    assert body.startswith(b"\x89PNG\r\n")
    assert get(srv, "/page/Chen2021Sys/9.png")[0] == 404   # one-page fixture: page 9 absent
    assert get(srv, "/page/Nope2020Xyz/0.png")[0] == 404


def test_text_bodies_are_gzipped_only_when_the_client_asks(srv):
    # the graph page is ~2 MB of HTML-wrapped JSON on every load — the single biggest thing a
    # phone waits for, and it compresses ~4x
    plain = get(srv, "/")
    assert plain[0] == 200 and "Content-Encoding" not in plain[1]
    gz = get(srv, "/", headers={"Accept-Encoding": "gzip, deflate"})
    assert gz[0] == 200 and gz[1]["Content-Encoding"] == "gzip"
    assert gz[1]["Vary"] == "Accept-Encoding"
    assert gzip.decompress(gz[2]) == plain[2]                # same bytes, fewer on the wire
    assert len(gz[2]) < len(plain[2])
    assert int(gz[1]["Content-Length"]) == len(gz[2])        # length describes the encoded body
    # already-compressed bodies are left alone
    img = get(srv, "/page/Chen2021Sys/0.jpg?w=828", headers={"Accept-Encoding": "gzip"})
    assert img[0] == 200 and "Content-Encoding" not in img[1]


def test_page_render_serves_jpeg_at_a_requested_width(srv):
    # the mobile path: the client asks for the width it will actually paint and gets JPEG, which
    # is ~7x smaller than the old full-width PNG for the same page
    status, headers, jpg = get(srv, "/page/Chen2021Sys/0.jpg?w=828")
    assert status == 200 and headers["Content-Type"] == "image/jpeg"
    assert jpg.startswith(b"\xff\xd8\xff")                   # JPEG SOI
    png = get(srv, "/page/Chen2021Sys/0.png")[2]
    assert len(jpg) < len(png)
    assert get(srv, "/page/Chen2021Sys/9.jpg?w=828")[0] == 404
    assert get(srv, "/page/Nope2020Xyz/0.jpg?w=828")[0] == 404


def test_page_width_snaps_to_a_shared_ladder_rung(srv):
    # every phone viewport in a rung shares one render + one cache entry, so the raster cache
    # can't fragment across the arbitrary widths real devices report
    a = get(srv, "/page/Chen2021Sys/0.jpg?w=390")
    b = get(srv, "/page/Chen2021Sys/0.jpg?w=412")
    assert a[2] == b[2] and a[1]["ETag"] == b[1]["ETag"]     # both snap to the 480 rung
    wide = get(srv, "/page/Chen2021Sys/0.jpg?w=1100")
    assert wide[1]["ETag"] != a[1]["ETag"] and len(wide[2]) > len(a[2])
    # an absurd width is clamped to the top rung rather than honoured
    assert get(srv, "/page/Chen2021Sys/0.jpg?w=99999")[1]["ETag"] == \
        get(srv, f"/page/Chen2021Sys/0.jpg?w={pdfview.WIDTHS[-1]}")[1]["ETag"]
    # no ?w= at all (a static build, or a viewer cached before this existed) still works
    assert get(srv, "/page/Chen2021Sys/0.png")[0] == 200


def test_pdf_derived_bodies_revalidate_with_an_etag(srv):
    # a revisit costs one bodiless 304 instead of re-downloading (and re-rendering) the document
    for path in ("/page/Chen2021Sys/0.jpg?w=828", "/words/Chen2021Sys/0.json",
                 "/pages/Chen2021Sys.json", "/preview/Chen2021Sys.png"):
        status, headers, body = get(srv, path)
        assert status == 200 and body, path
        etag = headers["ETag"]
        assert "max-age=86400" in headers["Cache-Control"], path
        s2, h2, b2 = get(srv, path, headers={"If-None-Match": etag})
        assert (s2, b2) == (304, b""), path
        assert h2["ETag"] == etag, path
        # a stale validator still gets the real body
        assert get(srv, path, headers={"If-None-Match": '"stale"'})[0] == 200, path


def test_etag_changes_when_the_pdf_does(srv, repo):
    before = get(srv, "/page/Chen2021Sys/0.jpg?w=828")[1]["ETag"]
    with fitz.open() as doc:                                 # a different one-page PDF
        doc.new_page().insert_text((72, 100), "revised paper")
        (repo / "pdfs" / "Chen2021Sys.pdf").write_bytes(doc.tobytes())
    after = get(srv, "/page/Chen2021Sys/0.jpg?w=828")
    assert after[1]["ETag"] != before                        # re-ingest invalidates immediately
    assert get(srv, "/page/Chen2021Sys/0.jpg?w=828",
               headers={"If-None-Match": before})[0] == 200  # the old validator no longer matches


def test_words_endpoint_serves_page_fraction_boxes(srv):
    # the selectable text overlay is fed by per-page word geometry, same page.rect normalization
    # as the highlight rects so it registers on the raster
    status, headers, body = get(srv, "/words/Chen2021Sys/0.json")
    assert status == 200 and headers["Content-Type"].startswith("application/json")
    assert "max-age" in headers["Cache-Control"]            # immutable until the PDF's mtime changes
    words = json.loads(body)
    assert [w["t"] for w in words][:2] == ["fixture", "paper"]   # reading order, whitespace dropped
    for w in words:
        assert set(w) == {"t", "x0", "y0", "x1", "y1", "ln"}
        assert all(0 <= w[k] <= 1 for k in ("x0", "y0", "x1", "y1"))
    assert get(srv, "/words/Chen2021Sys/9.json")[0] == 404   # one-page fixture: page 9 absent
    assert get(srv, "/words/Nope2020Xyz/0.json")[0] == 404


def test_pages_manifest_lists_every_page_size(srv):
    # the pinned viewer lays out the whole document from this per-page point-size manifest
    status, headers, body = get(srv, "/pages/Chen2021Sys.json")
    assert status == 200 and headers["Content-Type"].startswith("application/json")
    assert "max-age" in headers["Cache-Control"]
    sizes = json.loads(body)
    assert len(sizes) == 1                                   # one-page fixture
    assert all(len(s) == 2 and s[0] > 0 and s[1] > 0 for s in sizes)
    assert get(srv, "/pages/Nope2020Xyz.json")[0] == 404


def test_page_and_preview_are_browser_cacheable_but_html_is_not(srv):
    # live-rebuilt HTML must never cache; immutable page/preview images should, so reopening a
    # quote window doesn't refetch/redecode
    assert get(srv, "/")[1]["Cache-Control"] == "no-store"
    assert "max-age" in get(srv, "/page/Chen2021Sys/0.png")[1]["Cache-Control"]
    assert "max-age" in get(srv, "/preview/Chen2021Sys.png")[1]["Cache-Control"]


def test_resolve_hits_and_misses(srv):
    status, loc = post(srv, "/resolve", {"citekey": "Chen2021Sys", "quote": "fixture paper"})
    assert status == 200 and loc["page"] == 0
    assert len(loc["rects"]) >= 1
    assert all(len(r) == 4 and all(0 <= v <= 1 for v in r) for r in loc["rects"])
    # absent text → null (curator then draws the box by hand)
    assert post(srv, "/resolve", {"citekey": "Chen2021Sys", "quote": "no such sentence here"})[1] is None
    assert post(srv, "/resolve", {"citekey": "Nope2020Xyz", "quote": "x"}) == (404, None)


def test_quote_loc_writeback_persists_and_shows_in_graph(srv, repo):
    rects = [[0.1, 0.2, 0.5, 0.23]]
    status, res = post(srv, "/quote_loc",
                       {"citekey": "Chen2021Sys", "slice_id": "c1", "page": 0, "rects": rects})
    assert status == 200 and res == {"ok": True}
    # written into the YAML, round-tripped
    from ruamel.yaml import YAML
    doc = YAML(typ="safe").load((repo / "curated" / "Chen2021Sys.yaml").read_text())
    c1 = next(s for s in doc["claims"] if s["id"] == "c1")
    assert c1["quote_loc"] == {"page": 0, "rects": rects}
    # and surfaced in the rebuilt graph.json
    g = json.loads(get(srv, "/graph.json")[2])
    s = next(x for x in g["papers"]["Chen2021Sys"]["slices"] if x["id"] == "c1")
    assert s["loc"] == {"page": 0, "rects": rects}


def test_quote_loc_rejects_bad_payloads(srv):
    assert post(srv, "/quote_loc",                       # rect out of [0,1]
                {"citekey": "Chen2021Sys", "slice_id": "c1", "page": 0, "rects": [[0, 0, 2, 1]]})[0] == 400
    assert post(srv, "/quote_loc",                       # empty rects
                {"citekey": "Chen2021Sys", "slice_id": "c1", "page": 0, "rects": []})[0] == 400
    assert post(srv, "/quote_loc",                       # unknown slice
                {"citekey": "Chen2021Sys", "slice_id": "c9", "page": 0, "rects": [[0, 0, 1, 1]]})[0] == 404
    assert post(srv, "/quote_loc",                       # bad slice-id form
                {"citekey": "Chen2021Sys", "slice_id": "../x", "page": 0, "rects": [[0, 0, 1, 1]]})[0] == 400


# ── the move: POST /active writes the reading list ────────────────────────────────────────


def test_active_move_writes_config_and_shows_in_graph(srv, repo):
    from litgraph.config import load_config
    status, res = post(srv, "/active", {"citekey": "Chen2021Sys", "active": True})
    assert status == 200 and res == {"ok": True, "active": ["Chen2021Sys"]}
    # persisted to config.toml (curator state, deployment-local)
    assert load_config(repo).active == ("Chen2021Sys",)
    # and the rebuilt graph.json carries it (re-read per request), so the viewer filters it out
    assert json.loads(get(srv, "/graph.json")[2])["active"] == ["Chen2021Sys"]
    # symmetric removal
    _, res = post(srv, "/active", {"citekey": "Chen2021Sys", "active": False})
    assert res == {"ok": True, "active": []}
    assert load_config(repo).active == ()


def test_active_move_rejects_non_curated_and_bad_payloads(srv, repo):
    # a stub / unknown key has no local subgraph to curate → 404 (curated-only for now)
    assert post(srv, "/active", {"citekey": "Patel2017Vldb", "active": True})[0] == 404
    assert post(srv, "/active", {"citekey": "Nope2099X", "active": True})[0] == 404
    # malformed: missing / non-bool `active`, or a traversal citekey
    assert post(srv, "/active", {"citekey": "Chen2021Sys"})[0] == 400
    assert post(srv, "/active", {"citekey": "Chen2021Sys", "active": "yes"})[0] == 400
    assert post(srv, "/active", {"citekey": "../etc", "active": True})[0] == 400
    # a non-curated key can still be *removed* (idempotent cleanup — no curated-file check)
    assert post(srv, "/active", {"citekey": "Nope2099X", "active": False})[0] == 200


# ── CLI wiring ───────────────────────────────────────────────────────────────────────────

from litgraph import cli


def test_cli_serve_wires_root_port_and_pdf_dir(repo, monkeypatch):
    calls = {}
    monkeypatch.setattr(cli, "serve", lambda root, pdf_dir, host, port, read_only: calls.update(
        root=Path(root), pdf_dir=Path(pdf_dir), host=host, port=port, read_only=read_only))
    rc = cli.main(["serve", "--root", str(repo), "--host", "100.64.0.1", "--port", "0"])
    assert rc == 0
    assert calls == {"root": repo, "pdf_dir": repo / "pdfs",
                     "host": "100.64.0.1", "port": 0, "read_only": False}
    rc = cli.main(["serve", "--root", str(repo), "--pdf-dir", str(repo / "elsewhere")])
    assert (rc == 0 and calls["pdf_dir"] == repo / "elsewhere"
            and calls["host"] == "127.0.0.1" and calls["port"] == 8000)
    rc = cli.main(["serve", "--root", str(repo), "--read-only"])
    assert rc == 0 and calls["read_only"] is True


def test_cli_has_no_focus_command(capsys):
    # `lit focus` steered the cockpit's separate paper window (POST /focus); both are retired.
    # argparse rejects an unknown subcommand with usage + SystemExit(2), same as any typo.
    with pytest.raises(SystemExit) as exc:
        cli.main(["focus", "Chen2021Sys"])
    assert exc.value.code == 2
    assert "invalid choice: 'focus'" in capsys.readouterr().err


def test_cli_curate_moves_paper_in_and_out(repo, capsys):
    from litgraph.config import load_config
    rc = cli.main(["curate", "Chen2021Sys", "--root", str(repo)])
    assert rc == 0 and "moved into" in capsys.readouterr().out
    assert load_config(repo).active == ("Chen2021Sys",)
    rc = cli.main(["curate", "Chen2021Sys", "--done", "--root", str(repo)])
    assert rc == 0 and "returned to the graph" in capsys.readouterr().out
    assert load_config(repo).active == ()


def test_cli_curate_rejects_non_curated(repo, capsys):
    rc = cli.main(["curate", "Patel2017Vldb", "--root", str(repo)])   # a stub, not curated
    assert rc == 1 and "not a curated paper" in capsys.readouterr().err


def test_cli_serve_fails_fast_on_broken_repo(repo, monkeypatch, capsys):
    monkeypatch.setattr(cli, "serve", lambda *a, **k: pytest.fail("must not serve"))
    f = repo / "curated" / "Chen2021Sys.yaml"
    f.write_text(f.read_text().replace("grounded_in:  [m1]", "grounded_in:  [m99]", 1))
    rc = cli.main(["serve", "--root", str(repo)])
    assert rc == 1
    assert "m99" in capsys.readouterr().err


# ── stub abstracts: live OpenAlex fetch on hover, memoized, never persisted ────────────────
def test_stub_abstract_fetches_and_caches(srv):
    from litgraph.model import Work

    calls = []

    class FakeOA:
        def fetch_work(self, doi):
            calls.append(doi)
            return Work(doi=doi, title="t", year=2016, type_raw="article",
                        venue_display="V", abstract="A synthesized abstract.")

    srv._oa = FakeOA()   # pre-seed so no real network is touched
    status, _, body = get(srv, "/stub-abstract?key=Bench2016Tools")
    assert status == 200 and json.loads(body) == {"abstract": "A synthesized abstract."}
    get(srv, "/stub-abstract?key=Bench2016Tools")       # second hit served from session cache
    assert calls == ["10.0000/synth.bench2016"]          # fetched exactly once


def test_stub_abstract_bad_key_and_no_match(srv):
    assert get(srv, "/stub-abstract?key=../etc")[0] == 400   # malformed citekey

    class NoneOA:
        def fetch_work(self, doi):
            return None

    srv._oa = NoneOA()
    status, _, body = get(srv, "/stub-abstract?key=Zhao2014Nsdi")
    assert status == 200 and json.loads(body) == {"abstract": None}


# --- the programme index (the HUD's "programme" pill) ------------------------


def test_aims_json_indexes_the_programme(srv):
    status, headers, body = get(srv, "/aims.json")
    assert status == 200 and headers["Content-Type"].startswith("application/json")
    rows = json.loads(body)
    # proposals lead: a `~<grant>` row opens the narrative WITH the aims under it, which is how
    # the programme is read now that it no longer stands as a lane on the board
    assert [r["slug"] for r in rows] == ["~synth-grant", "@adaptive-batching"]
    prop, aim = rows
    assert prop["kind"] == "proposal" and prop["title"] == "Adaptive batching — placeholder application"
    assert prop["sections"] == 2 and prop["bullets"] == 5
    assert aim["kind"] == "aim" and aim["title"] == "Adaptive batch-size control"
    # the two signals the pill shows without opening the card
    assert aim["assumptions"] == 1 and aim["at_risk"] == 1 and aim["slices"] == 11


def test_preview_html_serves_an_aim_card(srv):
    status, headers, body = get(srv, "/preview.html?key=@adaptive-batching")
    assert status == 200 and headers["Content-Type"].startswith("text/html")
    assert b'"order": ["@adaptive-batching"]' in body
    assert b'"aim": true' in body


def test_preview_json_serves_an_aim_card(srv):
    status, _, body = get(srv, "/preview.json?key=@adaptive-batching")
    assert status == 200
    mini = json.loads(body)
    assert mini["papers"]["@adaptive-batching"]["aim"] is True


def test_preview_rejects_an_unknown_aim(srv):
    assert get(srv, "/preview.html?key=@nope")[0] == 404


def test_graph_json_carries_the_programme_lane_but_not_the_paper_sort(srv):
    """Job 2: aims (and the narrative that orders them) now ride in `/graph.json` too, in
    their own lane (viewer/js/18-programme.js) — but `order`, which drives the landing
    column's actual pass/year sort, is built from `g.papers` alone and must stay paper-only
    regardless, exactly as it did before this layer existed."""
    graph = json.loads(get(srv, "/graph.json")[2])
    assert "@adaptive-batching" in graph["papers"]
    assert graph["papers"]["@adaptive-batching"]["aim"] is True
    assert not [k for k in graph["order"] if k.startswith("@")]


def test_the_hud_carries_the_aims_pill(srv):
    body = get(srv, "/")[2]
    assert b'id="aims"' in body and b'id="aimPanel"' in body
    assert b'aims.json' in body


# ── the mirror: read-only mode and the payload cache ──────────────────────────────────────

@pytest.fixture()
def ro_srv(repo):
    """A server in mirror mode — serving a checkout it does not author."""
    s = make_server(repo, repo / "pdfs", read_only=True)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield s
    s.shutdown()
    s.server_close()


def test_read_only_refuses_writes_to_synced_content(ro_srv, repo):
    """A mirror's curated/ is overwritten by the next push, so a write there is a lie — refuse
    it rather than accept it and lose it."""
    before = (repo / "curated" / "Chen2021Sys.yaml").read_text()
    status, _ = post(ro_srv, "/quote_loc", {"citekey": "Chen2021Sys", "slice_id": "c1",
                                            "page": 0, "rects": [[1, 1, 2, 2]]})
    assert status == 405
    assert (repo / "curated" / "Chen2021Sys.yaml").read_text() == before


def test_read_only_still_moves_papers_in_and_out_of_the_reading_list(ro_srv, repo):
    """config.toml is host-local — every sync excludes it — so the mirror's reading list is
    its own and no push can clobber it. Curating from the couch is most of the point."""
    status, body = post(ro_srv, "/active", {"citekey": "Chen2021Sys", "active": True})
    assert status == 200 and body["ok"] and "Chen2021Sys" in body["active"]
    assert "Chen2021Sys" in (repo / "config.toml").read_text()

    status, body = post(ro_srv, "/active", {"citekey": "Chen2021Sys", "active": False})
    assert status == 200 and "Chen2021Sys" not in body["active"]


def test_read_only_still_reads_and_still_resolves_quotes(ro_srv):
    """The point of the mirror is browsing: the graph, the PDFs and quote geometry all work."""
    assert get(ro_srv, "/")[0] == 200
    assert get(ro_srv, "/pdf/Chen2021Sys.pdf")[0] == 200
    status, loc = post(ro_srv, "/resolve", {"citekey": "Chen2021Sys", "quote": "fixture paper"})
    assert status == 200 and loc["page"] == 0


def test_the_payload_is_rebuilt_once_until_a_source_changes(srv, repo, monkeypatch):
    """`lit serve` rebuilds from YAML per request by design; an *unchanged* repo rebuilding is
    pure waste, and on a small always-on host it is a visible pause on every refresh."""
    from litgraph import endpoints
    builds = []
    real = endpoints.payload_dict
    monkeypatch.setattr(endpoints, "payload_dict",
                        lambda *a, **k: (builds.append(1), real(*a, **k))[1])
    assert get(srv, "/")[0] == 200 and len(builds) == 1
    assert get(srv, "/graph.json")[0] == 200 and len(builds) == 1   # served from the cache

    f = repo / "claims" / "batching-adds-latency.yaml"
    f.write_text(f.read_text())                      # touch a *broad* claim, not curated/
    assert get(srv, "/")[0] == 200 and len(builds) == 2

    # a file can appear *older* than everything already there, so the count has to be part of
    # the key — max mtime alone would call this repo unchanged. `.md` full text is the safe
    # lever: quote polishing falls back to the raw anchor, so adding/removing one can't fail
    # validation and muddy what the test is actually measuring.
    md = repo / "pdfs" / "Chen2021Sys.md"
    md.write_text("fixture paper\n")
    os.utime(md, (0, 0))
    assert get(srv, "/")[0] == 200 and len(builds) == 3
    md.unlink()                                      # …and a deletion lowers the max mtime
    assert get(srv, "/")[0] == 200 and len(builds) == 4


# ── the offline copy ─────────────────────────────────────────────────────────────────────────

def test_offline_manifest_lists_the_shell_and_every_pdf(srv, repo):
    """The list the installed app syncs against: relative URLs (so it works under any mount),
    a stat-cheap version per entry, and every one of them actually servable."""
    status, headers, body = get(srv, "/offline.json")
    assert status == 200 and headers["Cache-Control"] == "no-store"
    man = json.loads(body)
    shell = {e["url"]: e for e in man["shell"]}
    for url in ("./", "graph.json", "aims.json", "pdfs.json", "manifest.webmanifest",
                "icon-192.png", "icon-512.png", "apple-touch-icon.png"):
        assert url in shell, url
    st = (repo / "pdfs" / "Chen2021Sys.pdf").stat()
    assert man["pdfs"] == [{"url": "pdf/Chen2021Sys.pdf", "size": st.st_size,
                            "version": f"{st.st_size:x}-{st.st_mtime_ns:x}"}]
    for e in man["shell"] + man["pdfs"]:
        assert not e["url"].startswith("/") and "://" not in e["url"], e
        assert e["version"], e
        status, _, got = get(srv, "/" + e["url"].removeprefix("./"))
        assert status == 200, e["url"]
        if e["size"] is not None:
            assert len(got) == e["size"], e["url"]
    assert get(srv, "/pdf/Chen2021Sys.pdf")[2] == FAKE_PDF


def test_offline_versions_follow_the_files(srv, repo):
    """A rewritten PDF gets a new version, a deleted one leaves the list, and an edit to the
    YAML re-versions the page and the graph — that is all the client compares."""
    def man():
        m = json.loads(get(srv, "/offline.json")[2])
        return {e["url"]: e["version"] for e in m["shell"] + m["pdfs"]}
    before = man()
    assert man() == before                           # stable while nothing changes
    pdf = repo / "pdfs" / "Chen2021Sys.pdf"
    os.utime(pdf, ns=(pdf.stat().st_atime_ns, pdf.stat().st_mtime_ns + 10**9))
    after = man()
    assert after["pdf/Chen2021Sys.pdf"] != before["pdf/Chen2021Sys.pdf"]
    assert after["./"] == before["./"]               # a PDF's bytes are not in the page
    f = repo / "claims" / "batching-adds-latency.yaml"
    f.write_text(f.read_text())
    os.utime(f, ns=(f.stat().st_atime_ns, f.stat().st_mtime_ns + 10**9))
    edited = man()
    assert edited["./"] != after["./"] and edited["graph.json"] != after["graph.json"]
    (repo / "pdfs" / "Second2020Abc.pdf").write_bytes(FAKE_PDF)
    pdf.unlink()
    final = man()
    assert "pdf/Chen2021Sys.pdf" not in final and "pdf/Second2020Abc.pdf" in final
    assert final["pdfs.json"] != edited["pdfs.json"]


def test_service_worker_is_served_from_the_root(srv):
    """Its scope is its own directory, so it has to live at / to cover the app; no-cache so a
    changed worker is noticed on the next open."""
    status, headers, body = get(srv, "/sw.js")
    assert status == 200
    assert headers["Content-Type"].startswith("application/javascript")
    assert headers["Cache-Control"] == "no-cache"
    assert b'addEventListener("fetch"' in body


def test_the_page_carries_the_offline_client(srv):
    """The sync is inlined like every other module and stays inert without a secure context."""
    text = get(srv, "/")[2].decode()
    assert 'fetch("offline.json", {cache: "no-store"})' in text
    assert 'navigator.serviceWorker.register("sw.js")' in text
    assert "window.isSecureContext" in text
    assert ":not(#offline){display:none!important}" in text   # the chip survives the app view
