import os
from pathlib import Path

from litgraph.graph import classify_ref


def test_classify_ref_forms():
    assert classify_ref("c1") == "local"
    assert classify_ref("m12") == "local"
    assert classify_ref("q3") == "local"
    assert classify_ref("West2015Sigmod") == "container"
    assert classify_ref("Chen2021Sys") == "container"
    assert classify_ref("Chen2021Sys:c3") == "sharpened"
    assert classify_ref("throughput-scales-with-batching") == "broad"
    assert classify_ref("buffering-has-costs") == "broad"


def test_classify_ref_borrowed_and_open_prefixes():
    """`b` (borrowed claim) and `oq` (open question) are canonical local ids (SCHEMA §3).

    `oq` is the one that can go wrong: two characters, and a bare kebab-case word is exactly
    what a broad slug looks like, so an alternation testing the single-char class first would
    silently reclassify every open question as a broad node -- a dangling ref at build time."""
    assert classify_ref("b1") == "local"
    assert classify_ref("b12") == "local"
    assert classify_ref("oq1") == "local"
    assert classify_ref("oq10") == "local"
    assert classify_ref("Petridou2021Cell:oq3") == "sharpened"
    assert classify_ref("Petridou2021Cell:b7") == "sharpened"
    # still a slug when it is not prefix+number
    assert classify_ref("open-questions") == "broad"
    assert classify_ref("boundary-stiffness") == "broad"


def test_classify_ref_venueless_citekey():
    """Books and monographs carry no venue segment; they are still containers, not slugs."""
    assert classify_ref("Weaire2000") == "container"
    assert classify_ref("Torquato2001") == "container"
    assert classify_ref("Weaire2000:c1") == "sharpened"
    # the leading capital is the discriminator — a kebab-case slug carrying a year stays broad
    assert classify_ref("jamming-is-not-just-cool-2000") == "broad"


from litgraph.graph import load_repo, Paper, Slice

EXAMPLE = Path(__file__).resolve().parents[3] / "example"


def test_load_repo_reads_curated_and_stubs():
    papers, broad = load_repo(EXAMPLE)
    assert "Chen2021Sys" in papers
    p = papers["Chen2021Sys"]
    assert isinstance(p, Paper)
    assert p.curated is True
    assert p.type == "original" and p.year == 2021 and p.pass_ == 4
    assert ("Chen, Mei", "first", False) in p.authors
    # stubs load as un-sliced containers
    assert papers["Patel2017Vldb"].curated is False
    assert papers["Patel2017Vldb"].slices == []
    # a curated claim parses its edges
    c1 = next(s for s in p.slices if s.id == "c1")
    assert c1.kind == "claim"
    assert "throughput-scales-with-batching" in c1.leads_to
    # broad nodes load
    assert "throughput-scales-with-batching" in broad
    assert broad["throughput-scales-with-batching"].kind == "broad claim"


def test_load_repo_reads_optional_broad_title():
    _, broad = load_repo(EXAMPLE)
    # `title` is the optional at-a-glance name (SCHEMA §4) …
    assert broad["performance-benchmarking"].title == "Performance benchmarking"
    assert broad["performance-benchmarking"].text.startswith("Measurement of a system's")
    # … and a node without one defaults to "" (never None), so the viewer falls back to text
    assert broad["microbenchmark"].title == ""


def test_load_repo_reads_tags():
    papers, _ = load_repo(EXAMPLE)
    assert papers["Chen2021Sys"].tags == ["batching", "throughput", "queueing-model"]
    # a curated paper without a `tags:` key defaults to an empty list (never None)
    assert papers["Kumar2020Net"].tags == []
    # stubs carry no tags (curated-only)
    assert papers["Patel2017Vldb"].tags == []


