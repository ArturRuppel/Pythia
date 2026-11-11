# `lit build` — Static Graph Build + Viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `lit build` subcommand that reads a literature_graph data repo's YAML, computes the graph + emergent properties (SCHEMA §7), and emits a self-contained HTML viewer (the paper-centric column view) you open via `file://`.

**Architecture:** A pure **graph core** (`litgraph/graph.py`: load → resolve → validate → compute) that a future `lit serve` can reuse unchanged, plus a thin **emit** layer (`litgraph/build.py` + a `viewer/template.html`) that serializes the graph to inlined JSON and writes `index.html`. CLI wiring mirrors the existing `ingest` subcommand.

**Tech Stack:** Python 3.10+, `ruamel.yaml` (already a dep), `tomllib`, `argparse`, `pytest`. Vanilla JS/HTML viewer (no toolchain). Tests are offline/deterministic against the `example/` tree.

**Spec:** [docs/2026-06-27-litgraph-static-build-design.md](../../2026-06-27-litgraph-static-build-design.md) · **Source design:** [docs/2026-06-25-visualization-design.md](../../2026-06-25-visualization-design.md) · **Mockup to port:** `docs/mockups/litgraph-columns.html`

**Working directory:** **`git`/`bash`/`cp` commands run from the repo root** (`literature_graph/`) — they use repo-root paths like `tools/lit/...` and `docs/...`. **Run `pytest` from `tools/lit/`** (where `pyproject.toml` lives); pytest test-file paths in this plan are written relative to `tools/lit/`.

---

## Key data shapes (referenced by every task — read once)

`litgraph/graph.py` defines these dataclasses. Later tasks assume these exact field names.

```python
from __future__ import annotations
from dataclasses import dataclass, field

@dataclass
class Slice:
    id: str                         # "c1" | "q2" | "m3"
    kind: str                       # "claim" | "question" | "method"
    text: str
    grounded_in: list[str] = field(default_factory=list)
    leads_to: list[str] = field(default_factory=list)
    corroborates: list[str] = field(default_factory=list)
    contradicts: list[str] = field(default_factory=list)
    answers: list[str] = field(default_factory=list)
    floor_flag: bool = False        # authored `floor: true` (claim axiom)
    quote: str | None = None
    # computed (filled by build_graph):
    is_floor: bool = False          # method floor, or claim with floor_flag
    grounded: bool = False          # claim: leads-to chain reaches a floor
    borrowed: bool = False          # claim: grounded_in reaches a cross-paper container
    answered: bool = False          # question: some claim answers it
    color: str = ""                 # view color token

@dataclass
class Paper:
    citekey: str
    curated: bool
    title: str
    type: str
    year: int | None
    pass_: int | None = None        # YAML/JSON key is "pass"; "pass" is a Python keyword
    doi: str | None = None
    note: str | None = None
    authors: list[tuple[str, str, bool]] = field(default_factory=list)  # (name, position, corresponding)
    slices: list[Slice] = field(default_factory=list)
    head: list[str] = field(default_factory=list)                 # top-altitude claim texts

@dataclass
class BroadNode:
    slug: str
    kind: str                       # "broad claim" | "broad question" | "broad method"
    text: str
    support: int = 0
    contradict: int = 0

@dataclass
class Graph:
    papers: dict[str, Paper]        # curated papers AND stubs (stubs: curated=False, no slices)
    broad: dict[str, BroadNode]
    order: list[str]                # paper citekeys, landing-list order

class BuildError(Exception):
    """Raised on any SCHEMA §6 validation failure. Message names the offending ref/id."""
```

**v1 meter semantics (a documented decision — see spec §3 / CONCEPT §9):** a broad claim is
itself a claim, so lateral edges may target its slug **directly** (SCHEMA §6 allows a lateral
edge to target "a claim"). So `support` = number of claims that generalize into it (`leads_to`)
**or** `corroborates` it; `contradict` = number of claims that `contradicts` it. On the
`example/` data this yields `traction-scales-with-stiffness → 1 support (c1 leads_to) / 1
contradict (c3 contradicts the slug)`.

---

## Task 1: Ref classification

**Files:**
- Create: `litgraph/graph.py`
- Test: `tests/test_graph.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_graph.py
from litgraph.graph import classify_ref


def test_classify_ref_forms():
    assert classify_ref("c1") == "local"
    assert classify_ref("m12") == "local"
    assert classify_ref("q3") == "local"
    assert classify_ref("Liu2010Pnas") == "container"
    assert classify_ref("Ruppel2023eLife") == "container"
    assert classify_ref("Liu2010Pnas:c3") == "sharpened"
    assert classify_ref("throughput-scales-with-batching") == "broad"
    assert classify_ref("batching") == "broad"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_graph.py::test_classify_ref_forms -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'litgraph.graph'`

- [ ] **Step 3: Write minimal implementation**

