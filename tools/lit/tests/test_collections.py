"""Collections (SCHEMA §10): papers gathered for a purpose, membership authored on the collection.

A collection is the mirror image of a topic: membership is written on the collection and never
on the paper, it may list stubs, and it is not graph — no edge targets it, nothing emergent reads
it. These tests hold those lines, the build-time validation, the payload the viewer reads, and
the `lit collection` CLI (including minting a stub for a DOI nobody has ingested). Offline: the
DOI path runs against the recorded OpenAlex/Crossref fixtures test_ingest.py uses.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from litgraph.build import to_json_dict
from litgraph.cli import main
from litgraph.collection import (CollectionError, create, edit_papers, load_collections,
                                 memberships, slugify, validate_collections)
from litgraph.graph import BuildError, build_graph
from litgraph.sources.crossref import Crossref
from litgraph.sources.openalex import OpenAlex

EXAMPLE = Path(__file__).resolve().parents[3] / "example"
FIX = Path(__file__).parent / "fixtures"
SEARCH = Path(__file__).parents[1] / "litgraph/viewer/js/14-search.js"


@pytest.fixture()
def repo(tmp_path):
    """A writable copy of the worked example (3 curated papers, 5 stubs, one collection)."""
    root = tmp_path / "example"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns("dist"))
    return root


def _write(root: Path, slug: str, body: str) -> None:
    (root / "collections").mkdir(exist_ok=True)
    (root / "collections" / f"{slug}.yaml").write_text(body)


# --- loading + payload ----------------------------------------------------------------------

def test_absent_tree_is_empty_not_an_error(tmp_path):
    assert load_collections(tmp_path) == {}
    (tmp_path / "curated").mkdir()
    assert to_json_dict(build_graph(tmp_path))["collections"] == {}


def test_example_collection_emits_title_date_and_authored_order():
    """The viewer finds a collection by title and lists `papers` as authored — curated and stubs
    together; PAPERS / STUBS tell them apart, so the payload carries no tier of its own."""
    c = to_json_dict(build_graph(EXAMPLE))["collections"]["batching-review"]
    assert c["title"] == "Batching review"
    assert c["date"] == "2026-10-29"
    assert c["papers"] == ["Chen2021Sys", "Kumar2020Net", "West2015Sigmod", "Zhao2014Nsdi"]


def test_unquoted_yaml_date_reads_back_as_the_iso_text(repo):
    _write(repo, "talk", 'title: "Talk"\ndate: 2026-11-02\npapers: [Chen2021Sys]\n')
    assert load_collections(repo)["talk"].date == "2026-11-02"


def test_membership_is_never_on_the_paper_and_never_graph(repo):
    """Deleting collections/ changes nothing but the `collections` key: no paper field, no
    slice, no edge, no emergent property reads it."""
    with_c = to_json_dict(build_graph(repo))
    shutil.rmtree(repo / "collections")
    without = to_json_dict(build_graph(repo))
    assert with_c.pop("collections") and without.pop("collections") == {}
    assert with_c == without


def test_memberships_is_the_derived_inverse():
    cols = load_collections(EXAMPLE)
    assert memberships(cols)["West2015Sigmod"] == ["batching-review"]
    assert "Lopez2019Arch" not in memberships(cols)


# --- validation (the build is the validator) ------------------------------------------------

@pytest.mark.parametrize("slug, body, match", [
    ("x", 'title: "X"\npapers: [Nobody2020Nope]\n', "neither a curated paper nor a stub"),
    ("x", 'title: "X"\npapers: [Chen2021Sys, Chen2021Sys]\n', "listed twice"),
    ("x", 'note: "no title"\npapers: [Chen2021Sys]\n', "no title"),
    ("Not_Kebab", 'title: "X"\npapers: []\n', "kebab-case"),
    ("performance", 'title: "X"\npapers: []\n', "also names"),          # a topic
    ("batching-adds-latency", 'title: "X"\npapers: []\n', "also names"),  # a broad claim
])
def test_build_fails_on_invalid_collections(repo, slug, body, match):
    _write(repo, slug, body)
    with pytest.raises(BuildError, match=match):
        build_graph(repo)


def test_slug_may_not_name_a_citekey(repo):
    cols = {"chen2021sys": load_collections(EXAMPLE)["batching-review"]}
    with pytest.raises(CollectionError, match="also names"):
        validate_collections(cols, {"Chen2021Sys": None}, {"chen2021sys"})


def test_a_collection_is_never_an_edge_target(repo):
    """SCHEMA §9 rule 4, applied to collections: a collection slug in a slice edge resolves to
    nothing (refs resolve bare names against broad slugs and containers only), so it fails."""
    p = repo / "curated" / "Kumar2020Net.yaml"
    text = p.read_text()
    assert "claims:" in text
    p.write_text(text.replace("claims:\n", "claims:\n  - {id: c99, text: x, quote: null, "
                                           "leads_to: [batching-review]}\n", 1))
    with pytest.raises(BuildError, match="batching-review"):
        build_graph(repo)


def test_cli_build_reports_a_dangling_citekey(repo, tmp_path, capsys):
    _write(repo, "x", 'title: "X"\npapers: [Nobody2020Nope]\n')
    assert main(["build", "--root", str(repo), "--out", str(tmp_path / "out")]) == 1
    assert "Nobody2020Nope" in capsys.readouterr().err


# --- writes ---------------------------------------------------------------------------------

def test_slugify():
    assert slugify("Batching review") == "batching-review"
    assert slugify("  ERC 2027: Starting grant! ") == "erc-2027-starting-grant"


def test_edit_papers_round_trips_comments_and_dedups(repo):
    path = repo / "collections" / "batching-review.yaml"
    changed, now = edit_papers(repo, "batching-review", add=["Lopez2019Arch", "Chen2021Sys"])
    assert changed == ["Lopez2019Arch"]
    assert now[-1] == "Lopez2019Arch" and now.count("Chen2021Sys") == 1
    assert path.read_text().startswith("# Collection (SCHEMA §10)")   # the header comment survives
    changed, now = edit_papers(repo, "batching-review", remove=["West2015Sigmod", "Absent"])
    assert changed == ["West2015Sigmod"] and "West2015Sigmod" not in now
    before = path.read_text()
    assert edit_papers(repo, "batching-review", add=["Chen2021Sys"])[0] == []
    assert path.read_text() == before                                  # no change, no write


def test_create_refuses_to_overwrite(repo):
    create(repo, "grant", "Grant")
    with pytest.raises(CollectionError, match="already exists"):
        create(repo, "grant", "Grant again")


# --- the CLI --------------------------------------------------------------------------------

def _offline(monkeypatch, calls):
    """Route stub_for_doi's metadata lookups to the recorded eLife fixtures."""
    focal = json.loads((FIX / "oa_focal.json").read_text())
    cr = json.loads((FIX / "cr_focal.json").read_text())

    def oa_get(url):
        calls.append(url)
        return focal if "/works/https://doi.org/" in url else {"results": []}

    monkeypatch.setattr("litgraph.ingest.OpenAlex",
                        lambda mailto="": OpenAlex(mailto="t@e", get_json=oa_get))
    monkeypatch.setattr("litgraph.ingest.Crossref",
                        lambda mailto="": Crossref(mailto="t@e", get_json=lambda url: cr))


