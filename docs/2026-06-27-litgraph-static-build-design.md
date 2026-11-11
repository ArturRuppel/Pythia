# `lit build` — static graph build + paper-centric viewer (design)

**Status:** implemented 2026-06-27 · companion to
[CONCEPT.md](../CONCEPT.md), [SCHEMA.md](../SCHEMA.md), and
[docs/2026-06-25-visualization-design.md](2026-06-25-visualization-design.md) (the view this
realizes). Implements the "generator" SCHEMA.md keeps referring to.

## 1. Goal & scope

Turn the hardcoded mockup ([`docs/mockups/litgraph-columns.html`](mockups/litgraph-columns.html))
into a real, data-driven app — driven by an actual data repo's YAML rather than inline
literals. **v1 is a static build:** a `lit build` subcommand reads the data repo, computes the
graph, and emits a self-contained HTML viewer you open directly (`file://`). No server.

This is the cheap first step deliberately chosen so we can develop against real data fast; a
`lit serve` (live re-read + PDF serving) is a likely **follow-on**, built on the *same graph
core*, and is explicitly out of scope here.

### In scope (tier A — "faithful core")

- Landing list = **all papers ranked** (rich cards for curated papers, one-line cards for
  stubs). Broad claim/question nodes are **not** in the landing list — they appear in the
  synthesis band when a paper is focused (visualization-design.md: "earned by drilling in").
- Focus a curated paper → columns fan out (**grounds ←, synthesis →**) with `leads-to` edges
  and **lateral** `corroborate`/`contradict` edges; the broad `leads_to` targets surface in the
  right-edge synthesis band here.
- Slice expansion (↓, within a paper card), each slice in its **emergent** color.
- Hover → metadata panel (see §6 for the abstract limitation).

### Out of scope (deferred)

- `lit serve`, live re-read, PDF serving/preview, OpenAlex abstract fetch.
- Citation-wall collapse (`▸ N sources`) and search/filter — *tier B*; add only if the real
  graph looks crowded once rendered (we'll know within minutes of first build).
- Slice-level edge re-routing on expand, sharpening-on-promotion, promotion write-back —
  *tier C*; some of it needs the server.
- The SQLite `graph.db` / catalog views (SCHEMA §intro): a separate future concern. v1's build
  artifact is `graph.json`, not SQLite. The graph core can back both later.

## 2. Architecture — the core/emit split

A new `lit build` subcommand in the existing `tools/lit` package (reuses `load_config` /
`--root` / `ruamel.yaml`, matching the `ingest` subcommand pattern in `cli.py`). The code
splits in two, and **the split is the point**: it is what lets a future `lit serve` reuse
everything but the last stage.

- **Graph core — `litgraph/graph.py`** — a *pure* function `build_graph(root) -> Graph`. Loads
  YAML, resolves refs, validates (SCHEMA §6), computes all emergent properties (SCHEMA §7).
  No output/serialization concerns; deterministic; the testable heart. `lit serve` will import
  this unchanged.
- **Build/emit — `litgraph/build.py` + CLI wiring** — serializes a `Graph` to `graph.json` and
  writes a self-contained `index.html` (JSON **inlined**, to dodge `file://` CORS). Output to a
  gitignored `dist/` (a disposable artifact, like `graph.db`); `--out` overridable; default
  `<root>/dist/`.

```
data repo YAML ──build_graph()──▶ Graph ──emit()──▶ dist/index.html  (JSON inlined)
  curated/ claims/                (pure core)        open in browser, file://
  questions/ methods/ stubs.yaml                     [future: lit serve reuses build_graph()]
```

## 3. The build pipeline (four pure stages, inside `build_graph`)

1. **Load.** Glob `curated/*.yaml`, `claims/*.yaml`, `questions/*.yaml`, `methods/*.yaml`;
   parse `stubs.yaml`. (ruamel.yaml, as `store.py` already uses.) Curated papers with no slices
   (bare `ingest` skeletons — e.g. `Nier2016BiophysJ`, `Ruppel2026NatPhys` in the real repo)
   are valid: they are curated containers with empty slice lists.

2. **Resolve.** Classify every edge ref by its **form** (SCHEMA §3): local slice (`c1`/`m2`/`q1`)
   · broad slug (`throughput-scales-with-batching`) · container citekey (`Liu2010Pnas`) · sharpened
   `citekey:id`. Build the node table (papers · slices · broad nodes · stubs) and resolve each
   `grounded_in` / `leads_to` / `corroborates` / `contradicts` / `answers` ref to a node.
   **Validate (SCHEMA §6)** and fail the build with a precise message on: dangling ref,
   duplicate local id, citekey that is both curated and a stub. (Quote integrity, §6 rule 4,
   is *not* re-checked here — it belongs to curation; v1 trusts it. **`leads-to` cycle
   detection (§6 rule 5) is deferred** — it's a tracked follow-up, not v1: nothing in the
   build recursively traverses `leads_to`, and `grounded_in` cycles are already absorbed by
   `reaches_floor`'s seen-set, so a cycle can't hang or crash the build.)

3. **Compute emergent properties (SCHEMA §7).** Never authored; always derived:
   - **floor vs model** (method): a method whose `grounded_in` reaches only containers (its
     source papers) is a **floor**; one that `grounded_in` other methods is a **model**.
   - **grounded vs plausible** (claim): grounded iff its `leads-to`/`grounded_in` chain reaches
     a floor (a measurement method or a `floor: true` axiom); else it dangles on reasoning.
   - **original vs borrowed** (claim): borrowed iff `grounded_in` reaches a cross-paper
     container/citation (a restatement, CONCEPT §6.1) rather than a same-paper floor.
   - **open vs answered** (question): answered iff some claim `answers` it.
   - **evidence meter** (broad claim): a broad claim is itself a claim, so lateral edges may
     target its slug directly (SCHEMA §6 allows "a claim"). **support** = #claims that
     `leads_to` or `corroborates` it; **contradict** = #claims that `contradicts` it. (On
     `example/`: `traction-scales-with-stiffness` → 1 support / 1 contradict.) A documented v1
     rule — revisit if richer lateral data wants child-level aggregation.
   - **top-altitude claims** (paper): claims with **no outgoing `leads_to`** → the card headline.
   - **pass**: authored, passed through (may be absent — see ranking below).
   - **landing rank** (`order`): **curated before stub** (the breadth tier wins first), then
     within curated by `pass` desc (absent last), then `year` desc; stubs by `year` desc. This
     keeps the two tiers cleanly separated regardless of `pass` presence. **Reality check:** the
     real data repo currently has **no `pass` fields** (only `example/` does), so curated papers
     will rank among themselves by year until the curator adds `pass` values — a curation TODO,
     not a build blocker.

