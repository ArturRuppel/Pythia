"""`lit map`: the broad layer and what hangs on it, read back from the loaded graph.

Offline and deterministic — the worked `example/` library plus an inline synthetic repo. The
invariant these tests defend is the one definition everything rests on: a paper slice is on
the map iff it reaches a broad node by `leads_to` (through any same-paper ladder) or, for a
claim, by `answers` naming a broad question. Every count, the reverse lookup and the off-map
report must agree with it.
"""

import json
from pathlib import Path

import pytest

from litgraph import broadmap as bm
from litgraph.cli import main
from litgraph.graph import build_graph

EXAMPLE = Path(__file__).resolve().parents[3] / "example"


def _run(capsys, *args) -> tuple[int, str]:
    rc = main(["map", *args])
    return rc, capsys.readouterr().out


def _json(capsys, *args):
    rc, out = _run(capsys, *args, "--json")
    assert rc == 0
    return json.loads(out)


# --- the synthetic repo ------------------------------------------------------
#
#   top ──┬── mid-a ──┐
#         └── mid-b ──┴── leaf        (leaf has two parents: a DAG, not a tree)
#   broad question bq, broad methods meth-top <- meth-leaf
#
#   Alpha2020Synth  c1 -> leaf; c2 -> c1 (same-paper ladder: c2 is on the map via c1);
#                   c3 off the map, answers q1; q1 -> bq; m1 -> meth-leaf
#   Beta2021Synth   c1 -> mid-a, contradicts Alpha2020Synth:c1; c2 answers bq directly;
#                   c3 corroborates top; m1 off the map
#   Gamma2022Synth  nothing attached (pass 1) — off the map
#   Delta2019Synth  a stub

_FILES = {
    "claims/top.yaml": 'title: "Top"\ntext: "The top claim."\n',
    "claims/mid-a.yaml": 'title: "Mid A"\ntext: "Middle claim a."\nleads_to: [top]\n',
    "claims/mid-b.yaml": 'text: "Middle claim b, untitled."\nleads_to: [top]\n',
    "claims/leaf.yaml": 'title: "Leaf"\ntext: "The leaf claim."\nleads_to: [mid-a, mid-b]\n',
    "questions/bq.yaml": 'title: "Broad Q"\ntext: "What is the broad question?"\n',
    "methods/meth-top.yaml": 'title: "Method family"\ntext: "A family of methods."\n',
    "methods/meth-leaf.yaml": 'text: "A specific method."\nleads_to: [meth-top]\n',
    "curated/Alpha2020Synth.yaml": """\
title: "Alpha paper"
type: original
year: 2020
pass: 3
tags: [one]
authors: [{name: "A, A", position: first}]
methods:
  - {id: m1, text: "alpha method", grounded_in: [Delta2019Synth], leads_to: [meth-leaf]}
questions:
  - {id: q1, text: "Alpha question?", leads_to: [bq]}
claims:
  - {id: c1, text: "Alpha leaf claim.", quote: "x", grounded_in: [m1], leads_to: [leaf]}
  - {id: c2, text: "Alpha specific claim.", quote: "x", grounded_in: [m1], leads_to: [c1]}
  - {id: c3, text: "Alpha unattached answer.", quote: "x", grounded_in: [m1], answers: [q1]}
""",
    "curated/Beta2021Synth.yaml": """\
title: "Beta paper"
type: original
year: 2021
pass: 2
tags: [two]
authors: [{name: "B, B", position: first}]
methods:
  - {id: m1, text: "beta method"}
claims:
  - {id: c1, text: "Beta mid claim.", quote: "x", leads_to: [mid-a], contradicts: ["Alpha2020Synth:c1"]}
  - {id: c2, text: "Beta answers the broad question.", quote: "x", answers: [bq]}
  - {id: c3, text: "Beta lateral support.", quote: "x", corroborates: [top, Delta2019Synth]}
""",
    "curated/Gamma2022Synth.yaml": """\
title: "Gamma paper"
type: original
year: 2022
pass: 1
tags: [one]
authors: [{name: "G, G", position: first}]
claims:
  - {id: c1, text: "Gamma floating claim.", quote: "x"}
questions:
  - {id: q1, text: "Gamma question?"}
""",
    "stubs.yaml": 'Delta2019Synth: {title: "Delta stub", year: 2019}\n',
    "topics/topic-one.yaml": 'title: "Topic one"\nkeywords: [one]\n',
}


