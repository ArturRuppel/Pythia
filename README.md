# Pythia

*(The project name; the repo, the `litgraph` package and the `lit` command keep
their original names.)*

A knowledge graph over the scientific literature. You read a paper, and the
claims, questions, and methods inside it become nodes in a graph: each one
welded to the exact sentence in the source that backs it. Granular,
paper-bound claims generalize upward toward broad ones, so the graph doubles as
a living, evidence-backed map of what is known on the topics you care about.

One constraint shapes everything: curation is the rate limiter. The tool
proposes; you accept, edit, or reject. A half-finished graph is a normal, valid
state, not a defect.

This repo is the general, reusable part: the model and the tooling. Your actual
library (real papers, real quotes) lives in a separate, private data repo, and
the PDFs live outside git entirely. Point the tool at your own data and
bootstrap your own graph.

## The model

One primitive, the **slice**, lives inside a container, the **paper**. A slice
is a single assertion welded to an exact `quote`. Slices come in three kinds:

- **Claim**: something the paper asserts.
- **Question**: something the paper asks.
- **Method**: how the paper measured or modeled something. Its quote is
  optional.

A paper *is* its slices, and slices are recursively sliceable: a broad claim can
hold finer ones. Three edges connect them:

- **leads-to**: the support skeleton: grounding, derivation, generalization,
  and citation.
- **answers**: a claim answers a question.
- **corroborate / contradict**: lateral stance between two slices.

Everything else is emergent from that structure, not written by hand: whether a
question is open or answered, whether a claim is original or borrowed, how the
evidence balances. You author the slices and the edges; the properties fall out.

Two tiers, decided by one fact on disk: whether a file exists.

- **Curated**: `curated/<citekey>.yaml` exists, so the paper has been sliced.
- **Stub**: it does not, so the paper is an un-sliced container in `stubs.yaml`.
  The set of stubs *is* the frontier. An edge can target a whole stub paper
  until curation slices it and the target sharpens.

One rule keeps the graph honest: generalize, don't merge. Never equate two
claims. Co-parent them under a broader claim node, so each paper's specific
phrasing and its quote survive.

## Source of truth

The git-tracked YAML is the source of truth: one diffable file per curated
paper, thin files for broad slices, a stub registry. The SQLite `graph.db` is a
disposable build artifact, rebuilt from the YAML and never committed. Curated
PDFs and their extracted full-text live in the data repo, one per paper;
uncurated staging PDFs stay outside git.

```
human-supplied PDF ──────────────▶  staging dir (outside git)
                                         │
read + curate, one paper at a time       │
        │                                │
        ▼                                │
YAML source of truth (git) ◀─────────────┘   curated/*.yaml · claims/*.yaml
        │                                     questions/*.yaml · methods/*.yaml · stubs.yaml
        │  lit build
        ▼
   graph.db (SQLite, gitignored)  ──▶  self-contained HTML graph viewer
```

The split means the graph is versioned and hand-reviewable as text, and CI can
build the viewer with no reference manager present.

One string names everything for a paper: the **citekey**,
`<Family><Year><Venue>` in CamelCase, for example `Chen2021Sys`. It names the
PDF, its full-text `.md`, the `curated/<citekey>.yaml` file, and the
`stubs.yaml` key.

## The tools

Everything runs through the `lit` CLI.

- **`lit ingest <pdf>`**: initialize a paper's bibliographic skeleton. Writes
  `curated/<citekey>.yaml` with metadata and authors, one deduped `stubs.yaml`
  entry per citation (DOI-anchored via OpenAlex), and an AI-readable `.md`
  full-text beside the renamed PDF. It does not extract slices: that is
  curation. Use `--dry-run` to preview without writing.
- **`lit build`**: build the static graph viewer into a self-contained
  `dist/index.html`. Validation fails the build on a dangling reference or a
  citekey collision. This is the shareable artifact.
- **`lit serve`**: the same viewer over loopback HTTP for a curation session.
  The graph rebuilds from the YAML on every refresh, so you edit a file and
  refresh; a broken edit returns the validation error and the server survives.
  Quotes get PDF hover-preview: hovering a claim's weld pops its PDF page with
  the sentence highlighted, and clicking pins a scrollable viewer over the whole
  document.

