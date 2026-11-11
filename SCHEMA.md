# SCHEMA: the on-disk data model

**Status:** v2, the lean slice model. **Date:** 2026-06-25. **Last revised:** 2026-10-29.
Companion to [CONCEPT.md](CONCEPT.md).

CONCEPT converged the graph to one primitive, the slice, in a container, the paper, wired by
three edges: `leads-to`, `answers`, and `corroborate` / `contradict`. Everything else is
emergent. This document fixes the files: how that graph is written to disk so that it stays
diffable, hand-editable and machine-buildable. The philosophy is the one the experiment
database already uses. A diffable text dump is the source of truth in git, and the binary
database is a gitignored build artifact that a generator produces from it.

```
YAML source of truth (git)  ──generator──▶  graph.db (SQLite, gitignored)  ──▶  catalog views
        ▲ hand-curated, one paper at a time
PDFs live outside git, in an external dir named by config.
```

No code is required to define the model. This spec plus the worked [`example/`](example/)
tree is the model, and a parser or generator conforms to it.

Section 5 is the table that maps CONCEPT's three edge names onto the YAML field names used
everywhere below. Section 11 records the choices this schema replaced.

---

## 1. The cardinal rule: one file per curated paper

A node's home is chosen so that the unit of storage equals the unit of curation. CONCEPT
section 5 says that curating one paper means producing its local subgraph, so one session
touches one file, which gives one clean commit and one readable diff.

| Node | Home | Rationale |
|---|---|---|
| **Curated paper** (the container `P`) | `curated/<citekey>.yaml`: metadata, plus its `claims`, `questions` and `methods` slices, plus their edges | the local subgraph |
| **Broad claim** | `claims/<slug>.yaml`, thin | a `leads_to` target shared across papers; minted only when at least two slices share it (CONCEPT section 10.2) |
| **Broad question** | `questions/<slug>.yaml`, thin | shared `leads_to` target for questions |
| **Broad method** | `methods/<slug>.yaml`, thin | shared technique; minted only when at least two papers share it |
| **Topic** | `topics/<slug>.yaml` | a container of keywords, grouping the `tags` vocabulary so papers stay findable as it grows. Not a slice and not in the graph (section 9) |
| **Collection** | `collections/<slug>.yaml` | papers gathered for a purpose (a review, a grant, a talk), listed by citekey. Not a slice and not in the graph (section 10) |
| **Stub** (uncurated paper) | one entry in `stubs.yaml` | an un-sliced container: bibliographic data only, machine-fetched, holding only the wildcard |
| **Author** | emergent, derived from each paper's `authors:` | no hand-maintained author files |

Two things fall out of this for free.

Tier is encoded by file presence. A paper is curated if and only if `curated/<citekey>.yaml`
exists; otherwise it is a stub, an entry in `stubs.yaml`. The frontier is the set of stubs,
and there is no `tier:` field. Promotion means moving the `stubs.yaml` entry into a new
`curated/` file and slicing it. Edges that pointed at the container `P` then sharpen to its
slices (CONCEPT section 2). This breadth tier stays emergent. The orthogonal maturity tier,
how far curation ran on a scale of 0 to 4, is the one thing recorded explicitly, as `pass:`
on the curated paper (section 4, CONCEPT section 10.1).

A slice's home in a container needs no syntax. A `claims`, `questions` or `methods` entry
inside a paper file is that paper containing it. It is the only implicit edge.

---

## 2. File layout

```
<root>/
  curated/
    Chen2021Sys.yaml         # one curated paper = its whole local subgraph
    ...
  claims/      <slug>.yaml   # thin broad claims (≥2 children)
  questions/   <slug>.yaml   # thin broad questions
  methods/     <slug>.yaml   # thin broad methods (≥2 papers)
  topics/      <slug>.yaml   # keyword containers — a paper-discovery axis, NOT graph (§9)
  collections/ <slug>.yaml   # papers gathered for a purpose — NOT graph either (§10)
  programme/   aims/<slug>.yaml · narrative/<slug>.yaml
                             # the proposed-work extension — separate spec, see below
  stubs.yaml                 # { citekey: bib-metadata } — un-sliced containers
  config.toml                # deployment-local (private): external PDF dir, etc.
```