```python
# litgraph/graph.py
"""Pure graph core: load a data repo's YAML, resolve refs, validate (SCHEMA §6),
compute emergent properties (SCHEMA §7). No output/serialization here."""

from __future__ import annotations

import re

_LOCAL = re.compile(r"^[cqm]\d+$")
_CITEKEY = re.compile(r"^[A-Z][A-Za-z]*\d{4}[A-Za-z]")  # <Family><Year><Venue>


def classify_ref(ref: str) -> str:
    """Classify an edge ref by its *form* (SCHEMA §3): local slice, sharpened
    cross-paper slice, container citekey, or broad slug."""
    if ":" in ref:
        return "sharpened"
    if _LOCAL.match(ref):
        return "local"
    if _CITEKEY.match(ref):
        return "container"
    return "broad"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_graph.py::test_classify_ref_forms -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/lit/litgraph/graph.py tools/lit/tests/test_graph.py
git commit -m "feat(graph): classify edge refs by form (SCHEMA §3)"
```

---

## Task 2: Dataclasses + repo loader

**Files:**
- Modify: `litgraph/graph.py`
- Test: `tests/test_graph.py`

- [ ] **Step 1: Write the failing test**

The loader reads the repo's YAML into the dataclasses. Test against the public `example/` tree (resolve its path relative to the repo root, two levels above `tools/lit/`).

```python
# tests/test_graph.py  (add)
from pathlib import Path
from litgraph.graph import load_repo, Paper, Slice

EXAMPLE = Path(__file__).resolve().parents[3] / "example"


def test_load_repo_reads_curated_and_stubs():
    papers, broad = load_repo(EXAMPLE)
    assert "Ruppel2023NatPhys" in papers
    p = papers["Ruppel2023NatPhys"]
    assert isinstance(p, Paper)
    assert p.curated is True
    assert p.type == "original" and p.year == 2023 and p.pass_ == 3
    assert ("Ruppel, Artur", "first", False) in p.authors
    # stubs load as un-sliced containers
    assert papers["Ramms2013Pnas"].curated is False
    assert papers["Ramms2013Pnas"].slices == []
    # a curated claim parses its edges
    c1 = next(s for s in p.slices if s.id == "c1")
    assert c1.kind == "claim"
    assert "traction-scales-with-stiffness" in c1.leads_to
    # broad nodes load
    assert "traction-scales-with-stiffness" in broad
    assert broad["traction-scales-with-stiffness"].kind == "broad claim"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_graph.py::test_load_repo_reads_curated_and_stubs -v`
Expected: FAIL with `ImportError: cannot import name 'load_repo'`

- [ ] **Step 3: Write minimal implementation**

Add the dataclasses from "Key data shapes" above (paste `Slice`, `Paper`, `BroadNode`, `Graph`, `BuildError` verbatim), then the loader:

```python
# litgraph/graph.py  (add: dataclass imports at top)
from dataclasses import dataclass, field
from pathlib import Path
from ruamel.yaml import YAML

_yaml = YAML(typ="safe")

# ... (paste Slice, Paper, BroadNode, Graph, BuildError dataclasses here) ...

_SLICE_GROUPS = {"claims": "claim", "questions": "question", "methods": "method"}


def _slice_from(raw: dict, kind: str) -> Slice:
    return Slice(
        id=raw["id"],
        kind=kind,
        text=raw.get("text", ""),
        grounded_in=list(raw.get("grounded_in", []) or []),
        leads_to=list(raw.get("leads_to", []) or []),
        corroborates=list(raw.get("corroborates", []) or []),
        contradicts=list(raw.get("contradicts", []) or []),
        answers=list(raw.get("answers", []) or []),
        floor_flag=bool(raw.get("floor", False)),
        quote=raw.get("quote"),
    )


def _authors_from(raw: dict) -> list[tuple[str, str, bool]]:
    out: list[tuple[str, str, bool]] = []
    for a in raw.get("authors", []) or []:
        out.append((a["name"], a.get("position", "middle"), bool(a.get("corresponding", False))))
    return out


def load_repo(root: Path) -> tuple[dict[str, Paper], dict[str, BroadNode]]:
    """Parse curated/*.yaml, claims|questions|methods/*.yaml, and stubs.yaml into
    Papers (curated + stubs) and BroadNodes. No validation/computation yet."""
    root = Path(root)
    papers: dict[str, Paper] = {}

    for f in sorted((root / "curated").glob("*.yaml")):
        raw = _yaml.load(f.read_text()) or {}
        citekey = f.stem
        slices: list[Slice] = []
        for group, kind in _SLICE_GROUPS.items():
            for s in raw.get(group, []) or []:
                slices.append(_slice_from(s, kind))
        papers[citekey] = Paper(
            citekey=citekey, curated=True,
            title=raw.get("title", ""), type=raw.get("type", "original"),
            year=raw.get("year"), pass_=raw.get("pass"),
            doi=raw.get("doi"), note=raw.get("note"),
            authors=_authors_from(raw), slices=slices,
        )

    stubs_path = root / "stubs.yaml"
    if stubs_path.exists():
        for citekey, raw in (_yaml.load(stubs_path.read_text()) or {}).items():
            raw = raw or {}
            papers[citekey] = Paper(
                citekey=citekey, curated=False,
                title=raw.get("title", ""), type=raw.get("type", "original"),
                year=raw.get("year"), doi=raw.get("doi"),
            )

    broad: dict[str, BroadNode] = {}
    for group, kind in (("claims", "broad claim"), ("questions", "broad question"),
                        ("methods", "broad method")):
        for f in sorted((root / group).glob("*.yaml")):
            raw = _yaml.load(f.read_text()) or {}
            broad[f.stem] = BroadNode(slug=f.stem, kind=kind, text=raw.get("text", ""))
    return papers, broad
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_graph.py::test_load_repo_reads_curated_and_stubs -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/lit/litgraph/graph.py tools/lit/tests/test_graph.py
git commit -m "feat(graph): dataclasses + repo loader (curated, stubs, broad)"
```

