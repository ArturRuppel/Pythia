# CURATION: how to read a paper into its local subgraph

**Status:** v2, the lean slice model. **Date:** 2026-06-25. **Batch mode added:** 2026-08-21.
**Last revised:** 2026-11-11. Companion to [CONCEPT.md](CONCEPT.md) and [SCHEMA.md](SCHEMA.md).

CONCEPT says what the graph is and SCHEMA says how it is stored. This document is the
reading protocol: the structured pass an agent makes over one paper's full text to propose
its local subgraph, for a human to accept, edit or reject. The subgraph is the paper's claim,
question and method slices and their edges, written as `grounded_in`, `leads_to`,
`corroborates`, `contradicts` and `answers`.

This is not a CLI. Curation is reading comprehension and judgement, and only an agent that
reads plus a human who curates can do it. The human is always the gate. The agent proposes,
the human accepts, edits or rejects, and nothing is curated until the human commits it.

`lit ingest` has already written the bibliographic skeleton: metadata, authors, `stubs.yaml`
entries and the `<citekey>.md` full text. Curation fills in the semantic body.

## Two modes

What varies between the modes is when the human is consulted.

**Interactive.** The human is present, typically with `lit serve` running and the paper's
card open. Each pass is a loop: the agent explains its reading in prose at that pass's
granularity, the two discuss until they agree, and only then does the agent tokenize the
agreed slices into `curated/<citekey>.yaml`. They realign before the next pass. Use this
mode when the paper is load-bearing, when its reading is contested, or when the curator
wants to steer granularity as it forms.

**Batch.** The human is not present. A dispatched agent is given one paper and a target
pass up front, climbs to that rung in a single run writing directly into
`curated/<citekey>.yaml`, and the completed proposition is reviewed afterwards as a git
diff. Agreement moves to the two ends: the target pass is agreed at dispatch, and the slices
are judged on return. This is how a batch of papers is curated in parallel, one agent per
paper.

Batch trades alignment bandwidth for throughput, and the cost is real. A misjudged reading
surfaces at the end rather than at the pass that produced it, so there is more to reject at
once. Two briefing rules keep it honest:

- Tell the agent what the paper is being asked to support, and instruct it that a finding
  which undermines that is the most valuable thing it can return. An agent that only ever
  confirms has been briefed badly.
- Name the specific question the paper must settle, so that its verdict on that question
  comes back stated outright rather than buried in the slices.

## The rhythm

### Discuss, then tokenize

In interactive mode, never write slices ahead of agreement. Each pass is the loop above:
explain your reading at the pass's granularity, discuss until aligned, and only then weld
the agreed slices into the file. Realign before the next pass. Curation runs from a
conventional coding-agent session, so the explain step happens in the session's own chat.

In batch mode this loop collapses to its two ends: the target pass is agreed at dispatch and
the whole proposition is judged on the git diff.

**`validated` is the owner's; never write it.** Next to `pass` a curated file may carry
`validated: N`, the pass the owner has validated (SCHEMA section 4). Curation, interactive or
batch, never adds, changes or removes that line, and an agent never runs `lit validate`. Raising
`pass` is what puts a paper on the owner's desk; the owner takes it off by validating.

### Render the proposition

Prose is hard to judge, so show the proposition as it will look. During the explain step,
write the pass's proposed slices to a scratch YAML in the real `curated/` schema, held
outside `curated/`, and run:

```
lit preview --scratch <file> --root <data>
```

This renders that one paper's local subgraph in isolation, with its slices and every edge,
and cross-paper endpoints shown as their stub chips or synthesis band. It uses the exact
viewer `lit build` ships, so the preview cannot drift from the final graph. The human judges
the card as it will actually look. Only on agreement is the scratch draft promoted into
`curated/<citekey>.yaml`, and that promotion is the tokenize step. Preview also checks the
quotes: a `quote-flag` warns at proposition time if an anchor is not verbatim in the `.md`.
It is a rendering aid, not a shortcut past the reading and judgement. The discussion is
still the work.

Where the render lands depends on the human's review surface. `lit preview --scratch`
writes a standalone `dist/preview.html`. Reach for it when there is no `lit serve` running,
or to see a proposition rendered before it lands in `curated/` at all. When `lit serve` is
running against the data repo, the simpler path is to tokenize straight into
`curated/<citekey>.yaml`, since that edit is the proposition. Run `lit build` first to
confirm it validates, then tell the human to reload the paper's card in the graph viewer.
Either way the human accepts, edits or rejects via the git diff, and whatever is rejected is
reverted before the next pass.

