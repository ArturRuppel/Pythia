# tests/test_build.py
import json
from pathlib import Path
from litgraph.graph import build_graph, Paper, Slice
from litgraph.build import to_json_dict, emit, _cons, _gen

EXAMPLE = Path(__file__).resolve().parents[3] / "example"


def test_to_json_dict_shape():
    d = to_json_dict(build_graph(EXAMPLE))
    # no "active": the reading list is retired; the desk is derived from pass + validated below
    assert set(d) == {"papers", "broad", "stubs", "order", "topics", "collections"}
    # curated paper carries computed slices + edge lists
    p = d["papers"]["Chen2021Sys"]
    assert p["cur"] is True and p["pass"] == 4
    assert p["validated"] is None      # never validated → the viewer shows it as new, on the desk
    assert p["authors"][0] == ["Chen, Mei", "first", False]
    assert p["tags"] == ["batching", "throughput", "queueing-model"]   # tags ride into the JSON
    assert d["papers"]["Kumar2020Net"]["tags"] == []                   # no tags → empty list
    assert p["abs"].startswith("Stream processors trade latency for throughput")
    c1 = next(s for s in p["slices"] if s["id"] == "c1")
    assert c1["color"] == "grounded" and c1["kind"] == "claim"
    # each slice carries its within-paper support refs (local grounded_in only)
    assert c1["up"] == ["m1"]          # c1 builds on the floor m1 (substructure)
    m1 = next(s for s in p["slices"] if s["id"] == "m1")
    assert m1["up"] == []              # the floor builds on nothing local (grounds in a citation)
    assert all(ref.startswith(("c", "b", "q", "oq", "m")) and ":" not in ref
               for s in p["slices"] for ref in s["up"])   # local refs only (SCHEMA §3)
    # the weld (exact quote) and answers edges ride along for the viewer's drill-down
    assert c1["quote"].startswith("throughput increased monotonically")
    b1 = next(s for s in p["slices"] if s["id"] == "b1")
    assert b1["answers"] == ["q1"]
    m1_q = next(s for s in p["slices"] if s["id"] == "m1")["quote"]
    assert m1_q is None                                   # methods' quotes are optional
    assert any(g["via"] == "m1" for g in p["grounds"])          # grounds -> left
    # container (unsharpened) grounds carry tid=None — the wildcard "some slice in here";
    # a sharpened ground keeps its target slice (Chen m2 extends Lopez2019Arch:m2)
    assert {"key": "Lopez2019Arch", "tid": "m2", "via": "m2"} in p["grounds"]
    assert all(g["tid"] is None for g in p["grounds"] if g["key"] != "Lopez2019Arch")
    assert any(co["slug"] == "throughput-scales-with-batching" for co in p["cons"])
    assert any(l["sign"] in ("corr", "contra") for l in p["lateral"])
    # a lateral ref to a broad slug routes to the synthesis band ({slug}), not a paper ({key})
    broad_lat = [l for l in p["lateral"] if "slug" in l]
    assert broad_lat == [{"slug": "throughput-scales-with-batching",
                          "sign": "contra", "via": "c3"}]
    assert all("key" not in l for l in broad_lat)
    # sharpened lateral refs keep the specific target slice (Kumar -> Chen2021Sys:c1/:c2)
    k = d["papers"]["Kumar2020Net"]
    assert {"key": "Chen2021Sys", "tid": "c1", "sign": "corr", "via": "c1"} in k["lateral"]
    assert {"key": "Chen2021Sys", "tid": "c2", "sign": "contra", "via": "c2"} in k["lateral"]
    # cross-paper answers edges are emitted separately (local ones nest via slice "answers")
    assert k["ans"] == [{"key": "Lopez2019Arch", "tid": "q1", "via": "c2"}]
    assert p["ans"] == []                                 # Chen's b1->q1 answer is local
    # inverted grounds: Lopez's builds-on lists Chen (m2 grounds in Lopez2019Arch:m2)
    lo = d["papers"]["Lopez2019Arch"]
    assert lo["builds"] == [{"key": "Chen2021Sys", "tid": "m2", "via": "m2"}]
    # the local generalization ladder rides along per slice: c2/c3 ladder into c1
    # (leads_to → local), while a broad-slug leads_to stays out of `gen` (it's a cons)
    assert next(s for s in lo["slices"] if s["id"] == "c2")["gen"] == ["c1"]
    assert next(s for s in lo["slices"] if s["id"] == "c3")["gen"] == ["c1"]
    assert next(s for s in lo["slices"] if s["id"] == "c1")["gen"] == []
    assert p["builds"] == []                              # nothing grounds in Chen (yet)
    # the cross-paper answer flips Lopez q1 to answered (emergent, SCHEMA §7)
    assert next(s for s in lo["slices"] if s["id"] == "q1")["answered"] is True
    # stubs are separated out (one-line cards), not under papers' slices
    assert "Patel2017Vldb" in d["stubs"]
    assert d["stubs"]["Patel2017Vldb"]["year"] == 2017
    # broad claim carries its meter
    assert "meter" in d["broad"]["throughput-scales-with-batching"]
    # a broad node's optional at-a-glance title reaches the viewer ("" when unset)
    assert d["broad"]["performance-benchmarking"]["title"] == "Performance benchmarking"
    assert d["broad"]["microbenchmark"]["title"] == ""
    # order is papers (curated + stubs), curated first
    assert d["order"][0] == "Chen2021Sys"