---

## Task 3: Method floor vs model (SCHEMA §7)

**Files:**
- Modify: `litgraph/graph.py`
- Test: `tests/test_graph.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_graph.py  (add)
from litgraph.graph import method_is_floor


def test_method_floor_vs_model():
    # floor: grounds only in containers (its source papers)
    floor = Slice(id="m2", kind="method", text="TFM",
                  grounded_in=["Sabass2007BiophysJ", "Bauer2021PloComputBiology"])
    assert method_is_floor(floor) is True
    # floor: no grounding at all still bottoms out
    assert method_is_floor(Slice(id="m1", kind="method", text="x")) is True
    # model: layers on another method (a local m-ref)
    model = Slice(id="m3", kind="method", text="MSM", grounded_in=["m2", "Tambe2011NatMater"])
    assert method_is_floor(model) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_graph.py::test_method_floor_vs_model -v`
Expected: FAIL with `ImportError: cannot import name 'method_is_floor'`

- [ ] **Step 3: Write minimal implementation**

```python
# litgraph/graph.py  (add)
def method_is_floor(s: Slice) -> bool:
    """A method is a floor iff it grounds only in containers (source papers) — i.e. it
    layers on no other method. A model has a local method ref in grounded_in (SCHEMA §7)."""
    return not any(classify_ref(r) == "local" for r in s.grounded_in)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_graph.py::test_method_floor_vs_model -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/lit/litgraph/graph.py tools/lit/tests/test_graph.py
git commit -m "feat(graph): method floor vs model (SCHEMA §7)"
```

---

## Task 4: Claim borrowed + grounded (SCHEMA §7)

**Files:**
- Modify: `litgraph/graph.py`
- Test: `tests/test_graph.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_graph.py  (add)
from litgraph.graph import claim_is_borrowed, reaches_floor


def test_claim_borrowed():
    borrowed = Slice(id="c4", kind="claim", text="borrowed", grounded_in=["Ramms2013Pnas"])
    assert claim_is_borrowed(borrowed) is True
    original = Slice(id="c1", kind="claim", text="orig", grounded_in=["m1"])
    assert claim_is_borrowed(original) is False
    sharp = Slice(id="c5", kind="claim", text="x", grounded_in=["Liu2010Pnas:c3"])
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_graph.py -k "claim_borrowed or reaches_floor" -v`
Expected: FAIL with `ImportError: cannot import name 'claim_is_borrowed'`

- [ ] **Step 3: Write minimal implementation**

```python
# litgraph/graph.py  (add)
def claim_is_borrowed(s: Slice) -> bool:
    """Borrowed (restated) iff grounded_in reaches a cross-paper container (CONCEPT §6.1)."""
    return any(classify_ref(r) in ("container", "sharpened") for r in s.grounded_in)


def reaches_floor(s: Slice, by_id: dict[str, Slice], seen: set[str] | None = None) -> bool:
    """Does this slice's downward (grounded_in) chain reach a floor — a method floor or a
    `floor: true` claim? Only local refs are walkable; cross-paper refs are opaque here."""
    seen = set() if seen is None else seen
    if s.id in seen:
        return False
    seen.add(s.id)
    if s.kind == "method" and s.is_floor:
        return True
    if s.kind == "claim" and s.floor_flag:
        return True
    for r in s.grounded_in:
        if classify_ref(r) != "local":
            continue
        t = by_id.get(r)
        if t is not None and reaches_floor(t, by_id, seen):
            return True
    return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_graph.py -k "claim_borrowed or reaches_floor" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/lit/litgraph/graph.py tools/lit/tests/test_graph.py
git commit -m "feat(graph): claim borrowed + grounded-reaches-floor (SCHEMA §7)"
```

---

## Task 5: Answered questions + broad-claim meter

**Files:**
- Modify: `litgraph/graph.py`
- Test: `tests/test_graph.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_graph.py  (add)
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_graph.py -k "answered or broad_meter" -v`
Expected: FAIL with `ImportError: cannot import name 'answered_question_ids'`

- [ ] **Step 3: Write minimal implementation**