@pytest.fixture
def repo(tmp_path) -> Path:
    for rel, body in _FILES.items():
        f = tmp_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(body)
    return tmp_path


@pytest.fixture
def ix(repo):
    return bm.build_index(build_graph(repo))


# --- the definition ------------------------------------------------------------


def test_attachment_climbs_same_paper_ladders(ix):
    assert ix.enters("Alpha2020Synth:c1") == ["leaf"]
    assert ix.enters("Alpha2020Synth:c2") == ["leaf"]            # via c1
    assert [h.via for h in ix.entries["Alpha2020Synth:c2"]] == [["c1"]]
    assert ix.enters("Alpha2020Synth:c3") == []                  # answers a paper question only


def test_answers_to_a_broad_question_attaches_a_claim(ix):
    assert ix.enters("Beta2021Synth:c2") == ["bq"]
    assert ix.entries["Beta2021Synth:c2"][0].edge == "answers"


def test_reach_walks_every_ancestor_once(ix):
    assert ix.reach("Alpha2020Synth:c1") == ["leaf", "mid-a", "mid-b", "top"]


def test_totals_count_by_kind(ix):
    t = bm.totals(ix)
    assert t["papers"] == {"attached": 2, "total": 3}
    # A:c1, A:c2, B:c1, B:c2 are on; A:c3, B:c3 (lateral only), G:c1 are off
    assert t["claim"] == {"attached": 4, "total": 7}
    assert t["question"] == {"attached": 1, "total": 2}
    assert t["method"] == {"attached": 1, "total": 2}


# --- the tree --------------------------------------------------------------------


def test_node_counts_are_transitive_and_distinct(ix):
    top = bm.node_summary(ix, "top")
    # leaf (A:c1, A:c2) sits under both mid-a and mid-b; it is counted once beneath top
    assert (top["papers"], top["slices"]) == (2, 3)
    assert (top["direct_papers"], top["direct_slices"]) == (0, 0)
    leaf = bm.node_summary(ix, "leaf")
    assert (leaf["slices"], leaf["direct_slices"]) == (2, 2)
    assert leaf["contradict"] == {"slices": 1, "papers": 1}


def test_lateral_balance_counts_edges_into_the_subtree_not_containers(ix):
    top = bm.node_summary(ix, "top")
    assert top["corroborate"] == {"slices": 1, "papers": 1}    # B:c3 -> top (the stub is skipped)
    assert top["contradict"] == {"slices": 1, "papers": 1}     # B:c1 -> A:c1, under leaf


def test_question_state(ix):
    q = bm.node_summary(ix, "bq")
    assert q["questions"] == 1 and q["answered_questions"] == 1
    assert q["answering_claims"] == 2          # A:c3 answers A:q1; B:c2 answers bq itself
    assert q["answered"] is True


def test_tree_text_shows_a_multi_parent_node_under_each_parent(repo, capsys):
    rc, out = _run(capsys, "--root", str(repo))
    assert rc == 0
    leaf_lines = [l for l in out.splitlines() if l.strip().startswith("leaf ")]
    assert len(leaf_lines) == 2
    assert leaf_lines[0].endswith("⇈") and leaf_lines[1].endswith("↑")
    assert "Middle claim b, untitled." in out          # untitled node falls back to its text
    assert "on the map: papers 2/3" in out


