# tests/test_viewer_modules.py
"""The viewer ships as one self-contained file assembled from viewer/css/ + viewer/js/.

The split is a source split only: `lit build`'s output must stay a single page with no
external requests, because it opens from file:// and from a phone with no network. These
tests guard the seam between the modules and that one-file contract.
"""
import re

import pytest

from litgraph.build import _CSS_MARK, _JS_MARK, _VIEWER, template_html
from litgraph.graph import BuildError


def test_every_module_is_reachable_and_non_empty():
    """A module that exists but is never inlined is a silent behaviour loss — the viewer
    would simply lack a feature, with nothing failing."""
    page = template_html()
    css = sorted((_VIEWER / "css").glob("*.css"))
    js = sorted((_VIEWER / "js").glob("*.js"))
    assert css and js, "the split produced no modules"
    for f in css + js:
        body = f.read_text(encoding="utf-8")[:-1]   # drop the stored trailing newline
        assert body.strip(), f"{f.name} is empty"
        assert body in page, f"{f.name} is not inlined into the built page"


def test_modules_are_inlined_in_filename_order():
    """The numeric prefixes ARE the load order: the viewer is one script in one scope, so a
    module reading another's const at parse time must come after it."""
    page = template_html()
    for subdir, ext in (("css", "*.css"), ("js", "*.js")):
        files = sorted((_VIEWER / subdir).glob(ext))
        positions = [page.index(f.read_text(encoding="utf-8")[:-1]) for f in files]
        assert positions == sorted(positions), f"viewer/{subdir}/ is inlined out of order"


def test_page_is_self_contained():
    """No external stylesheet, script or font: the artifact has to work offline."""
    page = template_html()
    assert _CSS_MARK not in page and _JS_MARK not in page, "a marker survived assembly"
    assert len(re.findall(r"<script\b", page)) == 1, "the page grew a second <script>"
    assert len(re.findall(r"<style\b", page)) == 1, "the page grew a second <style>"
    assert not re.search(r'<script[^>]+\bsrc=', page), "the page loads an external script"
    assert not re.search(r'<link[^>]+\bstylesheet', page), "the page loads an external stylesheet"


def test_family_sheet_is_inlined_ahead_of_the_viewer_css():
    """css/00-theme.css maps its names onto the family sheet's --hm-* tokens, so the sheet has
    to be in the page, and in front, so the viewer's own rules still win."""
    page = template_html()
    assert "/*@LITGRAPH_FAMILY_CSS@*/" not in page, "the family marker survived assembly"
    family = (_VIEWER / "harmonia" / "harmonia.css").read_text(encoding="utf-8")
    first = sorted((_VIEWER / "css").glob("*.css"))[0].read_text(encoding="utf-8")[:-1]
    assert family in page, "the family sheet is not inlined"
    assert page.index(family) < page.index(first), "the family sheet must precede the viewer's CSS"


def test_graph_slot_survives_the_split():
    """render_html swaps this token region for the payload; losing it breaks every build."""
    page = template_html()
    assert page.count("/*__GRAPH_JSON__*/") == 1
    assert page.count("/*__END__*/") == 1
    assert page.index("/*__GRAPH_JSON__*/") < page.index("/*__END__*/")


def test_search_indexes_papers_on_the_reading_list():
    """The reading list changes landing placement, not discoverability.

    Active papers are absent from the initial board and `gotoPaper` knows how to mint their
    cards on demand. Filtering them out while building the search index makes that path
    unreachable by title, author, or citekey.
    """
    search = (_VIEWER / "js" / "14-search.js").read_text(encoding="utf-8")
    index_body = search.split("function buildSearchIndex(){", 1)[1].split(
        "function openResults(){", 1
    )[0]
    assert "ACTIVE.has(key)" not in index_body
    assert "rows.push({key" in index_body


def test_missing_modules_fail_loudly(tmp_path, monkeypatch):
    """An incomplete install must not emit a viewer with no styles — silently shipping a
    blank page is worse than not building."""
    import litgraph.build as build

    monkeypatch.setattr(build, "_VIEWER", tmp_path)
    (tmp_path / "css").mkdir()
    (tmp_path / "shell.html").write_text(_CSS_MARK, encoding="utf-8")
    with pytest.raises(BuildError, match="no modules"):
        build.template_html()