```python
# litgraph/graph.py  (add)
def _global(citekey: str, ref: str) -> str:
    """Resolve a same-paper local ref to its global id; pass sharpened refs through."""
    return f"{citekey}:{ref}" if classify_ref(ref) == "local" else ref


def answered_question_ids(papers: dict[str, Paper]) -> set[str]:
    """Global ids (citekey:qN) of questions answered by some claim's `answers` edge."""
    out: set[str] = set()
    for p in papers.values():
        if not p.curated:
            continue
        for s in p.slices:
            if s.kind == "claim":
                for r in s.answers:
                    out.add(_global(p.citekey, r))
    return out


def broad_meter(slug: str, papers: dict[str, Paper]) -> tuple[int, int]:
    """v1 meter (spec §3): a broad claim is itself a claim, so lateral edges may target its
    slug directly (SCHEMA §6 allows "a claim"). support = #claims that generalize into it
    (leads_to) or corroborate it; contradict = #claims that contradict it."""
    support = 0
    contradict = 0
    for p in papers.values():
        for s in p.slices:
            if s.kind != "claim":
                continue
            if slug in s.leads_to or slug in s.corroborates:
                support += 1
            if slug in s.contradicts:
                contradict += 1
    return support, contradict
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_graph.py -k "answered or broad_meter" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/lit/litgraph/graph.py tools/lit/tests/test_graph.py
git commit -m "feat(graph): answered questions + broad-claim evidence meter"
```

---

## Task 6: Validation (SCHEMA §6)

**Files:**
- Modify: `litgraph/graph.py`
- Test: `tests/test_graph.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_graph.py  (add)
import pytest
from litgraph.graph import validate, BuildError


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_graph.py -k validate -v`
Expected: FAIL with `ImportError: cannot import name 'validate'`

- [ ] **Step 3: Write minimal implementation**

```python
# litgraph/graph.py  (add)
_EDGE_FIELDS = ("grounded_in", "leads_to", "corroborates", "contradicts", "answers")


def validate(papers: dict[str, Paper], broad: dict[str, BroadNode]) -> None:
    """Enforce the SCHEMA §6 rules that the build can check structurally: unique local ids,
    no dangling refs. Raises BuildError naming the offender. (Quote integrity and acyclicity
    of the full cross-paper DAG are out of v1 scope; same-paper cycles are caught by reaches_floor's
    seen-set, not here.)"""
    for ck, p in papers.items():
        local_ids: set[str] = set()
        for s in p.slices:
            if s.id in local_ids:
                raise BuildError(f"{ck}: duplicate local id {s.id!r}")
            local_ids.add(s.id)

    broad_slugs = set(broad)
    for ck, p in papers.items():
        local_ids = {s.id for s in p.slices}
        for s in p.slices:
            for field_name in _EDGE_FIELDS:
                for r in getattr(s, field_name):
                    if not _ref_resolves(r, local_ids, broad_slugs, papers):
                        raise BuildError(
                            f"{ck}:{s.id} {field_name} -> dangling ref {r!r}")


def _ref_resolves(ref, local_ids, broad_slugs, papers) -> bool:
    kind = classify_ref(ref)
    if kind == "local":
        return ref in local_ids
    if kind == "broad":
        return ref in broad_slugs
    if kind == "container":
        return ref in papers
    # sharpened "Citekey:id"
    base = ref.split(":", 1)[0]
    return base in papers
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_graph.py -k validate -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/lit/litgraph/graph.py tools/lit/tests/test_graph.py
git commit -m "feat(graph): validate unique ids + no dangling refs (SCHEMA §6)"
```

---

## Task 7: `build_graph` orchestrator (compute + order + color)

**Files:**
- Modify: `litgraph/graph.py`
- Test: `tests/test_graph.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_graph.py  (add)
from litgraph.graph import build_graph, Graph


def test_build_graph_example():
    g = build_graph(EXAMPLE)
    assert isinstance(g, Graph)
    p = g.papers["Ruppel2023NatPhys"]
    by_id = {s.id: s for s in p.slices}
    # m1 is a floor (grounds only in a container)
    assert by_id["m1"].is_floor is True and by_id["m1"].color == "floor"
    # c1 grounds in m1 -> grounded + original
    assert by_id["c1"].grounded is True and by_id["c1"].borrowed is False
    assert by_id["c1"].color == "grounded"
    # c4 grounds in a citation -> borrowed
    assert by_id["c4"].borrowed is True and by_id["c4"].color == "borrowed"
    # q2 answered (c4 answers it), q1 open
    assert by_id["q2"].answered is True
    assert by_id["q1"].answered is False
    # top-altitude claims become the head (no outgoing leads_to) — c3 has only contradicts
    assert p.head  # non-empty
    # broad-claim meter (example: 1 support via c1 leads_to, 1 contradict via c3)
    b = g.broad["traction-scales-with-stiffness"]
    assert (b.support, b.contradict) == (1, 1)
    # landing order: curated before stubs
    assert g.order[0] == "Ruppel2023NatPhys"
    assert g.order.index("Ruppel2023NatPhys") < g.order.index("Ramms2013Pnas")


def test_build_graph_handles_skeleton_paper(tmp_path):
    # a curated paper with no slices and no `pass` is valid and sorts after passed papers
    (tmp_path / "curated").mkdir()
    (tmp_path / "curated" / "Bare2020Jrnl.yaml").write_text(
        'title: "x"\ntype: original\nyear: 2020\nauthors: [{name: "A, B"}]\n')
    (tmp_path / "stubs.yaml").write_text("Old1990Jrnl:\n  title: t\n  year: 1990\n")
    g = build_graph(tmp_path)
    assert g.papers["Bare2020Jrnl"].slices == []
    assert g.order == ["Bare2020Jrnl", "Old1990Jrnl"]  # curated before stub
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_graph.py -k build_graph -v`
Expected: FAIL with `ImportError: cannot import name 'build_graph'`