def test_tree_json_has_stable_keys(repo, capsys):
    d = _json(capsys, "--root", str(repo))
    assert set(d) == {"claims", "questions", "methods", "totals"}
    assert [n["slug"] for n in d["claims"]][0] == "top"
    leaf = next(n for n in d["claims"] if n["slug"] == "leaf")
    assert set(leaf) >= {"slug", "kind", "title", "text", "parents", "children", "papers",
                         "slices", "direct_papers", "direct_slices", "corroborate", "contradict"}
    assert leaf["parents"] == ["mid-a", "mid-b"]
    assert [n["slug"] for n in d["methods"]] == ["meth-top", "meth-leaf"]


# --- one broad node ------------------------------------------------------------------


def test_node_view_groups_by_paper_and_calls_out_contradiction(repo, capsys):
    d = _json(capsys, "leaf", "--root", str(repo))
    assert d["parents"] == ["mid-a", "mid-b"] and d["ancestors"] == ["mid-a", "mid-b", "top"]
    [grp] = d["attached"]
    assert grp["citekey"] == "Alpha2020Synth" and grp["year"] == 2020 and grp["pass"] == 3
    rows = {r["ref"]: r for r in grp["slices"]}
    assert rows["Alpha2020Synth:c1"]["contradicted"] is True
    assert rows["Alpha2020Synth:c2"]["via"] == ["c1"]
    assert [c["ref"] for c in d["contradicting"]] == ["Beta2021Synth:c1"]
    rc, out = _run(capsys, "leaf", "--root", str(repo))
    assert "CONTRADICTED" in out and "via c1" in out and "contradicting (1)" in out


def test_question_view_lists_gathered_questions_and_their_answers(repo, capsys):
    d = _json(capsys, "bq", "--root", str(repo))
    rows = {r["ref"]: r for g in d["attached"] for r in g["slices"]}
    assert [a["ref"] for a in rows["Alpha2020Synth:q1"]["answered_by"]] == ["Alpha2020Synth:c3"]
    assert rows["Beta2021Synth:c2"]["edge"] == "answers"
    rc, out = _run(capsys, "bq", "--root", str(repo))
    assert "state     : answered" in out and "← Alpha2020Synth:c3" in out


def test_node_view_points_to_children(repo, capsys):
    d = _json(capsys, "top", "--root", str(repo))
    assert d["children"] == ["mid-a", "mid-b"]
    assert [c["slug"] for c in d["child_nodes"]] == ["mid-a", "mid-b"]
    assert d["meter"] == {"support": 1, "contradict": 0}    # graph.broad_meter, unchanged


# --- one paper (the reverse direction) -------------------------------------------------


def test_paper_view_splits_on_and_off_and_suggests_where(repo, capsys):
    d = _json(capsys, "Alpha2020Synth", "--root", str(repo))
    assert [r["ref"].split(":")[1] for r in d["on"]] == ["c1", "c2", "q1", "m1"]
    [off] = d["off"]
    assert off["ref"] == "Alpha2020Synth:c3"
    assert off["near"] == [{"edge": "answers", "target": "Alpha2020Synth:q1", "enters": ["bq"]}]
    assert d["counts"]["claim"] == {"attached": 2, "total": 3}


def test_one_slice_ref(repo, capsys):
    d = _json(capsys, "Alpha2020Synth:c2", "--root", str(repo))
    assert [r["ref"] for r in d["on"]] == ["Alpha2020Synth:c2"] and d["off"] == []


def test_stub_and_unknown_refs_are_errors(repo, capsys):
    assert main(["map", "Delta2019Synth", "--root", str(repo)]) == 2
    assert main(["map", "no-such-thing", "--root", str(repo)]) == 2
    assert main(["map", "Alpha2020Synth:c9", "--root", str(repo)]) == 2


# --- off the map ----------------------------------------------------------------------


