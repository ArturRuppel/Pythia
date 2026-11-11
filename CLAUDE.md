# CLAUDE.md — project context for agents

`literature_graph` is a **knowledge graph over the scientific literature**, built for the
AI-proposes / human-curates rhythm. You (an AI agent) do the heavy lifting — parsing PDFs,
drafting claims, fetching metadata — and a human accepts / edits / rejects. **Curation is
the rate limiter; never flood. A half-finished graph is a normal, valid state.**

## Read these first (in order)

1. [CONCEPT.md](CONCEPT.md) — the model: **one primitive (the slice) in a container
   (the paper), three edges**, everything else emergent. *What* the graph is and *why*.
2. [SCHEMA.md](SCHEMA.md) — the on-disk data model: one diffable YAML per curated paper,
   thin files for broad slices, a stub registry. *How* it's written to disk.
3. [CURATION.md](CURATION.md) — the reading protocol: the four-pass sweep that turns a
   paper's full text into its proposed local subgraph. *How* a paper is read in.
4. [tools/lit/](tools/lit/) — the `lit` CLI, self-contained (package, tests, spec).
5. [example/](example/) — a small worked library on the lean slice model (SCHEMA v2).

## Mental model (the 30-second version)

- **One primitive — the slice**, inside a **container `P`** (the paper). Three slice kinds:
  **Claim · Question · Method**, each welded to an exact `quote` (methods optional),
  recursively sliceable. A paper *is* its slices.
- **Three edges:** `leads-to` (the support skeleton — grounding · derivation ·
  generalization · citation; authored as `grounded_in` ⟂ `leads_to`), `answers` (claim →
  question), `corroborate` / `contradict` (lateral stance). A **measurement** Method is a
  *floor* where grounding bottoms out; a *model* is a Method that layers on measurements.
- **Everything else is emergent — no node fields:** open/answered, original/borrowed,
  grounded/plausible, evidence balance (CONCEPT §13). Don't author `evidence`/`status`/`role`.
- **Two tiers, by file presence:** *curated* iff `curated/<citekey>.yaml` exists; else a
  **stub** — an un-sliced container in `stubs.yaml`. The set of stubs *is* the frontier; an
  edge targets the container `P` until curation slices it (the wildcard sharpens).
- **Generalize, don't merge:** never equate two claims; co-parent them under a broader
  `claims/` node via `leads_to` (≥2 children). Paper-specific phrasing and quotes survive.
- **Two axes, kept apart:** the **claim ladder** (`leads_to` between `claims/` nodes) answers
  *what is known*; the **topic axis** (`topics/` — keyword containers over paper `tags`)
  answers *what papers do I have on X*. A statement that can be **false** is a claim; a
  heading you cannot disagree with is a topic. Topics are never edge targets, and nothing in
  the graph derives from them (SCHEMA §9).
- **A third axis — purpose:** a **collection** (`collections/`) answers *which papers did I
  gather for Y* — a peer review, a grant, a talk. Time-bound (dated), membership **authored on
  the collection** as a citekey list (curated or stub), never on the paper — the mirror image of
  a topic, whose membership is derived from tags. Never use a tag for purpose: tags say what a
  paper is *about* and stay true. Not graph, never an edge target (SCHEMA §10).
- **One extension:** the **programme graph** models what is *proposed* rather than what is
  known — two extra kinds (**Test · Capability**), two extra edges (`discriminates` ·
  `enabled_by`), the **aim** as container (`programme/aims/`), the `@aim` ref sigil, and a
  pure-ordering **narrative** layer (`programme/narrative/`) that linearizes aims into a
  grant's sections, carrying no edges and deriving nothing.

## Conventions this repo enforces

- **citekey = `<Family><Year><Venue>`**, CamelCase, e.g. `Chen2021Sys`. This one string
  names the PDF, its full-text `.md`, the `curated/<key>.yaml` file, **and** the
  `stubs.yaml` key. Venue is the ISO-4 journal abbreviation (+ an override map for brand
  names like `eLife`).
- **Authors** carry two orthogonal axes: `position` (`first | middle | last`, an authorship
  *tier* — multiple `first`s = co-first/equal-contribution) and an independent
  `corresponding: true` flag. List order = byline order.