- [ ] **Step 3: Write minimal implementation**

```python
# litgraph/graph.py  (add)
def _slice_color(s: Slice) -> str:
    if s.kind == "question":
        return "question"
    if s.kind == "method":
        return "floor" if s.is_floor else "model"
    # claim
    if s.borrowed:
        return "borrowed"
    return "grounded" if s.grounded else "plausible"


def _order(papers: dict[str, Paper]) -> list[str]:
    curated = [p for p in papers.values() if p.curated]
    stubs = [p for p in papers.values() if not p.curated]
    curated.sort(key=lambda p: (
        -(p.pass_ if p.pass_ is not None else -1), -(p.year or 0), p.citekey))
    stubs.sort(key=lambda p: (-(p.year or 0), p.citekey))
    return [p.citekey for p in curated] + [p.citekey for p in stubs]


def build_graph(root) -> Graph:
    """Load -> validate -> compute emergent properties -> order. The pure core."""
    papers, broad = load_repo(Path(root))
    validate(papers, broad)
    answered = answered_question_ids(papers)

    for p in papers.values():
        by_id = {s.id: s for s in p.slices}
        for s in p.slices:                       # methods first: floors feed grounded
            if s.kind == "method":
                s.is_floor = method_is_floor(s)
            elif s.kind == "claim" and s.floor_flag:
                s.is_floor = True
        for s in p.slices:
            if s.kind == "claim":
                s.borrowed = claim_is_borrowed(s)
                s.grounded = reaches_floor(s, by_id)
            elif s.kind == "question":
                s.answered = f"{p.citekey}:{s.id}" in answered
            s.color = _slice_color(s)
        p.head = [s.text for s in p.slices if s.kind == "claim" and not s.leads_to]

    for slug, b in broad.items():
        if b.kind == "broad claim":
            b.support, b.contradict = broad_meter(slug, papers)

    return Graph(papers=papers, broad=broad, order=_order(papers))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_graph.py -k build_graph -v`
Expected: PASS

- [ ] **Step 5: Run the full graph test module + commit**

Run: `pytest tests/test_graph.py -v`
Expected: PASS (all graph-core tests)

```bash
git add tools/lit/litgraph/graph.py tools/lit/tests/test_graph.py
git commit -m "feat(graph): build_graph orchestrator (compute, color, landing order)"
```

---

## Task 8: JSON serialization (`to_json_dict`)

**Files:**
- Create: `litgraph/build.py`
- Test: `tests/test_build.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_build.py
from pathlib import Path
from litgraph.graph import build_graph
from litgraph.build import to_json_dict

EXAMPLE = Path(__file__).resolve().parents[3] / "example"


def test_to_json_dict_shape():
    d = to_json_dict(build_graph(EXAMPLE))
    assert set(d) == {"papers", "broad", "stubs", "order"}
    # curated paper carries computed slices + edge lists
    p = d["papers"]["Ruppel2023NatPhys"]
    assert p["cur"] is True and p["pass"] == 3
    assert p["authors"][0] == ["Ruppel, Artur", "first", False]
    c1 = next(s for s in p["slices"] if s["id"] == "c1")
    assert c1["color"] == "grounded" and c1["kind"] == "claim"
    assert any(g["via"] == "m1" for g in p["grounds"])          # grounds -> left
    assert any(co["slug"] == "traction-scales-with-stiffness" for co in p["cons"])
    assert any(l["sign"] in ("corr", "contra") for l in p["lateral"])
    # stubs are separated out (one-line cards), not under papers' slices
    assert "Ramms2013Pnas" in d["stubs"]
    assert d["stubs"]["Ramms2013Pnas"]["year"] == 2013
    # broad claim carries its meter
    assert "meter" in d["broad"]["traction-scales-with-stiffness"]
    # order is papers (curated + stubs), curated first
    assert d["order"][0] == "Ruppel2023NatPhys"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_build.py::test_to_json_dict_shape -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'litgraph.build'`

- [ ] **Step 3: Write minimal implementation**