### Propose, never flood: the staircase

A handful of well-welded slices beats a wall of shallow ones (CONCEPT section 10). Curation
is a single staircase. A paper climbs it one rung at a time, and the rung is both how far
you read and how mature the card is. There is no second axis.

Record the rung reached as `pass: 0–4` on the curated file:

| pass | name | what it means |
|---|---|---|
| 0 | ingested | metadata and extracted full text, ready to curate |
| 1 | abstract | every slice on the card is supported by the abstract |
| 2 | introduction and discussion | borrowed claims, graph connections, open questions from the discussion |
| 3 | results | claims sharpened and welded to phrases describing the data |
| 4 | methods | methods read precisely, their citations traced and linked: the full sweep |

Bump `pass` only; leave a `validated:` line exactly as you found it, and never add one.
Climb one rung at a time, bumping `pass` as you go: one rung per sitting in interactive
mode, or up to the dispatched target in a batch run. Stopping early is a normal resting
state, not an unfinished task, and a batch target below 4 is a deliberate resting place
rather than a job left half done. The interface shows the owner's `validated` pass as a
paper's status and puts the paper on the owner's desk when `pass` moves past it
([docs/2026-11-11-desk.md](docs/2026-11-11-desk.md)). A stub
carries no `pass`; breadth stays emergent via file presence (SCHEMA section 1). The reading
passes below are these rungs, with the same numbers and the same names.

### The quote is the integrity anchor

Every claim is welded to a quote grounded in the paper's `.md` full text (SCHEMA section 6,
rule 4). Verbatim substrings are the default. Non-contiguous passages may be shortened with
`[...]` when the curator explicitly accepts the flag. Never paraphrase into a quote. If you
cannot find the grounded sentence, the claim is not ready.

The quote is shown in the PDF, not as inline text. Under `lit serve`, hovering a claim pops
its PDF page with the sentence highlighted, and clicking pins it. The highlight comes from
`quote_loc` (SCHEMA section 6). Run `lit locate` once to resolve every quote's place in its
PDF by full-coverage word-geometry match and store it in the YAML, then review the diff and
commit. Quotes without a stored location fall back to a live resolve. `quote_loc` is derived
and regenerable, with `lit locate --force` at any time, and never a hand-authored judgement.

### Generalize, don't merge, and don't duplicate for nesting

Before creating a broad `claims/`, `questions/` or `methods/` node, look for an existing one
to `leads_to`. Co-parent; never equate two claims. A broad target earns its existence only
when at least two children share it, or when it is genuinely broader than any one child. One
claim is one slice, refined across passes, not re-extracted per section.

---

## The passes

Pass 0 is the ingested starting line, not a reading step. `lit ingest` has written the
bibliographic skeleton and no slices yet, and curation climbs from there.

A paper speaks in three registers, and the reading passes follow those, not the section
order:

- **Words**, in the abstract, introduction and discussion: what the authors claim, how they
  frame it, and how they found out. The abstract is the low-resolution skeleton, pass 1.
  The introduction and discussion are the full-resolution version. They are two halves of
  one move, since the introduction sets the claims up and the discussion cashes them in, so
  they are read together as one framing pass, pass 2.
- **Evidence**, in the results: grounds each headline claim in the specific methods and
  data, and surfaces new sub-claims. Pass 3.
- **Approach**, in the methods: refines the method DAG and traces its citation provenance.
  Pass 4.

So pass 0 is ingested, pass 1 the gist, pass 2 what they claim, pass 3 what backs it, and
pass 4 the method detail. Abstract sentences are verbatim-dense, so you will often weld a
provisional quote in pass 1 and merely confirm or relocate it from the results later.

In interactive mode each pass runs as explain, discuss, align, tokenize. In batch mode the
agent climbs the rungs in order without pausing and the whole climb is judged at the end.
The rungs still have to be climbed in sequence, because each one refines the slices the
previous one wrote rather than appending beside them. The tables below say what each pass
yields. In interactive mode they are the targets of the discussion, not a licence to write
before you agree.

### Pass 1: the abstract

Read only the abstract. The abstract states the approach, so the methods come out here, as
floor slices the headline claims can immediately ground in. Nothing is deferred.