def test_cli_new_add_by_citekey_and_doi_then_show_and_list(repo, monkeypatch, capsys):
    calls = []
    _offline(monkeypatch, calls)
    r = ["--root", str(repo)]
    assert main(["collection", "new", "Caching review", "--note", "peer review",
                 "--date", "2026-10-29", *r]) == 0
    assert (repo / "collections" / "caching-review.yaml").is_file()

    # by citekey: a curated paper and a stub; by DOI: an existing stub resolves to its key
    # without a lookup, and an unknown DOI is minted as a stub first
    stubs_before = (repo / "stubs.yaml").read_text()
    assert main(["collection", "add", "caching-review", "Chen2021Sys", "Zhao2014Nsdi",
                 "https://doi.org/10.0000/SYNTH.west2015", "10.7554/eLife.83588", *r]) == 0
    out = capsys.readouterr().out
    assert "is already West2015Sigmod" in out
    assert "+ stub Ruppel2023eLife" in out
    assert len(calls) == 1                                     # only the unknown DOI went out
    papers = load_collections(repo)["caching-review"].papers
    assert papers == ["Chen2021Sys", "Zhao2014Nsdi", "West2015Sigmod", "Ruppel2023eLife"]

    stubs = (repo / "stubs.yaml").read_text()
    assert stubs.startswith(stubs_before.rstrip("\n"))          # additive; comments intact
    assert "Ruppel2023eLife:" in stubs and "10.7554/eLife.83588" in stubs
    g = build_graph(repo)                                      # and the whole thing validates
    assert not g.papers["Ruppel2023eLife"].curated

    # adding the same DOI again mints nothing and adds nothing
    assert main(["collection", "add", "caching-review", "10.7554/ELIFE.83588", *r]) == 0
    assert "0 added" in capsys.readouterr().out
    assert (repo / "stubs.yaml").read_text() == stubs

    assert main(["collection", "show", "caching-review", *r]) == 0
    out = capsys.readouterr().out
    assert "1 curated, 3 stub" in out and "Ruppel2023eLife" in out
    assert main(["collection", *r]) == 0                       # bare = list
    out = capsys.readouterr().out
    assert "caching-review" in out and "batching-review" in out