The `programme/` tree is specified separately, in
[docs/2026-08-02-programme-graph-design.md](docs/2026-08-02-programme-graph-design.md). It
extends this schema with two node kinds, capability and test, and the aim as a container,
for modelling proposed work rather than published work. Everything else in this document
covers the literature graph proper.

In the public repo this tree lives under [`example/`](example/). In a private data repo it
lives at the deployment's root, for example `literature/`, with the real PDF path in
`config.toml`.

---

## 3. Identifiers

| Id | Form | Source |
|---|---|---|
| **citekey** | `<Family><Year><Venue>` in CamelCase, e.g. `Chen2021Sys`, with an `a`/`b`/`c` suffix for same-DOI collisions. `Venue` is the ISO-4 abbreviation, with an override map for brand names like `eLife`. Also names the PDF and its `.md` | filename stem of a `curated/` file, or a key in `stubs.yaml` |
| **slice (local)** | `c1`, `c2` … / `b1`, `b2` … / `q1`, `q2` … / `oq1`, `oq2` … / `m1`, `m2` …, unique within its paper file. The prefixes are explained below | hand-assigned |
| **slice (global)** | `<citekey>:<local>`, e.g. `Chen2021Sys:c1` | composed by the generator |
| **broad claim / question / method** | kebab-case `<slug>`, globally unique | filename stem in `claims/`, `questions/`, `methods/` |

### Local slice ids

A local id has a prefix and a number. The prefix records the curator's reading of what the
paper does with the slice:

| prefix | the slice is |
|---|---|
| `c` | a claim the paper makes as its own |
| `b` | a borrowed claim: a restatement off a citation wall |
| `q` | a question the paper sets out to answer |
| `oq` | an open question the paper raises and leaves |
| `m` | a method |

Each prefix has its own counter, numbered in reading order when the file is written, so the
sequences interleave down the file: `c1 b1 c2 c3 b2`. Ids are stable handles, because other
files weld to `<citekey>:<id>`. A slice reclassified later swaps its prefix and keeps its
number, so `c4` becomes `b4`, leaving a gap in the `c` sequence rather than renumbering a
file the library already points into.

The prefix does not replace the emergent properties of section 7. Those stay computed from
the edges and are what the generator works with. The generator never reads the prefix. Kind
coherence, rule 6 of section 6, resolves the target and asks its kind, so `b3` and `c3`
validate identically. Keeping both an authored prefix and an emergent property is
deliberate:

- In the ordinary case they agree, and the prefix makes the agreement visible in the diff.
  The unit a human accepts or rejects is a YAML hunk, and `b7` says "restatement, judge it as
  one" without tracing every ref in `grounded_in` first.
- Where they disagree, that is a finding, not an error. A `b` claim whose `grounded_in`
  reaches no container means the wall was never mapped. A `c` claim that computes as
  borrowed means the curator read a result as the paper's own that its own citations say is
  not.
- For questions they are expected to diverge, permanently. `oq` records what this paper left
  open at publication; the emergent `open` flag records whether the library has since
  answered it. When a later paper's claim `answers` it, the question closes and keeps its
  `oq` id. The id is history, the flag is state. The viewer's "open questions" bucket reads
  the flag, not the prefix.

### Ref syntax

Every edge target is one string, and its form says what it points at:

| form | refers to | in an edge, means |
|---|---|---|
| `m3`, `c2`, `b5`, `q1`, `oq2` | a local slice in the same file | the precise slice |
| `throughput-scales-with-batching` | a broad `claims/`, `questions/` or `methods/` slug | the shared node |
| `West2015Sigmod` | a container, curated or stub | the wildcard: "some slice in here, not yet resolved" (CONCEPT section 2) |
| `West2015Sigmod:c3` | a sharpened cross-paper slice | the precise slice, once that paper is curated |

The generator resolves every ref into an edge and fails the build on a dangling reference
(section 6).

---

## 4. The slice and its edges

### Curated paper: `curated/<citekey>.yaml`