| you find | it becomes |
|---|---|
| the question or questions the paper sets out to answer | draft question slices in `questions:` |
| the approach, its measurements and models | method slices in `methods:`. A measurement is a floor; a model is `grounded_in` the measurements it consumes (CONCEPT section 7) |
| the headline claims | claim slices in `claims:`, with a provisional quote welded to the abstract sentence, `grounded_in` the relevant method floors, and `answers` on the question they resolve |
| the authors' keyword line under the abstract | proposed `tags`. These are not slices: they are a container filter axis (SCHEMA section 4), welded to nothing, with no evidential weight |

For the tags, run `lit tag <key> --suggest` to scrape and kebab-case the keyword line from
the full text. It prints candidates and a ready `lit tag` command and writes nothing; you
accept the ones worth keeping. Author keyword lists are often three broad words a journal
required, so gate them by hand.

### Pass 2: framing, the introduction and discussion together

Read the introduction and discussion as one pass. This is everything the authors claim and
how they position it. The data that backs each claim waits for pass 3.

| you find | it becomes |
|---|---|
| the sharpened question or questions and their hierarchy | question slices `q1`, `q2` …; hierarchy is a `leads_to` to a broader question in `questions/<slug>.yaml` |
| the questions the paper raises and leaves open: "future work", "it remains unclear whether", "an open question is", mostly in the discussion | open question slices `oq1`, `oq2` …, each welded to the verbatim sentence that raises it, and left floating as edges go: no `answers`, no anchor to the finding that provoked them |
| framing sentences sitting on citation walls, mostly in the introduction | borrowed claim slices `b1`, `b2` …, `grounded_in` the cited papers. A citation, not a floor; these are restatements (CONCEPT section 6.1) |
| the authors' headline insights, mostly in the discussion | claim slices at high altitude, `c1`, `c2` …: the paper's contribution, `grounded_in` a method floor, or a premise claim for a theory claim |
| methods named in the body but not the abstract: the introduction's "we measured … with", the discussion's model | new method floor slices, with coarse `grounded_in` on the pass-1 claims sharpened to point at them. The abstract rarely names every technique; the rest surface here, and their DAG and provenance wait for pass 4 |
| an insight positioned against prior work | `corroborates` or `contradicts` on that claim, lateral |
| the broad claims that at least two claims ladder up into | `claims/<slug>` `leads_to` targets. Look before creating; a single child gets no broad twin |

An open question's `text` is your interrogative rephrasing and its `quote` is the
declarative source, exactly like a claim, so it is verifiable and findable in the PDF. Go
looking for these. The bird's-eye "what does this paper leave unanswered" is easy to miss
when reading for what the authors claim.

**Two of the ids carry your reading** (SCHEMA section 3). Pass 2 is where `b` and `oq` first
appear, because it is the pass that produces borrowed claims and open questions. `b` means
"this is a restatement off a citation wall" and `c` means "this is the paper's own". `oq`
means "the paper raises this and walks away" and `q` means "the paper set out to answer
this". Each prefix counts separately, `c1 b1 c2 c3 b2` down the file in reading order, so a
claim keeps its id when a later pass adds slices around it. If you cannot decide between `b`
and `c`, that hesitation is usually the signal that the sentence is doing two jobs and wants
splitting into two slices.

The prefix is a label on your judgement, not a substitute for the edges. A `b` claim still
needs its citations in `grounded_in`; the generator computes "borrowed" from those and reads
no prefix anywhere. Where the two disagree, chase it. An `oq` that a later paper answers
keeps its `oq` id. The id says what this paper left open, the emergent flag says what the
library still has open, and those are meant to come apart.

**Map the walls.** Anchoring each citation wall to one borrowed claim is the cheapest way to
give many stubs an edge at once. Every paper the authors cite behind the claim goes into its
`grounded_in`. Read the role from the citing sentence, trust the authors' grouping, and do
not re-check whether each cite truly confirms; that is out of scope. A borrowed claim grounds
in citations only, with no floor, so it reads as a restatement, plausible until its sources
are curated. This is the cheap tier of the policy that exhaustive coverage is an ambition
(CONCEPT section 10.4). Lateral `corroborates` and `contradicts` are drafted here from the
authors' words and confirmed against the data in pass 3.

**Open questions stay unwired here.** Weld each to its verbatim source sentence, run
`lit locate` for the PDF highlight as for a claim, and stop. Do not connect them by edge: no
anchor to the finding that raised them, no link to a claim elsewhere that answers them.
Those connections are made in the meta read, a separate cross-library pass that takes a
bird's-eye view over the whole graph. Per-paper curation just deposits the open question as
a floating but welded slice. An open question so left renders in its own "open questions"
section at the bottom of the paper's card, bucketed by the emergent open flag, and closes on
its own the day some paper's claim `answers` it.

