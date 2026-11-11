# tests/test_desk.py
"""The desk (SCHEMA §4): `validated` as a field, the desk derived from it, and the two commands
that read and write it. All on copies of the example library, never on a real one."""
import json
import shutil
from pathlib import Path

import pytest

from litgraph import cli
from litgraph.desk import desk, flags, on_desk, status
from litgraph.graph import BuildError, build_graph
from litgraph.model import Author, CuratedPaper
from litgraph.store import set_validated

EXAMPLE = Path(__file__).resolve().parents[3] / "example"


@pytest.fixture
def repo(tmp_path) -> Path:
    root = tmp_path / "lib"
    shutil.copytree(EXAMPLE, root, ignore=shutil.ignore_patterns("dist"))
    return root


def _set_line(repo: Path, key: str, line: str) -> None:
    """Put a raw `validated:` line under `pass:` by hand, the way a file could arrive."""
    path = repo / "curated" / f"{key}.yaml"
    text = path.read_text()
    first = next(l for l in text.splitlines() if l.startswith("pass:"))
    path.write_text(text.replace(first, f"{first}\n{line}", 1))


def _papers(repo):
    return build_graph(repo).papers


# ── the field ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("bad", ["5", "-1", '"3"', "true", "2.5"])
def test_validated_must_be_an_int_0_to_4(repo, bad):
    _set_line(repo, "Kumar2020Net", f"validated: {bad}")
    with pytest.raises(BuildError, match="validated"):
        build_graph(repo)


def test_validated_is_only_on_curated_papers(repo):
    stubs = repo / "stubs.yaml"
    text = stubs.read_text()
    key = next(l for l in text.splitlines() if l and not l[0].isspace() and not l.startswith("#"))
    stubs.write_text(text.replace(key, f"{key}\n  validated: 0", 1))
    with pytest.raises(BuildError, match="only on a curated paper"):
        build_graph(repo)


def test_validated_above_pass_is_a_build_flag_not_an_error(repo, capsys):
    _set_line(repo, "Lopez2019Arch", "validated: 4")              # pass 2
    papers = _papers(repo)                                         # builds
    assert flags(papers) == [f"Lopez2019Arch: validated 4 is above pass 2 — the owner read "
                             "further than curation ran (legal, but unusual)"]
    assert cli.main(["build", "--root", str(repo)]) == 0
    assert "desk-flag: Lopez2019Arch: validated 4 is above pass 2" in capsys.readouterr().err


def test_ingest_never_writes_validated():
    p = CuratedPaper(citekey="Chen2021Sys", title="T", type="original", year=2021, doi=None,
                     url=None, pdf=None, authors=[Author("Chen, Mei", position="first")])
    assert "validated" not in p.to_yaml()


# ── the derivation ─────────────────────────────────────────────────────────────────────────


def test_desk_absent_equal_lower_higher(repo):
    papers = _papers(repo)
    assert all(status(papers[k]) == "new"                          # absent → new
               for k in ("Chen2021Sys", "Kumar2020Net", "Lopez2019Arch"))
    set_validated(repo, "Chen2021Sys")                             # equal (4 = 4) → off
    set_validated(repo, "Kumar2020Net", 1)                         # lower (1 < 3) → changed
    set_validated(repo, "Lopez2019Arch", 3)                        # higher (3 > 2) → changed
    papers = _papers(repo)
    assert not on_desk(papers["Chen2021Sys"])
    assert status(papers["Kumar2020Net"]) == status(papers["Lopez2019Arch"]) == "changed"
    assert not any(on_desk(p) for p in papers.values() if not p.curated)   # stubs never
    groups = desk(papers)
    assert groups["new"] == []
    assert {r.citekey for r in groups["changed"]} == {"Kumar2020Net", "Lopez2019Arch"}
    assert desk(papers, only={"Kumar2020Net"})["changed"][0].validated == 1


def test_absent_pass_counts_as_zero(repo):
    path = repo / "curated" / "Lopez2019Arch.yaml"
    path.write_text(path.read_text().replace("pass: 2\n", "", 1))
    assert status(_papers(repo)["Lopez2019Arch"]) == "new"
    set_validated(repo, "Lopez2019Arch")
    lines = path.read_text().splitlines()
    assert lines[lines.index("year: 2019") + 1] == "validated: 0"   # where `pass:` would be
    assert not on_desk(_papers(repo)["Lopez2019Arch"])


def test_a_rewrite_at_the_same_pass_stays_off_the_desk(repo):
    """Agents rewrite curated files at the same pass all the time; only a change of `pass`
    puts a validated paper back on the desk."""
    set_validated(repo, "Kumar2020Net")
    path = repo / "curated" / "Kumar2020Net.yaml"
    text = path.read_text().replace('text:  "Adaptive batch sizing sustains',
                                    'text:  "Adaptive batch sizing (rewritten) sustains', 1)
    path.write_text(text + "# a later agent's note\n")
    assert not on_desk(_papers(repo)["Kumar2020Net"])
    path.write_text(path.read_text().replace("pass: 3\n", "pass: 4\n", 1))
    assert status(_papers(repo)["Kumar2020Net"]) == "changed"


# ── the writer: comments and formatting survive ───────────────────────────────────────────