def test_load_repo_rejects_curated_stub_collision(tmp_path):
    import pytest
    from litgraph.graph import load_repo, BuildError
    (tmp_path / "curated").mkdir()
    (tmp_path / "curated" / "Dup2020Jrnl.yaml").write_text(
        'title: t\ntype: original\nyear: 2020\nauthors: [{name: "A, B"}]\n')
    (tmp_path / "stubs.yaml").write_text("Dup2020Jrnl:\n  title: t\n  year: 2020\n")
    with pytest.raises(BuildError, match="Dup2020Jrnl"):
        load_repo(tmp_path)


from litgraph.graph import method_is_floor


def test_method_floor_vs_model():
    # floor: grounds only in containers (its source papers)
    floor = Slice(id="m2", kind="method", text="microbenchmark",
                  grounded_in=["Bench2016Tools", "Rao2018Osdi"])
    assert method_is_floor(floor) is True
    # floor: no grounding at all still bottoms out
    assert method_is_floor(Slice(id="m1", kind="method", text="x")) is True
    # model: layers on another method (a local m-ref)
    model = Slice(id="m3", kind="method", text="pipeline simulator", grounded_in=["m2", "West2015Sigmod"])
    assert method_is_floor(model) is False


from litgraph.graph import claim_is_borrowed, reaches_floor


def test_claim_borrowed():
    borrowed = Slice(id="c4", kind="claim", text="borrowed", grounded_in=["Patel2017Vldb"])
    assert claim_is_borrowed(borrowed) is True
    original = Slice(id="c1", kind="claim", text="orig", grounded_in=["m1"])
    assert claim_is_borrowed(original) is False
    sharp = Slice(id="c5", kind="claim", text="x", grounded_in=["Chen2021Sys:c3"])
    assert claim_is_borrowed(sharp) is True


def test_reaches_floor():
    m1 = Slice(id="m1", kind="method", text="floor", is_floor=True)
    m3 = Slice(id="m3", kind="method", text="model", grounded_in=["m1"], is_floor=False)
    c1 = Slice(id="c1", kind="claim", text="grounded", grounded_in=["m3"])
    c3 = Slice(id="c3", kind="claim", text="theory", grounded_in=["c1"])
    c9 = Slice(id="c9", kind="claim", text="plausible", grounded_in=["Some2010Paper"])
    by_id = {s.id: s for s in (m1, m3, c1, c3, c9)}
    assert reaches_floor(c1, by_id) is True          # c1 -> m3 -> m1 (floor)
    assert reaches_floor(c3, by_id) is True           # c3 -> c1 -> ... -> floor
    assert reaches_floor(c9, by_id) is False          # grounds only in a citation


from litgraph.graph import answered_question_ids, broad_meter


def _paper(citekey, *slices):
    return Paper(citekey=citekey, curated=True, title="", type="original", year=2023,
                 slices=list(slices))


def test_answered_question_ids():
    p = _paper("P1",
               Slice(id="q1", kind="question", text="?"),
               Slice(id="q2", kind="question", text="?"),
               Slice(id="c1", kind="claim", text="ans", answers=["q1"]))
    assert answered_question_ids({"P1": p}) == {"P1:q1"}


def test_broad_meter_counts_support_and_contradict():
    # c1 generalizes into the broad claim (support); c2 contradicts the slug directly
    p1 = _paper("P1", Slice(id="c1", kind="claim", text="x", leads_to=["b-claim"]))
    p2 = _paper("P2", Slice(id="c2", kind="claim", text="y", contradicts=["b-claim"]))
    s, c = broad_meter("b-claim", {"P1": p1, "P2": p2})
    assert s == 1          # one claim generalizes into it (leads_to)
    assert c == 1          # one claim contradicts the slug directly


import pytest
from litgraph.graph import validate, BuildError, BroadNode


def test_validate_passes_clean_repo():
    p = _paper("P1",
               Slice(id="m1", kind="method", text="f"),
               Slice(id="c1", kind="claim", text="x", grounded_in=["m1"],
                     leads_to=["b-claim"]))
    broad = {"b-claim": BroadNode(slug="b-claim", kind="broad claim", text="b")}
    validate({"P1": p}, broad)   # no raise


