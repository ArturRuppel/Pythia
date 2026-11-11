# tests/test_eln_plugin.py
"""The labbook's `/litgraph/` adapter — the second server, which had no tests at all.

That gap is why its payload builder drifted a version behind `lit serve`'s without anything
noticing. These run the real Flask routes over the example library, so the two servers can
be compared directly rather than by reading both and hoping.
"""
import json
from pathlib import Path

import pytest

flask = pytest.importorskip("flask", reason="the labbook adapter needs Flask")
pytest.importorskip("eln", reason="the plugin imports the labbook's Plugin dataclass")

from litgraph import endpoints  # noqa: E402
from litgraph_eln import register_litgraph_routes  # noqa: E402

EXAMPLE = Path(__file__).resolve().parents[3] / "example"


@pytest.fixture()
def client(monkeypatch):
    """A Flask app carrying only the litgraph blueprint, pointed at the example library."""
    monkeypatch.setenv("LITGRAPH_ROOT", str(EXAMPLE))
    app = flask.Flask(__name__)
    register_litgraph_routes(app, root=None)
    app.config.update(TESTING=True)
    return app.test_client()


def test_graph_json_matches_the_shared_builder(client):
    """The route must serve exactly what `endpoints.payload_dict` produces — this is the
    equality the old hand-copied `_payload_dict` silently broke."""
    r = client.get("/litgraph/graph.json")
    assert r.status_code == 200
    served = json.loads(r.data)
    direct = endpoints.payload_dict(EXAMPLE, EXAMPLE / "pdfs")
    assert served == direct


def test_read_only_mount_carries_no_serve_only_keys(client):
    """The labbook never answers /views/, so the viewer it serves must not advertise it."""
    payload = json.loads(client.get("/litgraph/graph.json").data)
    assert "views" not in payload
    assert "active" not in payload             # the reading list is retired (the desk replaced it)


def test_index_serves_the_viewer_page(client):
    r = client.get("/litgraph/")
    assert r.status_code == 200
    assert r.mimetype == "text/html"
    body = r.data.decode()
    assert "/*__GRAPH_JSON__*/" not in body   # the slot was filled, not shipped empty
    assert "const GRAPH =" in body            # …by the real payload
    assert "Chen2021Sys" in body              # …carrying the example library
    assert body.count("<script") == 1         # still one self-contained page


def test_pdfs_manifest_is_json_even_with_no_pdfs(client):
    """No PDF directory is a normal state for a fresh library, not an error."""
    r = client.get("/litgraph/pdfs.json")
    assert r.status_code == 200
    assert isinstance(json.loads(r.data), list)


@pytest.mark.parametrize("url", [
    "/litgraph/page/NoSuchKey/1.png",
    "/litgraph/pages/NoSuchKey.json",
    "/litgraph/words/NoSuchKey/1.json",
    "/litgraph/search/NoSuchKey.json",
    "/litgraph/pdf/NoSuchKey.pdf",
    "/litgraph/preview/NoSuchKey.png",
])
def test_missing_pdf_is_a_404_not_a_stack_trace(client, url):
    """Every PDF route shares one guard now; each must still answer 404 rather than 500."""
    r = client.get(url)
    assert r.status_code == 404


@pytest.mark.parametrize("bad", ["../etc/passwd", "a/b", "Key%2Fx"])
def test_citekey_pattern_stops_traversal(client, bad):
    """The citekey regex is what keeps /pdf/ from walking out of pdf_dir."""
    r = client.get(f"/litgraph/pdf/{bad}")
    assert r.status_code in (404, 308, 400)
    assert b"root:" not in r.data


def test_preview_html_404s_for_an_uncurated_key(client):
    assert client.get("/litgraph/preview.html?key=NotAPaper").status_code == 404


def test_preview_html_isolates_one_curated_paper(client):
    r = client.get("/litgraph/preview.html?key=Chen2021Sys")
    assert r.status_code == 200 and r.mimetype == "text/html"


def test_quote_loc_rejects_a_malformed_payload(client):
    """A bad write payload must be refused before it reaches the YAML."""
    r = client.post("/litgraph/quote_loc", json={"citekey": "Chen2021Sys", "slice_id": "nope",
                                                 "page": "one", "rects": "no"})
    assert r.status_code == 400


def test_resolve_returns_null_for_an_unknown_paper(client):
    r = client.post("/litgraph/resolve", json={"citekey": "NoSuchKey", "quote": "x"})
    assert r.status_code == 200 and json.loads(r.data) is None