def test_cli_add_dry_run_writes_nothing(repo, monkeypatch, capsys):
    _offline(monkeypatch, [])
    before = (repo / "stubs.yaml").read_text()
    col = (repo / "collections" / "batching-review.yaml").read_text()
    assert main(["collection", "add", "batching-review", "10.7554/eLife.83588", "--dry-run",
                 "--root", str(repo)]) == 0
    assert "DRY-RUN" in capsys.readouterr().out
    assert (repo / "stubs.yaml").read_text() == before
    assert (repo / "collections" / "batching-review.yaml").read_text() == col


def test_cli_add_reports_what_it_cannot_resolve(repo, monkeypatch, capsys):
    monkeypatch.setattr("litgraph.ingest.OpenAlex",
                        lambda mailto="": OpenAlex(mailto="t@e", get_json=lambda u: {"results": []}))
    monkeypatch.setattr("litgraph.ingest.Crossref",
                        lambda mailto="": Crossref(mailto="t@e", get_json=lambda u: {}))
    monkeypatch.setattr(OpenAlex, "fetch_work", lambda self, doi: None)
    monkeypatch.setattr(Crossref, "fetch_work", lambda self, doi: None)
    rc = main(["collection", "add", "batching-review", "Lopez2019Arch", "NotAKey",
               "10.9999/nowhere", "--root", str(repo)])
    assert rc == 1
    cap = capsys.readouterr()
    assert "NotAKey" in cap.err and "10.9999/nowhere" in cap.err
    # what did resolve still lands
    assert "Lopez2019Arch" in load_collections(repo)["batching-review"].papers


def test_cli_remove_by_citekey_or_doi(repo, capsys):
    assert main(["collection", "remove", "batching-review", "Zhao2014Nsdi",
                 "10.0000/synth.west2015", "--root", str(repo)]) == 0
    assert load_collections(repo)["batching-review"].papers == ["Chen2021Sys", "Kumar2020Net"]
    assert main(["collection", "remove", "batching-review", "Zhao2014Nsdi",
                 "--root", str(repo)]) == 1                     # no longer in it: say so


def test_cli_new_refuses_a_reserved_slug(repo, capsys):
    assert main(["collection", "new", "Performance", "--root", str(repo)]) == 1
    assert "already names" in capsys.readouterr().err


# --- the viewer: a collection is found by its title -----------------------------------------

def test_search_finds_a_collection_by_title_or_slug_not_note():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed to execute the viewer's matcher")
    src = SEARCH.read_text()
    fn = src[src.index("function collectionHits("):src.index("const _collCount")]
    harness = """
    const assert = require('node:assert/strict');
    const COLLECTIONS = {
      'batching-review': {title: 'Batching review', date: '2026-10-29', note: 'grant', papers: []},
      'erc-grant': {title: 'ERC grant', date: '2027-01-01', note: 'for the Batching review too', papers: []},
    };
    """
    checks = """
    assert.deepEqual(collectionHits('Batching review'), ['batching-review']);
    assert.deepEqual(collectionHits('batching'), ['batching-review']);   // case-insensitive
    assert.deepEqual(collectionHits('review batch'), ['batching-review']);  // terms AND-ed
    assert.deepEqual(collectionHits('erc-grant'), ['erc-grant']);            // slug counts
    assert.deepEqual(collectionHits('grant'), ['erc-grant']);                // note does not
    assert.deepEqual(collectionHits('  '), []);
    """
    res = subprocess.run([node, "-e", harness + fn + checks], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