def test_validate_flags_dangling_ref():
    p = _paper("P1", Slice(id="c1", kind="claim", text="x", grounded_in=["m9"]))
    with pytest.raises(BuildError, match="m9"):
        validate({"P1": p}, {})


def test_validate_flags_duplicate_local_id():
    p = _paper("P1",
               Slice(id="c1", kind="claim", text="a"),
               Slice(id="c1", kind="claim", text="b"))
    with pytest.raises(BuildError, match="c1"):
        validate({"P1": p}, {})


# ── SCHEMA §6.6 kind coherence ─────────────────────────────────────────────────────────

_B = {"b-claim": BroadNode(slug="b-claim", kind="broad claim", text="b"),
      "b-q": BroadNode(slug="b-q", kind="broad question", text="q"),
      "b-m": BroadNode(slug="b-m", kind="broad method", text="m")}


def test_validate_rejects_cross_paper_leads_to():
    # a cross-paper leads_to would mis-render as a synthesis node (build's _cons)
    other = _paper("Other2020Jrnl", Slice(id="c1", kind="claim", text="y"))
    p = _paper("P1", Slice(id="c1", kind="claim", text="x", leads_to=["Other2020Jrnl"]))
    with pytest.raises(BuildError, match="leads_to"):
        validate({"P1": p, "Other2020Jrnl": other}, _B)
    p2 = _paper("P1", Slice(id="c1", kind="claim", text="x", leads_to=["Other2020Jrnl:c1"]))
    with pytest.raises(BuildError, match="leads_to"):
        validate({"P1": p2, "Other2020Jrnl": other}, _B)


def test_validate_rejects_leads_to_kind_mismatch():
    p = _paper("P1", Slice(id="c1", kind="claim", text="x", leads_to=["b-q"]))
    with pytest.raises(BuildError, match="broad question"):
        validate({"P1": p}, _B)
    m = _paper("P1", Slice(id="m1", kind="method", text="t", leads_to=["b-claim"]))
    with pytest.raises(BuildError, match="broad claim"):
        validate({"P1": m}, _B)


def test_validate_accepts_local_leads_to_generalization():
    # a specific claim laddering up into a broader local claim (same paper, same kind)
    p = _paper("P1",
               Slice(id="c1", kind="claim", text="specific", leads_to=["c3"]),
               Slice(id="c3", kind="claim", text="broader existence claim"))
    validate({"P1": p}, _B)          # no raise


def test_validate_rejects_local_leads_to_kind_mismatch():
    # a claim cannot generalize into a local question
    p = _paper("P1",
               Slice(id="c1", kind="claim", text="x", leads_to=["q1"]),
               Slice(id="q1", kind="question", text="?"))
    with pytest.raises(BuildError, match="question"):
        validate({"P1": p}, _B)


def test_validate_answers_must_target_a_question():
    p = _paper("P1",
               Slice(id="c1", kind="claim", text="x"),
               Slice(id="c2", kind="claim", text="y", answers=["c1"]))
    with pytest.raises(BuildError, match="answers"):
        validate({"P1": p}, _B)
    p2 = _paper("P1", Slice(id="c1", kind="claim", text="x", answers=["b-claim"]))
    with pytest.raises(BuildError, match="not a question"):
        validate({"P1": p2}, _B)
    # a container ref is the un-sliced wildcard — allowed; sharpened :qN is allowed
    stub = _paper("Stub2019Conf")
    stub.curated = False
    ok = _paper("P1", Slice(id="c1", kind="claim", text="x",
                            answers=["Stub2019Conf", "Stub2019Conf:q1"]))
    validate({"P1": ok, "Stub2019Conf": stub}, _B)   # no raise