| Field | Req | Type | Notes |
|---|---|---|---|
| `title` | ✔ | str | |
| `type` | ✔ | enum | `original \| review \| methods \| perspective \| commentary`. A filter only, with no evidential weight (CONCEPT section 6) |
| `year` | ✔ | int | |
| `pass` | – | int | curation depth, `0`–`4`, described below. Absent on a stub |
| `doi` / `url` / `pdf` | – | str | `pdf` defaults to `<citekey>.pdf` under the config PDF dir |
| `authors` | ✔ | list | each `{name, position?, corresponding?}`; list order is byline order. `position` is one of `first \| middle \| last`, default `middle`. It is an authorship tier, so several `first`s mean co-first. `corresponding: true` is independent of position, any number |
| `note` | – | str | free-text curator orientation, for example the experimental setup. Not a graph element |
| `abstract` | – | str | the verbatim abstract, written by `lit ingest` from OpenAlex or Crossref, else read out of the paper's own full text. Most Springer Nature and Elsevier papers have no abstract in the open metadata at all. Shown in the viewer tooltip; not a graph element. `lit abstracts` backfills it for papers ingested before that fallback existed |
| `tags` | – | list[str] | free-form curator labels, described below. Curated-only; a stub has none. Not a graph element |
| `claims` / `questions` / `methods` | – | list | the paper's slices, described below. Absent or empty is valid, since partial curation is normal |

`pass` is the curation depth of the artifact. It is a single staircase where the number is
both how far the paper was read and how mature the card is (CURATION.md): 0 ingested, with
metadata and extracted full text and no slices; 1 abstract, where every slice on the card is
supported by the abstract; 2 introduction and discussion, adding borrowed claims, graph
connections and open questions; 3 results, with claims sharpened and welded to phrases
describing the data; 4 methods, read precisely with their citations traced and linked, the
full sweep. It is the one authored process-state field, because how far curation went
cannot be reconstructed from the slices (CONCEPT section 10.1). The breadth tier stays
emergent via file presence (section 1).

`tags` is a container filter axis for organizing and finding papers, the same category as
`type`: a cheap filter with no evidential weight (CONCEPT section 6). Nothing in the graph
derives from it. It never feeds grounding, strength or any emergent property, and it lives
only on the container, never on a slice. It is authored by hand or via `lit tag`, and
searched by the viewer.

**Claim** (item of `claims`):

| Field | Req | Type | Notes |
|---|---|---|---|
| `id` | ✔ | str | `c1`…, unique within the file |
| `text` | ✔ | str | the natural-language claim, what you would write in an introduction |
| `quote` | ✔ | str | supporting text from the paper's `.md`. Normally a verbatim substring; non-contiguous passages may be joined with `[...]` but are flagged for curator review |
| `quote_loc` | – | map | derived PDF anchor for the quote: `{page: int (0-based), rects: [[x0,y0,x1,y1], …]}`, each rect a page fraction from 0 to 1, one per wrapped line. Written by `lit locate`, never hand-authored; optional and additive. See *Quote windows* in section 6 |
| `grounded_in` | – | ref list | `leads-to` edges into this claim: what it rests on. The list is heterogeneous, and the target's kind is the meaning. A method ref is an empirical floor; a claim ref is a premise or derivation; a container or citation ref makes this a borrowed, restated claim (CONCEPT section 6.1) |
| `leads_to` | – | slug list | `leads-to` edges out of this claim: the broader claim or claims it generalizes into |
| `corroborates` / `contradicts` | – | ref list | lateral stance toward an independently grounded claim or paper. The only signed edges (CONCEPT section 4) |
| `answers` | – | ref list | the question or questions this claim answers |
| `floor` | – | `true` | declares this claim an axiom, a self-grounding formal floor. The only deliberate marker in the model (CONCEPT section 3) |
| `note` | – | str | free-text curator judgement. Not quote-bound and never an edge |

**Question** (item of `questions`):