```python
# litgraph/build.py
"""Emit layer: serialize a Graph to inlined JSON and write the self-contained viewer."""

from __future__ import annotations

from litgraph.graph import Graph, Paper, classify_ref


def _grounds(p: Paper) -> list[dict]:
    """Left-column targets: each grounded_in ref that points at a container (a source paper)."""
    out = []
    for s in p.slices:
        for r in s.grounded_in:
            if classify_ref(r) in ("container", "sharpened"):
                out.append({"key": r.split(":", 1)[0], "via": s.id})
    return out


def _lateral(p: Paper) -> list[dict]:
    out = []
    for s in p.slices:
        for r in s.corroborates:
            out.append({"key": r.split(":", 1)[0], "sign": "corr", "via": s.id})
        for r in s.contradicts:
            out.append({"key": r.split(":", 1)[0], "sign": "contra", "via": s.id})
    return out


def _cons(p: Paper) -> list[dict]:
    """Right-band targets: each leads_to broad slug."""
    out = []
    for s in p.slices:
        for slug in s.leads_to:
            out.append({"slug": slug, "via": s.id})
    return out


def _paper_json(p: Paper) -> dict:
    return {
        "cur": p.curated, "pass": p.pass_, "type": p.type, "year": p.year,
        "title": p.title, "authors": [[n, pos, corr] for n, pos, corr in p.authors],
        "note": p.note, "head": p.head,
        "slices": [{"id": s.id, "kind": s.kind, "text": s.text, "color": s.color,
                    "is_floor": s.is_floor, "grounded": s.grounded,
                    "borrowed": s.borrowed, "answered": s.answered}
                   for s in p.slices],
        "grounds": _grounds(p), "lateral": _lateral(p), "cons": _cons(p),
    }


def to_json_dict(g: Graph) -> dict:
    curated = {ck: _paper_json(p) for ck, p in g.papers.items() if p.curated}
    stubs = {ck: {"title": p.title, "year": p.year, "type": p.type, "doi": p.doi}
             for ck, p in g.papers.items() if not p.curated}
    broad = {slug: {"kind": b.kind, "text": b.text,
                    "meter": ({"s": b.support, "c": b.contradict}
                              if b.kind == "broad claim" else None)}
             for slug, b in g.broad.items()}
    return {"papers": curated, "broad": broad, "stubs": stubs, "order": g.order}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_build.py::test_to_json_dict_shape -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tools/lit/litgraph/build.py tools/lit/tests/test_build.py
git commit -m "feat(build): to_json_dict — graph -> viewer JSON shape"
```

---

## Task 9: Viewer template (port the mockup to load injected JSON)

**Files:**
- Create: `litgraph/viewer/template.html` (copy of `docs/mockups/litgraph-columns.html`, edited)
- Test: manual (browser) + `node --check` in Task 10's emit test

- [ ] **Step 1: Copy the mockup into the package as the template**

```bash
mkdir -p tools/lit/litgraph/viewer
cp docs/mockups/litgraph-columns.html tools/lit/litgraph/viewer/template.html
```

- [ ] **Step 2: Replace the hardcoded data block with an injection token**

In `tools/lit/litgraph/viewer/template.html`, delete the three hardcoded literals
(`const PAPERS={...};`, `const BROAD={...};`, `const ORDER=[...];`) and replace them with a
single injection point plus destructuring:

```javascript
// ── data: injected by `lit build` (replaces the mockup's hardcoded literals) ──
const GRAPH = /*__GRAPH_JSON__*/ {"papers":{},"broad":{},"stubs":{},"order":[]} /*__END__*/;
const PAPERS = GRAPH.papers;
const BROAD = GRAPH.broad;
const STUBS = GRAPH.stubs;
const ORDER = GRAPH.order;
```

- [ ] **Step 3: Teach the viewer about stubs as one-line cards**

The mockup's `PAPERS` held both curated and stub records; now stubs live in `STUBS`. Update
`paperCard(key, level)` to look up either map and render a compact one-liner for stubs. Replace
the body-building branch in `paperCard` with:

```javascript
function paperCard(key, level){
  const p = PAPERS[key] || STUBS[key];
  const cur = !!(PAPERS[key] && PAPERS[key].cur);
  const id = `${level}:${key}`;
  const el = document.createElement("div");
  el.className = `card ${cur ? 'curated' : 'stub'}`;
  el.id = "card-" + id; el.dataset.key = key; el.dataset.id = id;
  if (cur) {
    let body = `${dots(p.pass)}
      <div class="chd"><span class="ckey">${key}</span>
        <span class="ctype ${p.type}">${p.type}</span><span class="cyr">${p.year}</span></div>
      <div class="ctitle">${p.title}</div>`;
    if (p.authors) body += `<div class="cauth">${authLine(p.authors)}</div>`;
    body += `<div class="chead">▸ ${(p.head && p.head[0]) || p.title}</div>
             <div class="slices">${sliceRows(p)}</div>`;
    el.innerHTML = body;
  } else {
    el.innerHTML = `${dots(null)}
      <div class="chd onelign"><span class="ckey">${key}</span>
        <span class="cyr">${p.year || ''}</span></div>
      <div class="ctitle stub1">${p.title}</div>`;
  }
  el.addEventListener("mousemove", e => showTip(e, key));
  el.addEventListener("mouseleave", () => tip.style.display = "none");
  el.addEventListener("click", e => {
    if (e.target.closest(".chd") || e.target.closest(".chead")) {
      if (cur) el.classList.toggle("open"); redraw(); return;
    }
    if (cur) focus(key);
  });
  return el;
}
```

- [ ] **Step 4: Update `authLine` (3-tuple) and `sliceRows` (computed color, grouped by kind)**

Replace the mockup's `authLine` (which assumed the old `[name, tier]` shape) with one that
stars the corresponding author from the `[name, position, corresponding]` tuple:

```javascript
function authLine(a){return a.map(([n, pos, corr]) =>
  corr ? `<span class="star">${n}*</span>` : n).join(' · ');}
```

Then replace `sliceRows`:

```javascript
const GROUP_LABEL = {method: "Methods", claim: "Claims", question: "Questions"};
const SID_CLASS = {floor: "fl", model: "fl", grounded: "cl", borrowed: "bo",
                   plausible: "cl", question: "q"};
function sliceRows(p){
  let html = "", lastKind = null;
  for (const s of p.slices) {
    if (s.kind !== lastKind) { html += `<div class="sgrp">${GROUP_LABEL[s.kind]}</div>`; lastKind = s.kind; }
    html += `<div class="slice"><span class="sid ${SID_CLASS[s.color] || 'cl'}">${s.id}</span>`
          + `<span class="stx">${s.text}</span></div>`;
  }
  return html;
}
```

- [ ] **Step 5: Update `showTip` for the no-abstract v1 + stubs**

```javascript
function showTip(e, key){
  const cur = !!(PAPERS[key] && PAPERS[key].cur);
  const p = PAPERS[key] || STUBS[key];
  tip.innerHTML = `<h4>${key}</h4>
    <div class="meta">${p.type || 'stub'} · ${p.year || ''}${cur ? ` · curated${p.pass!=null?` (Pass ${p.pass})`:''}` : ' · stub'}</div>
    <div class="abs">${cur ? (p.note || p.title) : p.title}</div>
    ${cur ? `<div class="nopdf">PDF preview/open needs <code>lit serve</code></div>`
          : `<div class="nopdf">uncurated stub — bib metadata only</div>`}`;
  tip.style.display = "block";
  const pad = 14, w = 300, h = tip.offsetHeight;
  let x = e.clientX + pad, y = e.clientY + pad;
  if (x + w > innerWidth) x = e.clientX - w - pad;
  if (y + h > innerHeight) y = innerHeight - h - pad;
  tip.style.left = x + "px"; tip.style.top = y + "px";
}
```

- [ ] **Step 6: Fix `dots()` to accept a possibly-null pass and add a `.stub1` style**

`dots(pass)` already handles `pass != null`; no change needed. Add to the `<style>` block:

```css
  .stub1{padding:5px 11px 8px;font-size:9.5px;color:var(--dim)}
  .chd.onelign{padding:7px 11px 2px 36px}
  --plausible:#8b98a5;
```

(Place the `--plausible` line inside the existing `:root{...}` block, and map a plausible claim
to it: in the SVG/legend code no change is needed since slice color classes drive only the id
chip. The `.sid.cl` chip already covers grounded/plausible.)

- [ ] **Step 7: Sanity-check the edited template's JS parses**

Run:
```bash
python3 - <<'PY'
import re, pathlib
html = pathlib.Path("tools/lit/litgraph/viewer/template.html").read_text()
m = re.search(r"<script>(.*)</script>", html, re.S)
# fill the injection token so the file is valid standalone JS
js = m.group(1).replace("/*__GRAPH_JSON__*/", "").replace("/*__END__*/", "")
pathlib.Path("/tmp/tmpl.js").write_text(js)
PY
node --check /tmp/tmpl.js && echo "TEMPLATE JS OK"
```
Expected: `TEMPLATE JS OK`

- [ ] **Step 8: Commit**

```bash
git add tools/lit/litgraph/viewer/template.html
git commit -m "feat(viewer): port mockup to a build template (injected JSON, stub cards)"
```

---

## Task 10: `emit` — write `graph.json` + `index.html`

**Files:**
- Modify: `litgraph/build.py`
- Modify: `tests/test_build.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_build.py  (add)
import json
from litgraph.build import emit


def test_emit_writes_self_contained_viewer(tmp_path):
    g = build_graph(EXAMPLE)
    emit(g, tmp_path)
    gj = tmp_path / "graph.json"
    html = tmp_path / "index.html"
    assert gj.exists() and html.exists()
    # graph.json round-trips
    data = json.loads(gj.read_text())
    assert "Ruppel2023NatPhys" in data["papers"]
    # index.html has the JSON inlined (self-contained) and no leftover token
    text = html.read_text()
    assert "Ruppel2023NatPhys" in text
    assert "__GRAPH_JSON__" not in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_build.py::test_emit_writes_self_contained_viewer -v`
Expected: FAIL with `ImportError: cannot import name 'emit'`

- [ ] **Step 3: Write minimal implementation**

```python
# litgraph/build.py  (add)
import json
from pathlib import Path

_TEMPLATE = Path(__file__).parent / "viewer" / "template.html"
_TOKEN_START = "/*__GRAPH_JSON__*/"
_TOKEN_END = "/*__END__*/"


def emit(g: Graph, out: Path) -> None:
    """Write graph.json and a self-contained index.html (JSON inlined) into `out`."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    data = to_json_dict(g)
    payload = json.dumps(data, ensure_ascii=False)
    (out / "graph.json").write_text(payload, encoding="utf-8")

    template = _TEMPLATE.read_text(encoding="utf-8")
    start = template.index(_TOKEN_START)
    end = template.index(_TOKEN_END) + len(_TOKEN_END)
    html = template[:start] + payload + template[end:]
    (out / "index.html").write_text(html, encoding="utf-8")
```