### Pass 3: results, grounding the claims in data

Go through the results together, agent and human, relating the data back to the framing.
This is where each headline claim is grounded in evidence.

| you do | it becomes |
|---|---|
| find the verbatim sentence or figure caption that grounds each claim | the claim's exact `quote`, relocated from the pass-1 or pass-2 weld if a tighter one exists |
| confirm which specific method or methods produced each finding | the claim's `grounded_in`, sharpened from the coarse pass-1 set to the precise floors |
| a result that is its own finding, not in the framing | a new sub-claim, welded to its result sentence |
| confirm which specific prior paper each finding supports or refutes | the right `corroborates` or `contradicts` ref |
| record judgement and caveats | a `note:` on the slice, in the curator's voice, not quote-bound and never an edge |

### Pass 4: methods, refining the how-DAG

The method floors were born in pass 1. Here you refine them (CONCEPT section 7).

| you find | it becomes |
|---|---|
| which method layers on which, as when a model consumes a measurement | `grounded_in` edges between methods: `m_model grounded_in [m_measurement, …]` |
| the methods paper that introduced each technique | that method's `grounded_in: [<citekey>]`, which pulls the methods paper into the frontier exactly like a claim's citation |

A method `quote` is optional, since methods prose is boilerplate. Its `grounded_in`
provenance is the payload.

---

## Worked example: Chen2021Sys, the lean encoding

Threaded through `curated/Chen2021Sys.yaml` in the [`example/`](example/) data root.

- **Pass 1, the approach becomes method floors.** The abstract's "a microbenchmark harness …
  an open-network queueing model" becomes `m1`, the harness, a measurement floor with
  `grounded_in: [Bench2016Tools]`, and `m2`, the queueing model, with `grounded_in: [m1]`, a
  model layered on the measurement. A headline result becomes `c1` with `grounded_in: [m1]`.
- **Pass 2, framing.** The context sentence "…memory bandwidth bounds the latency floor of a
  pipeline" becomes borrowed claim `b1` with `grounded_in: [Patel2017Vldb]`. One sentence
  pulls a stub into the frontier, and with no floor it is a restatement. It also
  `answers: [q1]`. The open question the paper walks away from is `oq1`, welded but unwired. Consensus
  that generalizes gets a `leads_to`: `c1` into `throughput-scales-with-batching`, which
  earns its broad claim once a second paper, `Kumar2020Net:c1`, shares it.
- **Pass 3, results.** Each claim's `grounded_in` sharpens to the exact methods, for example
  `c3 grounded_in [c1, m2]` for the measured trend compared against the model, and each quote
  relocates to the tightest results sentence.
- **Pass 4, methods.** The method DAG is recorded, `m2 grounded_in [m1]`, along with each
  technique's introducing paper, `m1 grounded_in [Bench2016Tools]`.

---

## When the subgraph is written

The agent writes the proposal into `curated/<citekey>.yaml`. The human reviews the diff and
edits or accepts it. A future deterministic check, `lit verify`, the offline twin of
`lit ingest`, will gate it on SCHEMA section 6: every quote grounded, verbatim by default
with `[...]` flagged; every ref resolving; ids unique; no emergent fields authored; enums
valid. Until then, SCHEMA section 6 is the manual checklist.

---

## History

- **The in-browser curation cockpit** was retired on 2026-08-27. It was a card, paper and
  terminal window per paper, driven by a focus wire, and the card window hot-reloaded itself
  on every edit. Curation now runs from a conventional coding-agent session against the data
  repo, the human reloads the card in the ordinary viewer, and `lit serve` is purely the graph
  viewer. The `active` worklist survived the cockpit as a plain reading list, until the desk
  replaced it on 2026-11-11 ([docs/2026-11-11-desk.md](docs/2026-11-11-desk.md)). The cockpit is
  specified in [docs/2026-07-28-curation-windows.md](docs/2026-07-28-curation-windows.md)
  and sections 3 and 4 of
  [docs/2026-07-09-cockpit-redesign-in-progress-zone.md](docs/2026-07-09-cockpit-redesign-in-progress-zone.md).
- **Batch mode** was added on 2026-08-21. Before it, every curation was interactive.