def test_static_build_carries_pass_and_validated_for_every_paper(tmp_path):
    """`lit build` lists the desk too: every curated paper ships both numbers, so the offline /
    static viewer can derive it. Only `lit serve` can write `validated`."""
    import shutil
    from litgraph.store import set_validated
    root = tmp_path / "lib"
    shutil.copytree(EXAMPLE, root)
    set_validated(root, "Kumar2020Net", 1)
    emit(build_graph(root), tmp_path / "dist")
    papers = json.loads((tmp_path / "dist" / "graph.json").read_text())["papers"]
    for k, p in papers.items():
        if p.get("aim") or p.get("narr"):
            continue
        assert "pass" in p and "validated" in p, k
    assert papers["Kumar2020Net"]["validated"] == 1 and papers["Kumar2020Net"]["pass"] == 3


# --- the topic axis (SCHEMA §9): emitted as a saved search, never a graph node --------------

def test_topics_emit_carries_derived_closure_and_membership():
    """The viewer must never re-walk `broader` itself (design doc §4/§6): each topic's
    `keywords` is already the full closure, and `papers` is already reduced to the curated
    citekeys it reaches — both computed in Python from the same helpers topics.py tests
    against (keyword_closure / papers_in), not re-derived here."""
    d = to_json_dict(build_graph(EXAMPLE))
    t = d["topics"]
    assert set(t) == {"performance", "throughput", "modelling"}
    # performance is the tier-1 heading: no keywords of its own, but its closure rolls up
    # everything the two containers beneath it own (the shared "batching" keyword included)
    assert t["performance"]["root"] is True
    assert t["performance"]["broader"] == []
    assert t["performance"]["keywords"] == ["batching", "queueing-model", "throughput"]
    # the leaves are not roots, and carry their own (smaller) closure
    assert t["throughput"]["root"] is False and t["throughput"]["broader"] == ["performance"]
    assert t["throughput"]["keywords"] == ["batching", "throughput"]
    # membership is paper citekeys, curated-only, reached transitively through `broader`
    assert t["performance"]["papers"] == ["Chen2021Sys"]
    assert t["throughput"]["papers"] == ["Chen2021Sys"]
    assert t["performance"]["title"] == "Systems performance"


def test_topics_emit_is_empty_dict_when_repo_has_no_topics_tree(tmp_path):
    """A repo with no topics/ directory must render exactly as it did before this axis
    existed — an absent tree is `{}`, not a missing key or an error."""
    (tmp_path / "curated").mkdir()
    d = to_json_dict(build_graph(tmp_path))
    assert d["topics"] == {}


def test_cons_skips_local_generalization():
    # a local leads_to is a same-paper ladder (nests in place); only broad slugs are
    # right-band synthesis nodes, so a phantom "c3" node must not be emitted.
    p = Paper(citekey="P1", curated=True, title="", type="original", year=2023,
              slices=[Slice(id="c1", kind="claim", text="x", leads_to=["c3", "b-claim"]),
                      Slice(id="c3", kind="claim", text="broader")])
    cons = _cons(p)
    assert {"slug": "b-claim", "via": "c1"} in cons
    assert all(co["slug"] != "c3" for co in cons)


def test_gen_lists_local_leads_to_only():
    # the ladder is the local leads_to refs; a broad slug generalizes rightward (_cons)
    s = Slice(id="c1", kind="claim", text="x", leads_to=["c3", "b-claim"])
    assert _gen(s) == ["c3"]
    assert _gen(Slice(id="c3", kind="claim", text="broader")) == []


def test_emit_writes_self_contained_viewer(tmp_path):
    g = build_graph(EXAMPLE)
    emit(g, tmp_path)
    gj = tmp_path / "graph.json"
    html = tmp_path / "index.html"
    assert gj.exists() and html.exists()
    # graph.json round-trips
    data = json.loads(gj.read_text())
    assert "Chen2021Sys" in data["papers"]
    # index.html has the JSON inlined (self-contained) and no leftover token
    text = html.read_text()
    assert "Chen2021Sys" in text
    assert "__GRAPH_JSON__" not in text
    assert 'rel="manifest"' in text
    assert all((tmp_path / name).is_file() for name in (
        "manifest.webmanifest", "icon-192.png", "icon-512.png", "apple-touch-icon.png"))