(Add `from litgraph.graph import Graph, Paper, classify_ref` already exists; ensure `json` and
`Path` imports are at the top of `build.py`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_build.py -v`
Expected: PASS (both build tests)

- [ ] **Step 5: Commit**

```bash
git add tools/lit/litgraph/build.py tools/lit/tests/test_build.py
git commit -m "feat(build): emit graph.json + self-contained index.html"
```

---

## Task 11: CLI `build` subcommand

**Files:**
- Modify: `litgraph/cli.py`
- Test: `tests/test_build.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_build.py  (add)
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_build.py -k cli_build -v`
Expected: FAIL (no `build` subcommand → `SystemExit: 2` from argparse)

- [ ] **Step 3: Write minimal implementation**

In `litgraph/cli.py`, add the subparser after the `ingest` one (around line 63) and a dispatch
branch before the final `return 2` (around line 88). Add the imports at the top.

```python
# litgraph/cli.py  (top, with other imports)
from litgraph.graph import build_graph, BuildError
from litgraph.build import emit
```

```python
# litgraph/cli.py  (after the p_ing block)
    p_build = sub.add_parser("build", help="build the static graph viewer from a data repo")
    p_build.add_argument("--root", default=".", help="data root (curated/, stubs.yaml, ...)")
    p_build.add_argument("--out", default=None,
                         help="output dir (default: <root>/dist)")
```

```python
# litgraph/cli.py  (dispatch, before `return 2`)
    if args.command == "build":
        cfg = load_config(args.root)
        out = Path(args.out) if args.out else cfg.root / "dist"
        try:
            graph = build_graph(cfg.root)
        except BuildError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        emit(graph, out)
        print(f"built {len(graph.papers)} papers -> {out}/index.html")
        return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_build.py -k cli_build -v`
Expected: PASS

- [ ] **Step 5: Run the whole suite**

Run: `pytest -q`
Expected: PASS (all prior tests + the new graph/build tests)

- [ ] **Step 6: Commit**

```bash
git add tools/lit/litgraph/cli.py tools/lit/tests/test_build.py
git commit -m "feat(cli): add `lit build` subcommand"
```

---

## Task 12: End-to-end on real data + gitignore + docs

**Files:**
- Modify: data repo `.gitignore` (the standalone `~/Projects/Pythia-database`)
- Modify: `CLAUDE.md` (tool list), `docs/2026-06-27-litgraph-static-build-design.md` (mark built)

- [ ] **Step 1: Build the real data repo and eyeball it**

Run:
```bash
cd tools/lit && pip install -e . >/dev/null 2>&1; cd ../..
lit build --root ~/Projects/Pythia-database --out ~/Projects/Pythia-database/dist
```
Expected: `built 417 papers -> .../dist/index.html` (7 curated + ~410 stubs; count may differ).

> If this instead prints `error: <ref> -> dangling ref ...` and exits 1, that is the validator
> doing its job: a real curated file references a slug/citekey that doesn't resolve (e.g. a
> `leads_to` to a broad-method slug with no `methods/` file). Fix the **data** (add the missing
> broad file, or correct the ref) — it is not a code bug — then re-run. Report it to the human
> rather than weakening validation.

Open `~/Projects/Pythia-database/dist/index.html` in a browser. Verify: the landing
list ranks the 7 curated papers above the stubs; clicking `Ruppel2023eLife` fans grounds left +
the synthesis band right with edges; expanding it shows slices in their emergent colors; hover
shows metadata (no abstract); no console errors.

- [ ] **Step 2: Note any crowding (tier-B trigger)**

If a focused paper's grounds column is unreadably tall (many stub grounds), record it — that is
the signal to add tier-B citation-wall collapse in a follow-up. Do not implement it here.

- [ ] **Step 3: Gitignore the build artifact in the data repo**

Run:
```bash
cd ~/Projects/Pythia-database
grep -qxF "dist/" .gitignore 2>/dev/null || echo "dist/" >> .gitignore
git add .gitignore && git commit -m "chore: ignore dist/ (lit build artifact)"
cd -
```

- [ ] **Step 4: Update CLAUDE.md tool list**

In `CLAUDE.md`, under `## Tools`, add a bullet after the `lit ingest` entry:

```markdown
- **`lit build`** — build the static graph viewer: reads the data repo's YAML, computes the
  graph + emergent properties (SCHEMA §7), and emits a self-contained `dist/index.html`
  (the paper-centric column view) plus `graph.json`. Open the HTML directly; no server.
```

- [ ] **Step 5: Mark the design doc built**

In `docs/2026-06-27-litgraph-static-build-design.md`, change the Status line from
`design (approved 2026-06-27, not yet implemented)` to `implemented 2026-06-27`.

- [ ] **Step 6: Commit the docs**

```bash
git add CLAUDE.md docs/2026-06-27-litgraph-static-build-design.md
git commit -m "docs: record `lit build` in CLAUDE.md; mark design implemented"
```

---

## Done criteria

- `pytest -q` green from `tools/lit/` (existing 25 tests + new graph-core and build tests).
- `lit build --root <example-or-data-repo>` writes `dist/index.html` + `graph.json`.
- The viewer opens with no console errors: pass-ranked landing list, focus→columns with
  correct edge styles, slice expansion in emergent colors, metadata hover.
- A malformed repo fails the build with a clear, ref-naming error (exit 1).