4. **Emit.** Assemble the `graph.json` of §4 and write `index.html` with it inlined.

## 4. `graph.json` shape

Mirrors the mockup's `PAPERS` / `BROAD` / edge structures, but every field is *computed*:

```jsonc
{
  "papers": {
    "Ruppel2023eLife": {
      "cur": true, "pass": null, "type": "original", "year": 2023,   // pass null when unauthored
      "title": "...", "authors": [["Ruppel, A.", "first"], ...],
      "head": ["c1 text", ...],                 // top-altitude claims (no outgoing leads_to)
      "note": "...",                            // curator orientation, if present (hover)
      "slices": [                               // claims + questions + methods, in groups
        {"id": "m2", "kind": "method", "floor": true, "text": "...", "color": "floor"},
        {"id": "c1", "kind": "claim", "grounded": true, "borrowed": false, "text": "...",
         "color": "grounded"},
        {"id": "q2", "kind": "question", "answered": false, "text": "...", "color": "question"}
      ],
      "grounds": [{"key": "Sabass2007BiophysJ", "via": "m2"}, ...],   // → left columns
      "lateral": [{"key": "Liu2010Pnas", "sign": "corr", "via": "c1"}, ...],
      "cons":    [{"slug": "throughput-scales-with-batching", "via": "c1"}, ...]  // → right band
    }
  },
  "broad":  { "throughput-scales-with-batching": {"kind": "broad claim", "text": "...",
              "meter": {"s": 1, "c": 0}} },
  "stubs":  { "Liu2010Pnas": {"title": "...", "year": 2010, "type": "original", "doi": "..."} },
  "order":  ["Ruppel2023eLife", ...]            // papers only; curated→stub, pass desc, year desc
}
```

The viewer's color/edge logic stays the structure-driven code it already is; the build just
hands it the *computed* facts instead of the mockup's hand-set ones.

## 5. The viewer changes

Evolve `litgraph-columns.html` (now templated by `build.py`) to consume inlined `graph.json`
instead of the hardcoded `PAPERS`/`BROAD`/`ORDER`. **Keep**: the landing list, focus→columns,
slice expansion, hover, lateral edges, and the edge de-dup helper. **Add**: two card densities
(rich curated vs one-line stub) and rendering driven by the computed `color`/`floor`/`grounded`
flags rather than hand-set classes. PDF action shows "open needs serve."

## 6. Known limitation — no abstract in v1

The mockup hover shows an abstract, but curated YAMLs carry no `abstract` field and stubs hold
only local bib metadata (this build is offline — no OpenAlex). So v1 hover shows what we
actually have: title · authors · type · year · doi, plus the curated paper's `note` if present.
Real abstracts wait for `lit serve` (OpenAlex fetch) or a future ingest change. Documented, not
a bug.

## 7. Testing

Matches the existing offline/deterministic ethos (recorded fixtures, no live network):

- **Core unit tests** on the `example/` tree: assert computed emergent properties against the
  known example — floors (`m1`), grounded vs borrowed claims, answered vs open questions, the
  evidence meter counts, and the top-altitude headline set.
- **Build smoke test**: `example/` builds; `graph.json` has no dangling refs; `index.html` is
  written and self-contained.
- **Validation failure test**: a malformed fixture (dangling ref / duplicate id / curated-stub
  collision) makes the build fail with a clear, specific error. (`leads-to` cycle detection is
  a deferred follow-up — see §3.)

## 8. File-by-file plan

| File | Change |
|---|---|
| `tools/lit/litgraph/graph.py` | **new** — `build_graph(root) -> Graph`: load · resolve · validate · compute (the pure core) |
| `tools/lit/litgraph/build.py` | **new** — `emit(graph, out)`: `graph.json` + templated `index.html` |
| `tools/lit/litgraph/viewer/template.html` | **new** — the mockup, parameterized to load inlined JSON |
| `tools/lit/litgraph/cli.py` | add the `build` subparser + dispatch (mirrors `ingest`) |
| `tools/lit/tests/` | core property tests, build smoke test, validation-failure fixture |
| data repo `.gitignore` | add `dist/` |
| `docs/mockups/litgraph-columns.html` | source of the viewer template (kept as reference) |