- **`lit locate`**: resolve every curated quote's place in its PDF and store it
  as `quote_loc` in the YAML. Run once, review the diff, commit.
- **`lit preview <citekey>`**: render one paper's local subgraph in isolation,
  through the same viewer `lit build` ships. Fed a scratch YAML, it renders a
  proposition before it is committed: the curation loop's "show it as it will
  look" step, which also flags any non-verbatim quote.

Smaller commands round out the loop: `lit enrich` and `lit abstracts` backfill
stub metadata and abstracts onto papers ingested before those fields existed,
`lit tag` edits a paper's tags, `lit topics` reports the topic axis (including
`--orphans` for dead keywords and unfiled tags), `lit programme` reports the
programme graph's emergent state, and `lit curate` moves a paper in or out of
the reading list (`[curation] active`). Every one of them has `--help`.

## Install the viewer on a phone

`lit serve` ships a web app manifest and dedicated iOS/Android icons. Bind it to
loopback and let [Tailscale Serve](https://tailscale.com/kb/1312/serve) publish
it to your tailnet over HTTPS, then open that URL on the phone and use **Add to
Home Screen**:

```bash
lit serve --host 127.0.0.1 --port 8000 --root /path/to/your/library
tailscale serve --bg --https=8000 http://127.0.0.1:8000
# -> https://<machine>.<tailnet>.ts.net:8000/
```

`tailscale serve` keeps its configuration across reboots and only touches the
port it is given, so other apps served the same way are unaffected. The
curation endpoints stay off the ordinary LAN, as with a tailnet-only bind.

### The offline copy

Over HTTPS the installed app keeps a read-only copy of the library on the
device, so tapping the icon with the server down still opens the graph and
every PDF. Each time the app opens it fetches `/offline.json` (every URL worth
keeping with a size-and-mtime version) and copies into the browser's Cache
Storage only what is new or changed, a few files at a time, deleting what the
server no longer has. An interrupted first sync resumes where it stopped. A
status chip in the corner shows progress, then "offline copy up to date · N
PDFs · X GB", or "server not reachable · offline copy from <time>".

A service worker (`/sw.js`) answers from that copy. The page and the graph come
from the server first and from the copy when the server does not answer within
four seconds; PDFs come from the copy first, including byte ranges. Running
from the copy, the moves that write (curate a paper, remove it from the
reading list) are disabled with the reason beside them, and the PDF pane shows
the cached PDF in the browser's own viewer instead of server-rendered pages,
so quote highlights and find-in-PDF need the server.

Without HTTPS (plain `http://` to a tailnet address), in a private window or
from a `lit build` file, the browser keeps no worker and the app behaves as it
always has. The static `lit build` output carries the manifest and icons for
HTTPS hosting but registers no worker: it has no PDFs or sync list to keep,
and as one self-contained file the browser's own cache already covers it.

## Curating a paper

Curation runs in one of two modes, and in both the human is the gate: the agent
proposes, the human accepts / edits / rejects, and nothing is curated until they
commit it. **Interactive** — work one pass at a time, explaining your reading at
that pass's granularity in prose, discussing until you and the human agree, then
tokenizing the agreed nodes into `curated/<citekey>.yaml`, realigning after every
pass and never tokenizing ahead of agreement. **Batch** — a dispatched agent is
given one paper and a target pass up front, climbs to it in a single run, and the
finished proposition is reviewed as a git diff. Batch buys throughput at the cost
of alignment bandwidth; see [CURATION.md](CURATION.md) for the briefing rules that
keep it honest.

## Read next

The design is documented in the order it is best read:

1. **[CONCEPT.md](CONCEPT.md)**: the model. One primitive, one container, three
   edges, and why it has this shape.
2. **[SCHEMA.md](SCHEMA.md)**: the on-disk data model. One diffable YAML per
   curated paper, thin files for broad slices, the stub registry.
3. **[CURATION.md](CURATION.md)**: the reading protocol. The pass-by-pass sweep
   that turns a paper's full text into its proposed local subgraph.
4. **[example/](example/)**: a small, fully-resolvable worked library exercising
   every slice kind and every edge. Start here to see real YAML.

Design converged and the data model is drafted; the `lit` CLI ingests, locates,
builds, and serves. [CURATION.md](CURATION.md) is where to go next to read your
first paper into the graph.