| Field | Req | Type | Notes |
|---|---|---|---|
| `id` | ✔ | str | `q1`… or `oq1`… |
| `text` | ✔ | str | interrogative, with no stance; an interrogative asserts nothing |
| `quote` | – | str | the paper sentence that raises the question, the same integrity weld a claim carries, so an open question is verifiable in the source and findable in the PDF. Optional, since a purely synthesized question may lack a verbatim anchor, but expected for open questions, which are raised by a specific "future work" or "remains unclear" sentence. Verbatim substring by default; `[...]`-joined passages are flagged for review. The `text` is the curator's interrogative rephrasing and the `quote` is the verbatim declarative source, exactly as a claim's `text` rephrases its `quote` |
| `quote_loc` | – | map | derived PDF anchor for the quote, written by `lit locate`, identical to a claim's (section 6) |
| `leads_to` | – | slug list | the broader question or questions it generalizes into |

Open versus answered is emergent. A question is answered if and only if some claim
`answers` it (section 7), and there is no `status` field. Because openness can flip when a
later paper's claim answers it, the `quote` weld is a kind-level affordance, never gated on
open or answered.

**Method** (item of `methods`):

| Field | Req | Type | Notes |
|---|---|---|---|
| `id` | ✔ | str | `m1`… |
| `text` | ✔ | str | the technique, e.g. "microbenchmark harness" |
| `grounded_in` | – | ref list | what this method rests on: the paper or papers that introduced it, and/or other methods it layers on, as when a model is `grounded_in` the measurements it consumes (CONCEPT section 7). A measurement method grounding only in its source paper is a floor |
| `leads_to` | – | slug list | a broader method it generalizes into, the method ladder: microbenchmark, then performance benchmarking |
| `quote` | – | str | a methods-section sentence. Optional, since methods prose is boilerplate. Shortening with `[...]` is allowed but flagged for curator review |

### Thin broad slice: `claims/<slug>.yaml`, `questions/<slug>.yaml`, `methods/<slug>.yaml`

Thin by design. It is a `leads_to` target, and its incoming edges live on the children and
are inverted by the generator. The "5 support, 2 contradict" meter of CONCEPT section 9 is
a count, never bookkept here.

| Field | Req | Type | Notes |
|---|---|---|---|
| `title` | – | str | an at-a-glance name of a few words, read in one beat, such as `"Traction force microscopy"`. The viewer renders it as the node's heading and demotes `text` to a gloss beneath. Absent, the node renders `text` alone. A display affordance, not a graph element; nothing resolves or derives from it |
| `text` | ✔ | str | the broad statement, question, or technique name |
| `leads_to` | – | slug list | generalizes further up the ladder: a broad claim into a broader one, microbenchmark into performance benchmarking |

### Stub: entry in `stubs.yaml`, keyed by citekey

```yaml
West2015Sigmod:
  title: "Unbounded throughput scaling in partitioned pipelines"
  authors: [Dana West, Omar Farooq]   # optional; byline order, display names (no role resolution)
  journal: "SIGMOD Record"            # optional; venue display name
  year: 2015
  doi: 10.0000/synth.west2015
  type: original                      # optional
```

A stub is an un-sliced container: bibliographic data only, reached by some slice's
`grounded_in`, `corroborates` or `contradicts`. It carries no slices, since it has not been
read. `authors` and `journal` are the metadata OpenAlex already returns for every reference.
`lit ingest` writes them and `lit enrich` backfills them onto older stubs. Both drive the
viewer's hover card: title, authors, journal, year. Unlike a curated paper's authors, stub
authors are plain names with no `position` or `corresponding`, since there is no PDF to
resolve roles from. A stub's abstract is never stored, because it would balloon the frontier
file; `lit serve` fetches it live from OpenAlex on hover instead.

### Author: emergent

Not a file. The generator collects distinct `name`s across all `authors:` lists and attaches
their `position` per paper, yielding the author nodes and `Author → Paper {position}`
edges. Nothing is hand-authored.

---

## 5. Edge encoding: one authoring site each

This table is the mapping between CONCEPT's edge names and the YAML fields.