def test_set_validated_adds_one_line_under_pass_and_keeps_every_other_byte(repo):
    path = repo / "curated" / "Kumar2020Net.yaml"
    path.write_text(path.read_text().replace("pass: 3\n", "pass: 3   # results read\n"
                                             "          # (a wrapped comment on pass)\n\n", 1))
    before = path.read_text()
    v = set_validated(repo, "Kumar2020Net")
    assert (v.old, v.new, v.pass_, v.changed) == (None, 3, 3, True)
    after = path.read_text().splitlines()
    i = after.index("pass: 3   # results read")
    assert after[i + 1] == "          # (a wrapped comment on pass)"
    assert after[i + 2] == "validated: 3"                          # under pass and its comment
    assert [l for j, l in enumerate(after) if j != i + 2] == before.splitlines()
    assert "leads_to:    [microbenchmark]" in path.read_text()     # aligned values untouched


def test_set_validated_in_place_keeps_its_comment_and_is_idempotent(repo):
    _set_line(repo, "Chen2021Sys", "validated: 2  # read to the discussion")
    path = repo / "curated" / "Chen2021Sys.yaml"
    v = set_validated(repo, "Chen2021Sys", 1)
    assert (v.old, v.new) == (2, 1)
    assert "validated: 1  # read to the discussion" in path.read_text()
    mtime = path.stat().st_mtime_ns
    assert not set_validated(repo, "Chen2021Sys", 1).changed      # unchanged → not rewritten
    assert path.stat().st_mtime_ns == mtime


def test_set_validated_refuses_stubs_and_bad_values(repo):
    with pytest.raises(FileNotFoundError):
        set_validated(repo, "Patel2017Vldb")
    for bad in (5, -1, True, "3"):
        with pytest.raises(ValueError):
            set_validated(repo, "Chen2021Sys", bad)


# ── lit desk / lit validate ───────────────────────────────────────────────────────────────


def _run(capsys, *args):
    rc = cli.main(list(args))
    return rc, capsys.readouterr()


def test_lit_desk_lists_groups_and_a_total(repo, capsys):
    set_validated(repo, "Kumar2020Net", 1)
    rc, out = _run(capsys, "desk", "--root", str(repo))
    assert rc == 0
    text = out.out
    assert text.index("new — never validated (2)") < text.index("changed — curation moved (1)")
    assert "Kumar2020Net" in text and "validated 1 → curated 3 results" in text
    assert text.rstrip().endswith("desk: 3 papers (2 new, 1 changed)")


def test_lit_desk_json_and_filters(repo, capsys):
    rc, out = _run(capsys, "desk", "--json", "--root", str(repo))
    data = json.loads(out.out)
    assert rc == 0 and data["total"] == 3 and data["changed"] == []
    assert set(data["new"][0]) == {"citekey", "status", "validated", "pass", "title", "year",
                                   "updated"}
    rc, out = _run(capsys, "desk", "--json", "--tag", "batching", "--root", str(repo))
    assert [r["citekey"] for r in json.loads(out.out)["new"]] == ["Chen2021Sys"]
    col = next((repo / "collections").glob("*.yaml")).stem
    rc, out = _run(capsys, "desk", "--json", "--collection", col, "--root", str(repo))
    assert rc == 0 and json.loads(out.out)["scope"]["collection"] == col
    rc, out = _run(capsys, "desk", "--collection", "no-such", "--root", str(repo))
    assert rc == 2 and "no such collection" in out.err
    rc, out = _run(capsys, "desk", "--topic", "no-such", "--root", str(repo))
    assert rc == 2


def test_lit_validate_named_papers_with_and_without_pass(repo, capsys):
    rc, out = _run(capsys, "validate", "Kumar2020Net", "--root", str(repo))
    assert rc == 0 and "Kumar2020Net: new → validated 3 results" in out.out
    rc, out = _run(capsys, "validate", "Kumar2020Net", "Chen2021Sys", "--pass", "2",
                   "--root", str(repo))
    assert rc == 0 and "Kumar2020Net: validated 3 → validated 2 intro+disc" in out.out
    rc, out = _run(capsys, "validate", "Chen2021Sys", "--pass", "2", "--root", str(repo))
    assert "already validated 2 intro+disc" in out.out
    rc, out = _run(capsys, "validate", "Lopez2019Arch", "--pass", "4", "--root", str(repo))
    assert "(above curated 2)" in out.out
    rc, out = _run(capsys, "validate", "Patel2017Vldb", "--root", str(repo))
    assert rc == 1 and "not a curated paper" in out.err
    with pytest.raises(SystemExit):
        cli.main(["validate", "Kumar2020Net", "--pass", "5", "--root", str(repo)])


def test_lit_validate_all_and_collection_with_dry_run(repo, capsys):
    col = next((repo / "collections").glob("*.yaml")).stem
    members = set(build_graph(repo).collections[col].papers)
    before = {f.name: f.read_text() for f in (repo / "curated").glob("*.yaml")}
    rc, out = _run(capsys, "validate", "--all", "--dry-run", "--root", str(repo))
    assert rc == 0 and "DRY-RUN" in out.out and "3 changed" in out.out
    assert {f.name: f.read_text() for f in (repo / "curated").glob("*.yaml")} == before
    rc, out = _run(capsys, "validate", "--collection", col, "--root", str(repo))
    assert rc == 0
    papers = _papers(repo)
    for k, p in papers.items():
        if p.curated:
            assert on_desk(p) == (k not in members), k
    rc, out = _run(capsys, "validate", "--all", "--root", str(repo))
    assert not any(on_desk(p) for p in _papers(repo).values())
    rc, out = _run(capsys, "validate", "--all", "--pass", "1", "--root", str(repo))
    assert rc == 2
    rc, out = _run(capsys, "validate", "--root", str(repo))
    assert rc == 2