- **Source of truth is git-tracked YAML.** The SQLite `graph.db` is a disposable build
  artifact (gitignored). **Curated PDFs and their `.md` full-text live in `pdfs/`
  inside the data repo** (`pdf_dir` in `config.toml`), committed one-per-paper.
  Uncurated/staging PDFs live outside git in `~/Literature/`.

## Tools

Every command has `--help`; this section is the *invariant* each one carries, not its
manual. Viewer behaviour is specified in [docs/](docs/) — see the design index below.

**Getting papers in**

- **`lit ingest <pdf>`** — writes the bibliographic skeleton: `curated/<citekey>.yaml`
  (metadata + authors), one deduped `stubs.yaml` entry per citation (DOI-anchored via
  OpenAlex), and an AI-parsable `<citekey>.md` full text beside the renamed PDF.
  **Non-interactive, and it does *not* extract slices** — that is curation (CURATION.md).
  `--dry-run` previews. The `abstract` comes from OpenAlex/Crossref, else from the paper's
  own full text (Springer Nature and Elsevier deposit none, so it is null for most of the
  Nature family and all of Cell Press). **It never guesses**: an unanchored abstract is
  left missing and said so, because a wrong abstract is worse than none
  (`fulltext.extract_abstract`).
- **`lit abstracts`** / **`lit enrich`** — backfills for papers already on disk: abstracts
  onto curated papers from their stored `.md` (no network), authors + journal onto stubs
  from OpenAlex. Both only fill gaps, both have `--dry-run`. Run once, review the diff,
  commit.

**Curating**

- **`lit preview <citekey>`** / **`--scratch <file>`** — render one paper's local subgraph
  in isolation, through the viewer `lit build` ships, so it cannot drift. Fed a scratch
  YAML it renders **a proposition before it is tokenized** — the curation loop's "show it
  as it'll look" step — and flags non-verbatim quotes at proposition time. Also renders an
  **aim** (`lit preview '@<slug>'`), so the same loop works on proposed work.
- **`lit locate`** — resolve every curated quote's place in its PDF (full-coverage
  word-geometry match) and store it as `quote_loc`. Derived, never hand-authored; additive,
  never affects graph structure. `--force` re-resolves, `--dry-run` reports.

**Organizing**

- **`lit tag <citekey> [tags…]`** — add / remove / list a paper's `tags`: free-form curator
  labels, a container filter axis like `type` (SCHEMA §4) — no evidential weight,
  curated-only. Round-trips the one YAML file, comments intact. `--suggest` proposes tags
  from the author-keyword line and **writes nothing**, so the curator gates what lands.
- **`lit topics`** — report the topic axis (SCHEMA §9). **`--orphans`** is the one that
  matters: unfiled tags, dead keywords and stranded papers — the three signals that stop
  the layer rotting behind the tagging. `--strict` exits non-zero for CI. Run it after a
  tagging session.
- **`lit map`** — read back the broad layer and what hangs on it: the ladder with papers and
  slices beneath each node (`lit map`), one node's papers and contradictions (`<slug>`), one
  paper's reach (`<Citekey>`, `<Citekey>:<id>`), the curated papers off the map (`--off`), and
  a phrase finder (`--find`); `--json`, `--tag`, `--topic` on all. **One definition carries
  every count: a slice is on the map iff it reaches a broad node by `leads_to` — through any
  same-paper ladder — or, for a claim, by `answers` naming a broad question.** A claim that
  answers a paper question gathered under a broad one is listed, not counted. Read-only,
  derived from the loaded graph alone (no PDF or quote checks), so it runs in seconds.