def test_validate_kind_coherence_resolves_the_target_not_its_id_prefix():
    """Local ids are curator-assigned and have drifted past SCHEMA §3's `^[cqm]\\d+$`: the
    library uses `oq*` for an open question and `b*` for a borrowed claim. Kind coherence
    reads the resolved target's kind, so those cross-paper edges are legal — which is what
    the meta read draws (an open question closes when some paper's claim `answers` it) —
    while a genuine kind mismatch is still caught, now by kind rather than by spelling."""
    src = _paper("P2", Slice(id="c1", kind="claim", text="the answer",
                             answers=["P1:oq1"], contradicts=["P1:b4"]))
    tgt = _paper("P1",
                 Slice(id="oq1", kind="question", text="an open question"),
                 Slice(id="b4", kind="claim", text="a borrowed claim"))
    validate({"P1": tgt, "P2": src}, _B)          # no raise

    # and the mismatch is still an error, reported as a kind and not as a prefix
    bad = _paper("P2", Slice(id="c1", kind="claim", text="x", answers=["P1:b4"]))
    with pytest.raises(BuildError, match="is a claim, not a question"):
        validate({"P1": tgt, "P2": bad}, _B)
    bad2 = _paper("P2", Slice(id="c1", kind="claim", text="x", corroborates=["P1:oq1"]))
    with pytest.raises(BuildError, match="is a question, not a claim"):
        validate({"P1": tgt, "P2": bad2}, _B)


def test_validate_lateral_must_target_a_claim_or_container():
    p = _paper("P1",
               Slice(id="q1", kind="question", text="?"),
               Slice(id="c1", kind="claim", text="x", corroborates=["q1"]))
    with pytest.raises(BuildError, match="corroborates"):
        validate({"P1": p}, _B)
    p2 = _paper("P1", Slice(id="c1", kind="claim", text="x", contradicts=["b-q"]))
    with pytest.raises(BuildError, match="not a claim"):
        validate({"P1": p2}, _B)


def test_validate_floor_only_on_a_claim():
    p = _paper("P1", Slice(id="m1", kind="method", text="t", floor_flag=True))
    with pytest.raises(BuildError, match="floor"):
        validate({"P1": p}, _B)


# ── the broad tier's own leads_to (SCHEMA §4): the claim ladder one rung above the slices ──

def test_load_repo_reads_broad_leads_to(tmp_path):
    (tmp_path / "curated").mkdir()
    (tmp_path / "claims").mkdir()
    (tmp_path / "claims" / "head.yaml").write_text('text: "a head"\nleads_to: [apex]\n')
    (tmp_path / "claims" / "apex.yaml").write_text('text: "an apex"\n')
    _, broad = load_repo(tmp_path)
    assert broad["head"].leads_to == ["apex"]
    assert broad["apex"].leads_to == []              # no `leads_to:` key -> [], never None


def test_validate_broad_ladder_flags_dangling_target():
    broad = {"head": BroadNode(slug="head", kind="broad claim", text="h", leads_to=["nope"])}
    with pytest.raises(BuildError, match="unknown broad slug"):
        validate({}, broad)


def test_validate_broad_ladder_rejects_kind_mismatch():
    # mirrors §6.6 one tier up: a broad claim generalizes into a broad claim, never a question
    broad = {"head": BroadNode(slug="head", kind="broad claim", text="h", leads_to=["b-q"]),
             "b-q": BroadNode(slug="b-q", kind="broad question", text="q")}
    with pytest.raises(BuildError, match="broad question"):
        validate({}, broad)


def test_validate_broad_ladder_rejects_a_cycle_and_names_the_path():
    broad = {"a": BroadNode(slug="a", kind="broad claim", text="a", leads_to=["b"]),
             "b": BroadNode(slug="b", kind="broad claim", text="b", leads_to=["a"])}
    with pytest.raises(BuildError, match="a -> b -> a"):
        validate({}, broad)