from litgraph.graph import BroadNode, Graph, Paper, Slice
from litgraph.build import _answers, _builds


def test_broad_payload_carries_leads_to():
    """The broad tier's own `leads_to` (SCHEMA §4) rides into the payload so the viewer can
    lay the synthesis band out as a ladder instead of one flat column."""
    head = BroadNode(slug="head", kind="broad claim", text="h", leads_to=["apex"])
    apex = BroadNode(slug="apex", kind="broad claim", text="a")
    d = to_json_dict(Graph(papers={}, broad={"head": head, "apex": apex}, order=[]))
    assert d["broad"]["head"]["leads_to"] == ["apex"]
    assert d["broad"]["apex"]["leads_to"] == []


def _paper(citekey, *slices, curated=True):
    return Paper(citekey=citekey, curated=curated, title="", type="original",
                 year=2023, slices=list(slices))


def test_answers_emits_cross_paper_forms_only():
    p = _paper("P1",
               Slice(id="q1", kind="question", text="?"),
               Slice(id="c1", kind="claim", text="x",
                     answers=["q1", "Other2020Jrnl:q2", "Stub2019Conf", "broad-q"]))
    out = _answers(p)
    # local q1 nests in place; sharpened keeps tid; container is the wildcard (tid=None);
    # a broad question slug routes to the synthesis band
    assert out == [{"key": "Other2020Jrnl", "tid": "q2", "via": "c1"},
                   {"key": "Stub2019Conf", "tid": None, "via": "c1"},
                   {"slug": "broad-q", "via": "c1"}]


def test_builds_inverts_grounds_between_curated_papers_only():
    old = _paper("Old2019Jrnl", Slice(id="m1", kind="method", text="f"))
    new = _paper("New2021Jrnl",
                 Slice(id="m1", kind="method", text="g",
                       grounded_in=["Old2019Jrnl:m1", "Stub2016Conf"]),
                 Slice(id="c1", kind="claim", text="x", grounded_in=["Old2019Jrnl"]))
    stub = _paper("Stub2016Conf", curated=False)
    g = Graph(papers={"Old2019Jrnl": old, "New2021Jrnl": new, "Stub2016Conf": stub},
              broad={}, order=[])
    idx = _builds(g)
    # both the sharpened and the container ground invert onto the curated source;
    # the stub target gets no builds entry (stubs cannot be focused)
    assert idx == {"Old2019Jrnl": [
        {"key": "New2021Jrnl", "tid": "m1", "via": "m1"},
        {"key": "New2021Jrnl", "tid": None, "via": "c1"}]}


from litgraph.cli import main


def test_cli_build_writes_dist(tmp_path, capsys):
    rc = main(["build", "--root", str(EXAMPLE), "--out", str(tmp_path / "dist")])
    assert rc == 0
    assert (tmp_path / "dist" / "index.html").exists()
    out = capsys.readouterr().out
    assert "dist" in out  # reports where it wrote


def test_cli_build_reports_validation_error(tmp_path, capsys):
    (tmp_path / "curated").mkdir()
    (tmp_path / "curated" / "Bad2020Jrnl.yaml").write_text(
        'title: t\ntype: original\nyear: 2020\nauthors: [{name: "A, B"}]\n'
        'claims:\n  - {id: c1, text: x, grounded_in: [m9]}\n')
    rc = main(["build", "--root", str(tmp_path), "--out", str(tmp_path / "dist")])
    assert rc == 1
    err = capsys.readouterr().err
    assert "m9" in err


def test_emit_escapes_script_close_in_inlined_json(tmp_path):
    # a paper whose text contains "</script>" must not break the self-contained page
    (tmp_path / "curated").mkdir()
    (tmp_path / "curated" / "Evil2020Jrnl.yaml").write_text(
        'title: "danger </script><b>x</b>"\ntype: original\nyear: 2020\n'
        'authors: [{name: "A, B"}]\n')
    out = tmp_path / "dist"
    emit(build_graph(tmp_path), out)
    html = (out / "index.html").read_text()
    # the only literal </script> is the real closing tag (data occurrence is escaped)
    assert html.count("</script>") == 1
    assert "\\u003c/script>" in html
    # graph.json keeps the raw (unescaped) value and round-trips
    data = json.loads((out / "graph.json").read_text())
    assert data["papers"]["Evil2020Jrnl"]["title"] == "danger </script><b>x</b>"