- **`lit collection`** — `new "<title>"` · `add <slug> <citekey|doi>…` · `remove` · `list` ·
  `show` (SCHEMA §10). **`add` by DOI works for a paper not yet in the library**: it mints the
  `stubs.yaml` entry from OpenAlex/Crossref (ingest's citekey rules and merge), then adds it.
  The build fails on a citekey a collection lists but the library lacks.
- **`lit programme`** — report the programme graph's emergent state: **load-bearing
  assumptions ranked by blast radius** (dependents, no test aimed at them, no grounding —
  what a hostile reviewer finds first), plus speculation, tests at risk from an unevidenced
  capability, aspirational capabilities, open questions, orphans. `--strict` for CI.
  Terminal only — every payoff lands without the viewer.

**The owner's desk** — `validated` is the owner's; **never write it, never run `lit validate`.**

- **`lit desk`** — list the desk: the curated papers whose curation moved past what the owner
  validated, as **new** (`validated` absent) and **changed** (validated N → pass M), newest
  curation record first; `--collection` / `--topic` / `--tag`, `--json`. **A paper is on the desk
  iff `validated` is absent or differs from `pass` (absent `pass` = 0) — derived, never stored**,
  so an agent rewriting a paper at the same pass leaves it off and only a change of `pass` puts it
  back. Read-only, from the loaded graph alone, like `lit map`. Agents may run it.
- **`lit validate <citekey>… [--pass N]`** — the owner records the pass they have validated: the
  paper's current pass, or N (0–4); `--collection <slug>` / `--all` validate everything on the desk
  in that scope (each at its own pass), `--dry-run` previews. **Only the owner writes `validated`
  — through this command or the viewer's Validate action (serve's `POST /validate`).** `lit
  ingest` never writes it, curation never touches it (CURATION.md). One line under `pass:`, every
  other byte of the file kept. A `validated` above `pass` is legal and a `lit build` warning.

**Viewing**

- **`lit build`** — the static, shareable artifact: reads the YAML, computes emergent
  properties (SCHEMA §7), emits a self-contained `dist/index.html` + `graph.json`. **The
  build is the validator** — a dangling ref or a curated/stub citekey collision fails it
  (SCHEMA §6). Client-side search, so it works offline.
- **`lit serve`** — the same viewer over loopback: the graph rebuilds from the YAML on every
  refresh, so a curator's edit shows up on reload, and a broken edit returns the validation
  error without killing the server. Adds what a static file cannot — the docked PDF viewer,
  the Validate action (the desk), the aims pill, live stub abstracts. Anything serve-only stays hidden
  in `lit build`. The in-browser curation cockpit (a card + paper + terminal window per paper,
  driven by a focus wire and `POST /term`) was retired 2026-08-27: curation now runs as a
  conventional coding-agent session against the data repo, following CURATION.md, with the
  human reviewing the diff — `lit serve` is back to being purely the graph viewer.

### Design index — where viewer behaviour is actually specified

Do not re-derive these from the code, and do not re-litigate them without reading the
reversal each one records.

| Doc | Specifies |
|---|---|
| [2026-08-05-edge-visibility.md](docs/2026-08-05-edge-visibility.md) | the four edge states (*lit · scaffolding · ghost · not drawn*) decided in one place, `edgeVis`; why nothing in it reads a gesture; pin release (`pinLive`, `clear arrows`); §7 the `quiet arrows` mode — the resting board dark, pins and hover kept |
| [2026-08-19-card-folds.md](docs/2026-08-19-card-folds.md) | what an OPEN card shows: the paper's identity, plus three folds asked for one click at a time — abstract, slice graph, and cited cards that arrive collapsed. Records the reversal of "open each source on the exact cited finding" |
| [2026-08-03-topics-and-claim-altitudes.md](docs/2026-08-03-topics-and-claim-altitudes.md) | the synthesis band as **containment**, one box per ladder root. §6 and §6.1 record two reversals — hiding-until-clicked, and altitude columns. **Length is not the defect; unstructured length is.** |
| [2026-08-03-the-walk-design.md](docs/2026-08-03-the-walk-design.md) | the walk: one focus, one relation, no drawn edges. `contains` is a **roster**, the only complete view, and it flags `unwired` slices |
| [2026-07-09-cockpit-redesign-in-progress-zone.md](docs/2026-07-09-cockpit-redesign-in-progress-zone.md) §2 | the browse view's collapsible/detachable docked PDF pane — still current. (§§3–4 of the same doc, and [2026-07-28-curation-windows.md](docs/2026-07-28-curation-windows.md) entirely, specify the curation cockpit, retired 2026-08-27 — see CURATION.md) |
| [2026-11-11-desk.md](docs/2026-11-11-desk.md) | the desk: `validated` beside `pass`, the desk derived from the two, the validated pass as every paper's status (app, board, library sort, landing rank), Validate and its lower levels, offline/static behaviour; what the reading list it replaced was |
| [2026-10-29-collections.md](docs/2026-10-29-collections.md) | collections (the purpose axis): why not a tag; found by title in search (board: a row above the papers, opened uncapped; app: its own screen); the Topics tab leads with them; the library rail's collection facet |
| [2026-08-02-programme-graph-design.md](docs/2026-08-02-programme-graph-design.md) | the programme graph and its narrative layer |
| [2026-08-25-claim-map-design.md](docs/2026-08-25-claim-map-design.md) | the claim map (`prototypes/claim-map/`): the 44 broad claims on one page, x = median year of their papers, y = ladder altitude. §1 records the rejected similarity-embedding proposal, §3 the measurement that rules out a topic band as an axis |
| [2026-08-05-additive-graph-views.md](docs/2026-08-05-additive-graph-views.md) · [2026-07-19-tags-and-search-design.md](docs/2026-07-19-tags-and-search-design.md) · [2026-06-25-visualization-design.md](docs/2026-06-25-visualization-design.md) | view composition, tags/search, and the original (still unbuilt) recursive container view |