| CONCEPT section 4 edge | Authored on | As | Direction |
|---|---|---|---|
| **`leads-to`** (grounding / derivation / generalization / citation) | the curated slice | `grounded_in` (arrow in) or `leads_to` (arrow out) | ground → derived |
| **`answers`** | the answering claim | `answers` | claim → question |
| **`corroborate` / `contradict`** | the asserting claim | `corroborates` / `contradicts` | lateral, signed |
| `Author → Paper` (position) | the paper's `authors[]` | `{name, position}` | — |

`leads-to` is one edge type. `grounded_in` and `leads_to` are inverse views of it, so every
edge is authored exactly once, on the curated slice, and never by editing a shared `claims/`
file or an upstream stub. Downward edges, to floors, premises and citations, are authored
as `grounded_in`. Upward edges, to broader claims, are authored as `leads_to`.

---

## 6. Validation rules

The generator enforces these and the build fails otherwise.

1. **No dangling refs.** Every `grounded_in`, `leads_to`, `corroborates`, `contradicts` and
   `answers` ref resolves to a local slice id, a `claims/`, `questions/` or `methods/` slug,
   a container (a `curated/` file or a `stubs.yaml` key), or a `<citekey>:<id>` slice.
2. **Local ids are unique** within each paper file, across all prefixes.
3. **Slugs and citekeys are globally unique.** A citekey is never both curated and a stub.
4. **Quote integrity.** Every claim `quote`, and every question or method `quote` when
   present, must be grounded in the paper's `.md` full text. Verbatim substrings are the
   default. A quote containing `[...]` is accepted when non-contiguous passages are
   intentionally shortened, but only if every segment is itself verbatim and the segments
   occur in the full text in the order written (each is searched after the previous one's
   match). A segment that is not is flagged exactly like a non-verbatim quote, by number. A
   join that passes is still flagged for curator review, with the characters cut between its
   segments, so a stitch across distant sections stands out. It is never silently treated as
   verbatim. `lit preview --scratch` runs the same check at proposition time.
5. **`leads-to` is acyclic.** The support DAG is many-to-many with no cycles.
6. **Kind coherence.** `leads_to` targets a same-kind broad slug: claim to claim, question
   to question, method to method. `answers` targets a question. `corroborates` and
   `contradicts` target a claim or a container. `floor: true` appears only on a claim.
7. **No emergent fields authored.** `status`, `evidence`, citation `role` and rollup
   `polarity` are not valid keys. They are derived (section 7), and their presence is an
   error. A paper's `tags` is not one of these: it is authored container metadata like
   `type`, and derives no graph property (section 4).
8. **Enums are valid.** `type` as listed in section 4; `position` in `first|middle|last`;
   `corresponding` either `true` or absent; `pass` in `0|1|2|3|4` and only on a curated
   paper.

### Quote windows: `quote_loc`

A `quote` may carry an optional `quote_loc`, a page plus fractional rects, one per wrapped
line, welding it to its place in the PDF. It is derived, not authored. `lit locate` resolves
it by word-geometry matching covering the whole quote, across line breaks and hyphenation,
and writes it into the YAML. Re-run it with `--force` any time the matcher improves. It is
additive and never affects graph structure or emergent properties. `lit build` reads the
words whose centre lies inside each stored rect back out of the PDF and flags a `quote_loc`
whose text does not match its quote (a stale or mis-parented location). It only drives the
`lit serve` viewer's PDF quote windows: a stored location renders instantly, and a quote
without one is resolved live. The static artifact from `lit build` ignores it.

---

## 7. Emergent properties

The generator computes these. They are never authored.

| property | rule |
|---|---|
| **open vs answered** (question) | answered if and only if some claim `answers` it. Independent of the `oq` prefix, deliberately: the prefix is what the paper left open, this flag is what the library still has open (section 3) |
| **original vs borrowed** (claim) | borrowed if and only if its `grounded_in` reaches a container or citation, i.e. crosses papers, rather than a floor. It is a restatement (CONCEPT section 6.1). The `b` prefix is the curator's reading of the same thing, and a disagreement between them is a finding to chase, not a build error (section 3) |
| **grounded vs plausible** (claim) | grounded if and only if its `leads-to` chain reaches a floor, a measurement method or an axiom; otherwise it dangles on reasoning |
| **evidence balance** (claim) | count incoming `corroborates` against `contradicts` |
| **floor** (slice) | a slice whose own grounding bottoms out: a measurement method grounding only in its source paper, or a `floor: true` axiom. Models are methods that are not floors, because they are `grounded_in` the methods below them (CONCEPT section 7) |