def test_validate_broad_ladder_rejects_a_self_cycle():
    broad = {"a": BroadNode(slug="a", kind="broad claim", text="a", leads_to=["a"])}
    with pytest.raises(BuildError, match="cycle"):
        validate({}, broad)


def test_validate_broad_ladder_accepts_a_multi_parented_dag():
    # a broad claim may ladder into two heads at once -- a DAG, not a cycle, and must pass clean
    broad = {
        "child": BroadNode(slug="child", kind="broad claim", text="c",
                           leads_to=["head1", "head2"]),
        "head1": BroadNode(slug="head1", kind="broad claim", text="h1", leads_to=["apex"]),
        "head2": BroadNode(slug="head2", kind="broad claim", text="h2", leads_to=["apex"]),
        "apex": BroadNode(slug="apex", kind="broad claim", text="a"),
    }
    validate({}, broad)          # no raise


from litgraph.graph import build_graph, Graph


def test_build_graph_example():
    g = build_graph(EXAMPLE)
    assert isinstance(g, Graph)
    p = g.papers["Chen2021Sys"]
    by_id = {s.id: s for s in p.slices}
    # m1 is a floor (grounds only in a container)
    assert by_id["m1"].is_floor is True and by_id["m1"].color == "floor"
    # c1 grounds in m1 -> grounded + original
    assert by_id["c1"].grounded is True and by_id["c1"].borrowed is False
    assert by_id["c1"].color == "grounded"
    # b1 grounds in a citation -> borrowed; the prefix agrees, but is not what computes it
    assert by_id["b1"].borrowed is True and by_id["b1"].color == "borrowed"
    # q1 answered (b1 answers it), oq1 open
    assert by_id["q1"].answered is True
    assert by_id["oq1"].answered is False
    # top-altitude claims become the head (no outgoing leads_to) -- c3 has only contradicts
    assert p.head  # non-empty
    # broad-claim meter (example: 2 support via Chen c1 + Kumar c1 leads_to, 1 contradict via Chen c3)
    b = g.broad["throughput-scales-with-batching"]
    assert (b.support, b.contradict) == (2, 1)
    # landing order: curated before stubs
    assert g.order[0] == "Chen2021Sys"
    assert g.order.index("Chen2021Sys") < g.order.index("Patel2017Vldb")


def test_build_graph_handles_skeleton_paper(tmp_path):
    # a curated paper with no slices and no `pass` is valid and sorts after passed papers
    (tmp_path / "curated").mkdir()
    (tmp_path / "curated" / "Bare2020Jrnl.yaml").write_text(
        'title: "x"\ntype: original\nyear: 2020\nauthors: [{name: "A, B"}]\n')
    (tmp_path / "stubs.yaml").write_text("Old1990Jrnl:\n  title: t\n  year: 1990\n")
    g = build_graph(tmp_path)
    assert g.papers["Bare2020Jrnl"].slices == []
    assert g.order == ["Bare2020Jrnl", "Old1990Jrnl"]  # curated before stub


from litgraph.graph import _slice_color


def test_slice_color_all_branches():
    assert _slice_color(Slice(id="q1", kind="question", text="?")) == "question"
    assert _slice_color(Slice(id="m1", kind="method", text="f", is_floor=True)) == "floor"
    assert _slice_color(Slice(id="m2", kind="method", text="m", is_floor=False)) == "model"
    assert _slice_color(Slice(id="c1", kind="claim", text="b", borrowed=True)) == "borrowed"
    assert _slice_color(Slice(id="c2", kind="claim", text="g", grounded=True)) == "grounded"
    assert _slice_color(Slice(id="c3", kind="claim", text="p")) == "plausible"