### Not yet in a design doc

Two viewer behaviours are specified nowhere but here. When either gets a doc, cut it from
this file and add a row above.

**The programme lane.** Aims and the narrative that orders them (`programme/narrative/`)
ride in `/graph.json` in their own fixed **"programme" lane**, left of the landing column
(`viewer/js/18-programme.js`). The landing column's own pass/year sort (`order`) is built
from papers alone and stays untouched. A repo with no `programme/` tree shows no lane and
no **"aims · N"** pill (which indexes `programme/aims/` via `/aims.json`, carrying each
aim's assumption and at-risk-test counts; a row opens that aim's card at
`/preview.html?key=@<slug>`).

**Board zoom.** It is a *camera* — one
`scale()` on `#stage`, so nothing re-wraps and a learned picture survives the move —
distinct from the width slider, which re-lays-out card text. The track is **log-spaced over
1/3 … 3** so 100% sits mid-track and half sits as far from it as double. Zoomed out the
board stops being readable and becomes a **map**. `redraw()` is the one place that converts
glass pixels back to stage pixels (÷ BZ); this is a transform, not CSS `zoom`, so every
scroll-anchoring site is untouched.

## Curating a paper

When the human asks to **curate a paper**, **read [CURATION.md](CURATION.md) first** and
follow its protocol. There are **two modes**, and which one you are in is set by whether the
human is present. In both, the human is the gate: you propose, they accept / edit / reject, and
nothing is curated until they commit it.

**`validated` is the owner's; never write it.** A curated file may carry `validated: N` under
`pass:` — the pass the owner has validated, which drives their desk. Curation raises `pass` and
leaves that line exactly as found; never add, change or remove it, and never run `lit validate`.

**Interactive** (human present, usually with `lit serve` and the card open) — never a one-shot
file dump:

- Work **one pass at a time** (the four passes in CURATION.md).
- Each pass is a loop: **explain your reading** of the paper at that pass's granularity in
  prose → **discuss with the human until you agree** → *only then* **tokenize** (write the
  agreed nodes into `curated/<citekey>.yaml`).
- **Realign after every pass** before starting the next. Never tokenize ahead of agreement.

**Batch** (you were dispatched with one paper and a target pass, human not present) — climb to
that target in a single run, writing into `curated/<citekey>.yaml`, and the human reviews the
finished proposition as a git diff:

- Climb the rungs **in order** anyway. Each pass refines the slices the previous one wrote; do
  not skip to the target.
- **Report a verdict, not just a file.** Say what the paper does and does not show on the
  specific question you were dispatched to settle.
- **A finding that undermines the claim you were asked to support is the most valuable thing
  you can return.** Do not stretch, soften, or select slices to make a hypothesis look
  supported. Write the gap into the claim text and flag it in your report.
- Touch only `curated/<citekey>.yaml`, and in it never the `validated:` line. Sibling agents may
  be running; do not run `lit build`.

## Working with this project

- Propose, don't impose. Surface a paper's local subgraph for accept/edit/reject; don't
  auto-commit curated judgments.
- Metadata fetches use the OpenAlex/Crossref **polite pool** — always send the `mailto`
  from `config.toml`.
- Dev: Python. Tests are **offline & deterministic** (recorded OpenAlex/Crossref fixtures +
  saved PDF-text snippets) — no live network in the test suite.
- **When a viewer decision gets made, it goes in a `docs/` design doc, not here.** This file
  is orientation; `docs/` is the record. That boundary is why this section is short.