def test_off_report(repo, capsys):
    d = _json(capsys, "--off", "--root", str(repo))
    assert [r["citekey"] for r in d["off"]] == ["Gamma2022Synth"]
    assert d["off"][0]["claim"] == 1 and d["off"][0]["question"] == 1
    part = {r["citekey"]: r["unattached"] for r in d["partial"]}
    assert part == {"Alpha2020Synth": {"claim": 1, "question": 0, "method": 0},
                    "Beta2021Synth": {"claim": 1, "question": 0, "method": 1}}
    rc, out = _run(capsys, "--off", "--root", str(repo))
    assert "pass 1 (1)" in out and "Gamma2022Synth" in out


def test_tag_and_topic_restrict_every_count(repo, capsys):
    d = _json(capsys, "--off", "--tag", "two", "--root", str(repo))
    assert d["scope"] == {"tag": "two", "topic": None}
    assert d["totals"]["papers"] == {"attached": 1, "total": 1}
    d = _json(capsys, "--topic", "topic-one", "--root", str(repo))
    assert d["totals"]["papers"] == {"attached": 1, "total": 2}        # Alpha on, Gamma off
    leaf = next(n for n in d["claims"] if n["slug"] == "leaf")
    assert leaf["contradict"]["slices"] == 0                           # Beta is out of scope
    assert main(["map", "--topic", "nope", "--root", str(repo)]) == 2
    assert main(["map", "Beta2021Synth", "--tag", "one", "--root", str(repo)]) == 2


# --- the finder -----------------------------------------------------------------------


def test_find_broad_first_then_slices_every_word(repo, capsys):
    d = _json(capsys, "--find", "LEAF", "--root", str(repo))
    assert [b["slug"] for b in d["broad"]] == ["leaf", "meth-leaf"]     # slugs are searched too
    assert [s["ref"] for s in d["slices"]] == ["Alpha2020Synth:c1"]
    d = _json(capsys, "--find", "alpha", "claim", "--root", str(repo))
    assert [s["ref"] for s in d["slices"]] == ["Alpha2020Synth:c1", "Alpha2020Synth:c2"]
    d = _json(capsys, "--find", "alpha", "--root", str(repo))
    refs = [s["ref"].split(":")[1] for s in d["slices"]]
    assert refs == ["c1", "c2", "m1", "q1", "c3"]                     # on-map first
    assert d["slices"][-1]["reaches"] == []


def test_off_and_find_are_exclusive(repo):
    with pytest.raises(SystemExit):
        main(["map", "--off", "--find", "x", "--root", str(repo)])


# --- the worked example ---------------------------------------------------------------


def test_example_library(capsys):
    d = _json(capsys, "--root", str(EXAMPLE))
    t = d["totals"]
    assert t["papers"] == {"attached": 3, "total": 3}
    assert t["claim"] == {"attached": 7, "total": 9}       # Lopez c2/c3 ride the local ladder
    bhc = next(n for n in d["claims"] if n["slug"] == "buffering-has-costs")
    assert (bhc["papers"], bhc["slices"]) == (2, 4)
    tsb = next(n for n in d["claims"] if n["slug"] == "throughput-scales-with-batching")
    assert tsb["contradict"]["slices"] == 1 and tsb["corroborate"]["slices"] == 1
    pb = next(n for n in d["methods"] if n["slug"] == "performance-benchmarking")
    assert (pb["slices"], pb["direct_slices"]) == (3, 0)


def test_example_paper_view_finds_where_an_off_map_claim_points(capsys):
    d = _json(capsys, "Kumar2020Net", "--root", str(EXAMPLE))
    [off] = d["off"]
    assert off["ref"] == "Kumar2020Net:c2"
    assert off["near"][0] == {"edge": "contradicts", "target": "Chen2021Sys:c2",
                              "enters": ["batching-adds-latency"]}


def test_example_text_modes_run(capsys):
    for args in ([], ["q-resource-scheduling"], ["microbenchmark"], ["Chen2021Sys"],
                 ["--off"], ["--find", "latency"]):
        rc, out = _run(capsys, *args, "--root", str(EXAMPLE))
        assert rc == 0 and out.strip()