---

## 8. Broader-question nesting

CONCEPT section 12 records the decision: broad questions get their own thin `questions/`
files, and a claim's `answers` is the only bridge from a question to a claim. This is the
minimal stance and it is retractable. If it is later reversed to anchoring the question DAG
onto claim altitudes, `questions/` collapses into claim altitudes with no change to the
paper files.

---

## 9. Topics: the keyword axis, not the graph

Design: [docs/2026-08-03-topics-and-claim-altitudes.md](docs/2026-08-03-topics-and-claim-altitudes.md).

A topic groups keywords, and keywords are the paper `tags` of section 4. It exists so that a
growing `tags` vocabulary stays navigable. It answers "what papers do I have on X", never
"what is known". The claim ladder, `leads_to` between `claims/` nodes, is the axis for the
latter, and the two never touch.

A topic is not a claim and must never become one. It asserts nothing, so every emergent
property of the model, grounded versus plausible, the corroborate and contradict meter, the
walk to a floor, is undefined on it. The rule that keeps this safe:

> A statement that can be false is a claim and goes in `claims/`.
> A heading you cannot disagree with is a topic and goes in `topics/`.

| Field | Req | Type | Notes |
|---|---|---|---|
| `title` | ✔ | str | at-a-glance name, e.g. `"Cancer mechanics"` |
| `note` | – | str | free-text curator gloss on what the topic is for |
| `keywords` | ✔ | list[str] | tag strings this topic contains. May be empty on a pure grouping node whose keywords all live below it. Matched against paper `tags` case-insensitively |
| `broader` | – | slug list | the topic or topics this one sits under. A separate DAG, not `leads-to` |

`broader` is a fourth edge only in the sense that it is not one of the three. It is confined
to `topics/ → topics/`, never resolves a slice ref, never enters the support skeleton, and no
emergent property reads it. The three-edge core of CONCEPT section 4 is untouched.

### Membership is derived, never authored

A paper is in a topic if and only if any of its `tags` appears in that topic's `keywords`, or
in the keywords of any topic beneath it through `broader`. Nothing is written on the paper.
`tags` stays exactly the free-form container field of section 4, and a paper never names a
topic. This is what keeps topics from becoming hand-authored emergent state, the thing the
tags design refused when it banned slice-level tags.

Keywords are non-exclusive. The same keyword may belong to several topics, as `glioblastoma`
is both cancer and nervous-system, and a topic may have several `broader` parents. The topic
axis is deliberately a DAG, not a tree.

### Validation

1. **`broader` resolves** to an existing `topics/` slug, and the `broader` graph is acyclic.
2. **Topic slugs are globally unique** and distinct from any `claims/`, `questions/` or
   `methods/` slug. A topic is never an edge target, and the disjointness keeps it that way.
3. **Warn, don't fail,** on a dead keyword (in a topic, on no paper) and on an unfiled tag
   (on a paper, in no topic). Both are curation signals, not errors. The unfiled-tag report is
   what stops the topic layer silently rotting as the tag vocabulary grows.
   `lit topics --orphans` surfaces them, along with stranded papers, which are curated but reached by no
   topic. `--strict` turns them into a non-zero exit for CI.
4. **Topics are absent from the slice graph entirely.** A topic slug in any `grounded_in`,
   `leads_to`, `answers`, `corroborates` or `contradicts` is a dangling ref under rule 1 of
   section 6 and fails the build.

### Inserting a layer later

A topic's depth is emergent from `broader`. There is no `level` field, exactly as there is
none for claim altitude. So a new tier is: add the file, then add one `broader` line to each
topic that should sit under it. Nothing renumbers and no consumer learns a new concept.

---

## 10. Collections: the purpose axis, not the graph