def test_order_ranks_curated_by_pass(tmp_path):
    (tmp_path / "curated").mkdir()
    (tmp_path / "curated" / "Deep2021Jrnl.yaml").write_text(
        'title: t\ntype: original\nyear: 2021\npass: 3\nauthors: [{name: "A, B"}]\n')
    (tmp_path / "curated" / "Shallow2022Jrnl.yaml").write_text(
        'title: t\ntype: original\nyear: 2022\nauthors: [{name: "A, B"}]\n')  # no pass
    g = build_graph(tmp_path)
    # pass 3 ranks above no-pass even though Shallow is newer
    assert g.order == ["Deep2021Jrnl", "Shallow2022Jrnl"]


def test_stub_loads_authors_and_journal(tmp_path):
    from litgraph.graph import load_repo
    (tmp_path / "stubs.yaml").write_text(
        "Schwarz2015BBA:\n"
        "  title: Traction force microscopy\n"
        "  authors: [Ulrich S. Schwarz, Jérôme R. D. Soiné]\n"
        "  journal: Biochim. Biophys. Acta\n"
        "  year: 2015\n"
        "  doi: 10.1/bba\n")
    papers, _ = load_repo(tmp_path)
    s = papers["Schwarz2015BBA"]
    assert s.curated is False
    assert s.journal == "Biochim. Biophys. Acta"
    # stub authors carry as (name, "", False) — byline names, no position/corresponding
    assert s.authors == [("Ulrich S. Schwarz", "", False), ("Jérôme R. D. Soiné", "", False)]


# --- the per-file parse cache (graph._YAML_CACHE) -------------------------------------


def test_load_yaml_reuses_the_parse_until_the_file_changes(tmp_path):
    """`load_yaml` memoizes on (mtime_ns, size), so an unchanged file is parsed once.

    This is what keeps a `lit serve` rebuild from re-parsing all 274 files because one of
    them moved -- or because something that is not YAML at all moved. Toggling a paper on
    the reading list writes config.toml, which `serve._source_version` watches, so before
    the cache a rebuild that touched no YAML whatsoever still paid for every file."""
    from litgraph import graph

    f = tmp_path / "one.yaml"
    f.write_text("title: first\n")
    graph._YAML_CACHE.pop(f, None)

    first = graph.load_yaml(f)
    assert first == {"title": "first"}
    assert graph.load_yaml(f) is first          # the hit is the same object, not a re-parse

    # a real edit invalidates: same path, new fingerprint
    os.utime(f, ns=(0, 0))                      # pin an mtime the rewrite is sure to beat
    f.write_text("title: second\n")
    assert graph.load_yaml(f) == {"title": "second"}
    # one entry per path, REPLACED on change -- the cache is bounded by the size of the repo,
    # not by the number of edits made to it (the module-level dict is shared across tests, so
    # count only this file's entries)
    assert [k for k in graph._YAML_CACHE if k == f] == [f]


def test_load_yaml_cache_is_not_poisoned_by_a_slice_edit(tmp_path):
    """The cache hands back a SHARED mapping, so every consumer must copy what it retains.

    `quote_loc` is the one field that used to be held by reference; writing through a
    built Slice must not reach the parsed document behind it."""
    from litgraph import graph

    f = tmp_path / "Key2020Journal.yaml"
    f.write_text(
        "title: a paper\n"
        "claims:\n"
        "  - id: c1\n"
        "    text: something\n"
        "    quote: a quote\n"
        "    quote_loc: {page: 2, rects: [[0.1, 0.1, 0.2, 0.2]]}\n"
    )
    graph._YAML_CACHE.pop(f, None)

    paper = graph.paper_from_raw("Key2020Journal", graph.load_yaml(f))
    paper.slices[0].quote_loc["page"] = 99
    paper.slices[0].quote_loc["rects"][0][0] = 9.9

    again = graph.paper_from_raw("Key2020Journal", graph.load_yaml(f))
    assert again.slices[0].quote_loc == {"page": 2, "rects": [[0.1, 0.1, 0.2, 0.2]]}