def test_stub_payload_carries_authors_and_journal():
    stub = Paper(citekey="Schwarz2015BBA", curated=False, title="TFM", type="original",
                 year=2015, doi="10.1/bba", journal="Biochim. Biophys. Acta",
                 authors=[("Ulrich S. Schwarz", "", False), ("Jérôme R. D. Soiné", "", False)])
    g = Graph(papers={"Schwarz2015BBA": stub}, broad={}, order=["Schwarz2015BBA"])
    d = to_json_dict(g)
    s = d["stubs"]["Schwarz2015BBA"]
    assert s["journal"] == "Biochim. Biophys. Acta"
    assert s["authors"] == [["Ulrich S. Schwarz", "", False], ["Jérôme R. D. Soiné", "", False]]


def test_yaml_error_names_the_file(tmp_path):
    """A malformed YAML anywhere in the repo must say WHICH file.

    ruamel is handed text, not a path, so its own message is `in "<unicode string>",
    line N` — a line number with no filename, across a repo of a hundred files."""
    from litgraph.graph import BuildError, load_yaml
    import pytest

    bad = tmp_path / "Broken2026Journal.yaml"
    # a sharpened cross-paper ref left unquoted in a flow sequence: the round-trip parser
    # store.py writes with accepts this, the safe parser the graph loads with does not
    bad.write_text('title: x\nclaims:\n  - id: c1\n    corroborates: [Other2026Journal:c4]\n')
    with pytest.raises(BuildError) as e:
        load_yaml(bad)
    assert "Broken2026Journal.yaml" in str(e.value)


def test_quoting_a_sharpened_ref_makes_it_load():
    """…and the fix the message implies actually works."""
    from litgraph.graph import load_yaml
    import tempfile, pathlib

    with tempfile.TemporaryDirectory() as d:
        f = pathlib.Path(d) / "Ok2026Journal.yaml"
        f.write_text('claims:\n  - id: c1\n    corroborates: ["Other2026Journal:c4"]\n')
        assert load_yaml(f)["claims"][0]["corroborates"] == ["Other2026Journal:c4"]


def test_yaml_error_names_the_offending_ref_and_line(tmp_path):
    """The generic ruamel message ("could not find expected ':'") points at the wrong token
    and gives no fix. When the parse failure matches this specific trap, the error should
    name the exact ref and line instead, and spell out the fix inline."""
    from litgraph.graph import BuildError, load_yaml
    import pytest

    bad = tmp_path / "Bi2014SoftMatter.yaml"
    # pad with filler lines so the offending line number is unambiguous and not line 1
    bad.write_text(
        'title: "x"\n'
        "type: original\n"
        "claims:\n"
        '  - id: c1\n'
        '    text: "t"\n'
        "    corroborates: [Key2026Journal:c4]\n"
    )
    with pytest.raises(BuildError) as e:
        load_yaml(bad)
    msg = str(e.value)
    assert "Bi2014SoftMatter.yaml" in msg
    assert "line 6" in msg
    assert 'unquoted cross-paper ref in a flow sequence' in msg
    assert 'write ["Key2026Journal:c4"], not [Key2026Journal:c4]' in msg


def test_yaml_error_hint_reports_every_offending_line():
    """More than one unquoted ref in the same broken file → every line gets named, not just
    the first (ruamel aborts at the first syntax error, but our scan reads the whole text)."""
    from litgraph.graph import load_yaml
    import tempfile, pathlib, pytest
    from litgraph.graph import BuildError

    with tempfile.TemporaryDirectory() as d:
        f = pathlib.Path(d) / "Two2020Traps.yaml"
        f.write_text(
            "claims:\n"
            "  - id: c1\n"
            "    corroborates: [Key2026Journal:c4]\n"
            "  - id: c2\n"
            "    contradicts: [Other2019Nat:c9]\n"
        )
        with pytest.raises(BuildError) as e:
            load_yaml(f)
        msg = str(e.value)
        assert "line 3" in msg and "Key2026Journal:c4" in msg
        assert "line 5" in msg and "Other2019Nat:c9" in msg


def test_yaml_error_falls_back_to_ruamel_message_for_unrelated_syntax():
    """A parse error that ISN'T the unquoted-sharpened-ref trap still gets a file-named
    BuildError (the original bug this function fixed), just without the extra hint."""
    from litgraph.graph import BuildError, load_yaml
    import tempfile, pathlib, pytest

    with tempfile.TemporaryDirectory() as d:
        f = pathlib.Path(d) / "Malformed2020X.yaml"
        f.write_text("title: [unclosed\n")
        with pytest.raises(BuildError) as e:
            load_yaml(f)
        assert "Malformed2020X.yaml" in str(e.value)
        assert "unquoted cross-paper ref" not in str(e.value)