A collection records **why papers were gathered**: the related work for a peer review, the
citations behind a grant, the papers a talk rests on. It is the third way into the library, and
it answers a question neither of the other two can:

| Axis | Answers | Stays true |
|---|---|---|
| the claim ladder (`claims/`, section 4) | *what is known* | until a paper contradicts it |
| the topic axis (`topics/`, section 9) | *what papers do I have on X* | as long as the papers do |
| a collection (`collections/`) | *which papers did I gather for Y, and why* | it is dated: the review gets submitted |

It is not a tag, and using `tags` for it is the misuse this section exists to prevent. A tag
describes what a paper is about and is read by the topic axis. "Batching review" says nothing
about any paper's subject; written as a tag it would sit on the paper long after the review was
sent, and surface in `lit topics --orphans` as an unfiled tag forever.

```yaml
title: "Batching review"           # required — what search matches
date: "2026-10-29"                   # optional, ISO
note: "Related work for refereeing a batching-latency manuscript."   # optional, free text
papers:                              # required (may be empty), citekeys in the order gathered
  - Chen2021Sys
  - West2015Sigmod                   # a stub is fine: a paywalled paper may only ever be one
```

| Field | Req | Type | Notes |
|---|---|---|---|
| `title` | ✔ | str | the name the viewer's search finds it by, e.g. `"Batching review"` |
| `date` | – | ISO date | when the collection is for, e.g. the review's due date. Display and ordering only (newest first) |
| `note` | – | str | free-text gloss on what the papers were gathered for. Not searched |
| `papers` | ✔ | citekey list | curated papers **or stubs**, in the order they were gathered |

### Membership is authored on the collection, never on the paper

The mirror image of a topic. A topic's membership is derived from paper `tags` and nothing is
written on the paper. A collection's membership is written on the collection, and still nothing
is written on the paper: a paper never names its collections. The viewer derives the inverse
("in collections") for display, and that is all. A paper may be in any number of collections.

`lit collection` maintains the file. `lit collection add <slug> <doi>` accepts a DOI that is not
yet in the library and mints a `stubs.yaml` entry for it first, from OpenAlex or Crossref, with
the same citekey rules and merge as `lit ingest`'s references (section 4). So the collection can
always name a key the build resolves.

### Validation

The build fails on:

1. **An unresolved citekey.** Every entry in `papers` is a `curated/` file or a `stubs.yaml`
   key. This is an error, not a warning like a dead topic keyword (section 9 rule 3), because
   the collection is the one place this membership is authored. A key that resolves nowhere is
   a dangling ref in the sense of rule 1 of section 6.
2. **A citekey listed twice** in one collection, and **a missing `title`**.
3. **A slug that is not kebab-case, or that also names** a `claims/`, `questions/`, `methods/`
   or `topics/` slug or a citekey. Collection slugs are disjoint from every name a ref can
   resolve to.
4. **A collection in the slice graph.** A collection slug in any `grounded_in`, `leads_to`,
   `answers`, `corroborates` or `contradicts` is a dangling ref under rule 1 of section 6, the
   same rule that keeps topics out (section 9 rule 4). No edge targets a collection and no
   emergent property reads one. Deleting `collections/` changes nothing in the graph.

---

## 11. History: what this schema replaced

- **A `tier:` field.** Replaced by file presence (section 1).
- **`status`, `evidence`, citation `role` and rollup `polarity` fields.** All emergent now
  (section 7) and rejected by rule 7 of section 6 if authored. CONCEPT section 14 records
  the model change behind this.
- **Question nesting left open.** CONCEPT section 12 once left undecided whether the question
  DAG stands alone or anchors onto claim altitudes. Section 8 records the resolution.
- **Slice-level tags.** Refused in the tags design
  ([docs/2026-07-19-tags-and-search-design.md](docs/2026-07-19-tags-and-search-design.md)),
  which is why `tags` lives only on the container and topics derive membership rather than
  papers naming topics (sections 4 and 9).
- **Purpose as a tag.** Grouping papers by why they were gathered (a review, a grant) was
  refused as a tag, because tags and the topics built on them describe what a paper is about
  and stay true. Collections took it over, authored on the collection (section 10).
