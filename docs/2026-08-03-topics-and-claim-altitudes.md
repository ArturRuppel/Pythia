# Topics and claim altitudes — two axes, one library

**Status:** design · data layer and viewer both built · **Date:** 2026-08-03
**Companions:** [CONCEPT.md](../CONCEPT.md) · [SCHEMA.md](../SCHEMA.md) ·
[2026-07-19-tags-and-search-design.md](2026-07-19-tags-and-search-design.md)

The library crossed the size where its own top level stopped being readable: 53 curated
papers, 19 broad claims in a flat scroll, and a 92-item `tags` vocabulary. Two different
things were illegible, and they needed two different fixes.

| Illegible thing | The question it fails to answer | Fix |
|---|---|---|
| 19 broad claims in one list | *what is known, and how does it hang together* | more altitude on the **claim ladder** — same `leads-to` edge, no schema change |
| 92 free-form tags | *what papers do I have on X* | a new **topic axis** — keyword containers, outside the graph |

The temptation was to solve both with one mechanism: mint category nodes above the broad
claims and let them serve as headings. This document records why that was rejected.

---

## 1. Why a category cannot be a claim

Every emergent property in the model is defined on things that **assert** something:
grounded-vs-plausible needs a chain that can reach a floor, the evidence meter counts
corroborations *of a proposition*, the walk-to-root terminates on a measurement. A heading
asserts nothing, so a heading placed in the `leads-to` chain is a node where all of that
machinery silently returns garbage — and garbage that *looks* like a reading, which is worse
than an error.

It is also a category error in the edge itself. `leads-to` means "generalizes into". A
claim does not generalize into a subject heading; it is *about* one. Those are different
relations and collapsing them costs the model its only structural guarantee.

**The operative test, and the whole of the rule:**

> A statement that can be **false** is a claim. A heading you cannot disagree with is a topic.

Applied to this library, the claim ladder had two rungs left in it — all seven new nodes in
§2 are contestable propositions with a real null hypothesis behind them. It stops there. The
ceiling is where statements like *"systems respond to load"* start appearing, and the two
apexes sit one rung below it: anything that would parent *both* of them is exactly that
sentence. That is the altitude at which to switch axes, not before and not after.

## 2. What was added to the claim ladder

Seven new broad claims across two rungs, no schema change (a broad claim's `leads_to` into a
broader one was already in SCHEMA §4). 19 broad claims → 26, with **4 roots instead of 19**
and a ladder three deep.

First rung — five heads over the existing claims:

| New head | Children | The null it was written against |
|---|---|---|
| `backpressure-sets-pipeline-behaviour` | 5 | load passes through passively; each stage behaves on its own |
| `queueing-generates-tail-latency` | 3 | tail latency imposed from outside, by hardware or the network |
| `memory-layout-sets-operator-cost` | 3 | compute sets cost; memory layout is inert |
| `admission-control-is-a-load-signal-relay` | 2 | schedulers infer load from a static proxy |
| `tuning-effect-is-workload-dependent` | 2 | tuning gains differ in magnitude but not in sign across workloads |

plus the existing `system-performance-is-emergent`, which gained
`queue-depth-encodes-saturation` and `systems-run-at-the-saturation-knee` beneath it.

Two claims are deliberately **multi-parented** — `retries-inject-load` and
`hot-partitions-are-latency-sources` each ladder into two heads. Nothing is duplicated;
the DAG carries it. `scale-up-or-scale-out-dichotomy` is left an orphan root, which is a valid resting
state, not a gap to be filled with a head that would not earn its ≥2 children.

### The apex — two, and deliberately not one

Second rung. The five heads sorted themselves by *scale*, so they cap in two places:

| Apex | Children | The null it was written against |
|---|---|---|
| `pipeline-behaviour-is-collective-dynamics` | `backpressure-sets-pipeline-behaviour`, `queueing-generates-tail-latency`, `system-performance-is-emergent` | pipeline behaviour is the superposition of stage-local behaviours, load a downstream readout rather than a cause |
| `performance-and-control-share-one-substrate` | `memory-layout-sets-operator-cost`, `admission-control-is-a-load-signal-relay` | performance and control ride on separable machinery — an inert data path on one side, dedicated monitors feeding a control loop on the other |

**They are not joined, and joining them is the mistake to resist.** A rung above both would
have to say something like *"systems respond to load"* — the §1 test rejects it, because
nobody can disagree with it. Two apexes with no common parent is what an honest ceiling
looks like; a single root is an aesthetic preference, not a claim.

The other two roots stay roots. `tuning-effect-is-workload-dependent` is methodological
rather than scalar — it cuts across both apexes and belongs under neither — and
`scale-up-or-scale-out-dichotomy` remains the deliberate orphan.

**The apex meters read `0 / 0`, and that is the healthy state.** No paper takes a direct
stance on either; they are reached only through the ladder. If an apex meter ever starts
filling, papers are asserting it *directly* — which means it was never as high as it looked,
and the ceiling is lower than we drew it.

### The known cost

A head accumulates large in-degree, and its corroborate/contradict meter becomes a count of
corroborations of something near-truistic. Survivable at six heads; it is precisely the
symptom that says the ladder has gone one rung too high. If a head's meter ever starts
reading as noise, that head wanted to be a topic.

## 3. What a topic is

A **container of keywords** — nothing more. Full field spec in SCHEMA §9.

```yaml
title: "Cloud deployments"
note: "Performance read off multi-tenant, elastic infrastructure..."
broader: [deployment-contexts]
keywords: [cloud, serverless, autoscaling, edge-inference, ...]
```

Three properties make it safe to add:

- **Membership is derived.** A paper is in a topic iff one of its `tags` is one of the
  topic's keywords (transitively through `broader`). Nothing is written on the paper; a
  paper never names a topic. `tags` remains exactly the free-form container field the tags
  design specified, and the ban on slice-level tags is untouched.
- **It never enters the graph.** `broader` is confined to `topics/ → topics/`. A topic slug
  in any slice edge is a dangling ref and fails the build. The three-edge core is intact.
- **Keywords are non-exclusive.** `edge-inference` is in both `cloud` and `embedded`;
  `tiered-storage` is in both `testbeds` and `storage`. A topic may
  have several `broader` parents. This axis is a DAG on purpose.

## 4. The topic set as built

Four headings over fourteen keyword containers; all 92 tags filed, no dead keywords, every
one of the 53 papers reachable. Three containers sit under two headings each.

```
methods-and-tooling        benchmarking · fault-injection ·
                           testbeds* · modelling
performance                saturation · backpressure · load-balancing ·
                           concurrency · storage* · scheduling*
system-internals           memory-hierarchy · admission-control ·
                           storage*
deployment-contexts        cloud · embedded · scheduling* · testbeds*
                                                              (* = two parents)
```

**The tier-1 headings are navigation, not filters.** `performance` reaches 46 of 53
papers, which is useless as a query and fine as a place to start drilling. The leaf
containers are the filter that actually narrows (10–24 papers each). Worth knowing before
anyone wires a UI that treats the two tiers alike.

## 5. Tooling — `lit topics`

`litgraph/topics.py` holds the axis, deliberately outside `graph.py`. `build_graph` loads and
validates it as a last step that touches nothing above it, so every `lit build` checks the
tree; the emit layer ignores `Graph.topics` entirely.

```
lit topics                 # the tree, with papers reached and keywords owned per node
lit topics <slug>          # the papers one topic reaches, and its keyword closure
lit topics --orphans       # unfiled tags · dead keywords · stranded papers  (--strict for CI)
```

**`--orphans` is the load-bearing one.** The other two are conveniences; this is what stops
the layer rotting as the tag vocabulary grows. Three signals, none of them build errors:

| Signal | Means |
|---|---|
| *unfiled tag* — on a paper, in no topic | the topic layer has fallen behind the tagging |
| *dead keyword* — in a topic, on no paper | a typo, or a tag since renamed |
| *stranded paper* — curated, reached by nothing | untagged, or tagged only in unfiled vocabulary |

Run it after a tagging session. The library is currently clean on all three.

## 6. Rendering — and the lesson it taught

Two things had to be built, and the *first* one was not enough on its own.

**The band tiers by altitude.** `BroadNode.leads_to` was documented in SCHEMA §4 but never
loaded, so the entire broad-to-broad ladder — the new claim rungs *and* the six broad methods
that had been laddering since long before this document — had silently never rendered. With
that fixed the band became columns keyed by `SYNTH + tier`, generality still increasing
rightward, and the two apexes landed at altitude 3 and 2 rather than sharing a rightmost column.

**Altitude alone did not fix the flat list, and this is the part worth remembering.** Tier 0
still held 31 of 42 broad nodes; the leftmost synthesis column was still a 31-item scroll. *A
ladder makes altitude legible, but it does not remove leaves.* The list only got shorter when
the band was **collapsed to its roots** — the 14 nodes nothing ladders out of — with one click
revealing one generation, the same drill idiom the rest of the board already used. 42 → 14 on
the landing view; 26 broad claims → 4. *(That collapse was later reversed: hoisting turned out to
be the whole answer and hiding only subtracted — see "The band goes flat" below. The 31-item
column is back, deliberately.)*

**The landing column went the same way.** Papers now arrive only when something asks for them:
a claim you show, or a jump from the search box or the library. The board landed on 53 curated
papers for the same bad reason the band landed on 42 nodes. *(Also reversed, and by the same
argument — see "…and the landing column with it" below.)*

### Arriving is easy; leaving has to be too

*(This whole subsection describes machinery that no longer exists — the landing column is flat and
nothing arrives or leaves. It is kept because the diagnosis is the reason the collapse was
eventually abandoned: read it as the bill of costs, not as a description of the viewer.)*

The first cut of the collapse got the doors in and forgot the door out, and it was unusable for
three compounding reasons worth recording, because they are the generic failure of any
accumulate-by-clicking surface:

1. **The two chips looked like siblings and weren't.** The rung-opener moves *along* the band;
   the papers chip reaches *out* of it. Same row, same shape, same `▸`, two different axes.
2. **One door had no exit.** A paper reached by name was added to a set nothing ever removed
   from. Every search hit you had ever clicked was still there an hour later.
3. **Removal was unguessable even where it existed.** The column's contents were a *union* of
   sources, so un-toggling the chip that fetched a paper did nothing if a second source still
   wanted it. The affordance looked broken; it was just invisible bookkeeping.

Underneath all three: the column had no identity. It was not "this claim's evidence" nor "my
pile" — it was whatever had asked, with mixed provenance and mixed lifetime, and *that* is why
nobody could predict what would remove a card.

The fix keeps the accumulate model and makes it legible. Three sets, one rule *(superseded: only
`landedStuck` and `shownBroad` survive, both narrowed — see "…and the landing column with it")*:

| Set | Filled by | Lifetime |
|---|---|---|
| `landedStuck` | a jump by name — search box, library row | sticky |
| `shownBroad` | showing a claim (clicking its card) | lives and dies with the claim |
| `landedDropped` | the per-card `×` | **overrides both**, until something asks again |

> **A drop outranks every source, and lifts only when something explicitly asks for that paper
> again** — a jump by name, or the claim shown again.

That is the whole model, and it is what makes `×` mean what it says. Around it: each card states
what is holding it (`asked for by name · evidence for "…"`), recomputed every sync because a
second claim can add a *reason* without adding a card; the papers chip reports `showing 3 of 4`
rather than a bare total, so a dismissal leaves it honest; the two chips keep separate visual
languages (`▾ 3 narrower`, pill, purple, along the band · `◂ 2 papers`, square, paper-blue) so it
is obvious which axis each is talking about; and the column header carries `clear`, the guaranteed
way back to empty that a three-door column has no business lacking.

### One gesture per claim

Splitting the two chips into separate visual languages was the right diagnosis of the wrong
problem. It made the rung chip and the papers chip *distinguishable* — but distinguishable is only
worth having if they are different **decisions**, and they were not. Counting the whole card, there
were three gestures on it: `◂ 2 papers` landed the evidence, `▸ 3 narrower` walked one rung down the
ladder, and clicking the **card** pinned its edges bright and hoisted the block. All three mean
"show me this claim". They differed only in which fraction of the result you got.

And they were never independent. Since the landing column collapsed, a claim's evidence has no
cards until something lands it — so pinning a claim before showing its evidence isolates a set of
arrows that do not exist. The card click was only ever the chips' other half, and which one you
happened to reach for decided what you saw.

So the card is the whole gesture, at **every altitude**. Click a claim and whatever sits one step
below it comes onto the board: papers if the claim stands at the foot of the ladder, the narrower
claims that ladder into it if it stands higher, both if it has both. Its arrows go bright and stay
bright, and the whole block gathers into one screenful. Click again and it all comes undone. Both
chips lost their clicks and became **readouts** — `▾ 3 narrower`, `◂ showing 3 of 4` — reporting the
state rather than offering ways into pieces of it.

> **One card, one gesture.** Two controls for one intention is not a choice, it's a coin flip.

The generalization is the part worth keeping. A high-altitude claim's narrower claims *are* its
evidence, in exactly the sense that a tier-0 claim's papers are: the thing one step down that the
claim rests on. Which kind you get is a fact about where the claim sits in the graph, and asking the
reader to express that with a different chip pushed a detail of the schema out into their hands.
So `broadOpen` — the rung-reveal set — was deleted and folded into `shownBroad`, and `visibleBroad()`
now walks that one set. A claim's pin is likewise **derived** from `shownBroad` on every rebuild
rather than toggled separately: two independent flags for one fact can disagree, and these did. The
same collapse ate the hoist bookkeeping, since the click order to replay is just `shownBroad`'s own
insertion order.

Folding a claim takes its whole **subtree** with it (`pruneShown`, iterated to a fixpoint): a
narrower claim you reached *through* a parent has no card once the parent folds, and a shown claim
with no card is one still landing papers with nothing on screen to say why. A claim with two parents
survives until the last of them folds, which is what multi-parenting is for. *(Superseded — the band
is flat now and `pruneShown` is gone; see "The band goes flat" below.)*

Two consequences to know. Clicking empty board space thaws the slice-row pins but *not* the claims,
since dropping a claim's brightness while its evidence stayed on the board would rebuild exactly the
half-state this removed. And `clear` lives on the landing column header, so a high-altitude claim
shown with only claims beneath it has no `clear` to reach for — click it again. That was true of the
old rung chip too, but it is more reachable now that one gesture leads there.

### The library view — the other half of the split

Collapsing the papers only works if browsing has somewhere else to live, so it got its own
surface in the same document (a second *file* would duplicate the ~2.3 MB inlined payload and
break the single-file `file://` property). It is a reference-manager list — row per paper, facet
rail, virtualized over the whole ~3.8k-entry bibliography — over the *same* index the find-a-paper
box already built. **The topic axis is its facet rail**, which is where §4 said this axis
belonged: headings group, leaf containers narrow.

> **Browse is where you find; the board is where you reason.** A row click hands off to
> `gotoPaper()`, and that handoff is the seam between the two.

One asymmetry to know: topics reach curated papers only, because `tags` are curated-only and a
topic reaches papers through tags. A stub can never match a topic facet.

### Order is arrival order, not a re-sort

The last thing the collapse exposed: with the board landing near-empty, *everything* on screen got
there by a click, and the order it appeared in became the only structure there was. Two places
threw that away on every click.

The spawned columns (`grounds ←`, `builds on →`, the synthesis band) sorted globally by year, so
opening a second paper slid its grounds *into* the first paper's block. And `hoistBroad`, which
gathers a clicked claim and its papers into one screenful, hoisted to the very top
unconditionally — so clicking a second claim shoved the first one's block down and out of view.
Both make an *additive* gesture read as a rearrangement: you asked for one more thing and the
things you already had moved.

The fix is one idea applied twice. Every spawned card carries the **group** that pulled it in — the
index of the card you opened, in the order you opened it — and a column sorts by group first, its
own rule (year desc, ladder order) only within the group. The sweep in `rebuild()` therefore walks
`open` in insertion order rather than column order, which is where the index comes from. Hoisting
likewise became a stack: `hoistShown()` replays every shown claim's block in click order, so block
*N* lands below block *N−1*.

> **A click adds; it never rearranges.** Whatever was on screen before stays where you left it,
> and the new material lands underneath.

Two ties fall out of that rule and are worth stating. A card wanted by two groups belongs to the
**first** that asked — pulling it down on the second click would tear a hole in a block you are
still reading. And re-opening something you had closed counts as a **fresh arrival**, landing at
the bottom, because `open` and `shownBroad` are both ordered by last touch.

### The band goes flat — hoisting replaces hiding

The two mechanisms above were built for the same complaint (*42 nodes at once is a backlog*) and
only one of them was needed. **Collapsing the band to its roots** hid what you had not clicked;
**hoisting** gathered what you did click, with its narrower claims and its papers, into one
screenful at the top of their columns. Running both meant a click did two different kinds of thing
at once — reveal *and* place — and the revealing half was the one carrying all the costs:

- **You cannot see what is not there.** The band's job is to be the standing map of what the
  library claims. A map that renders only the branch you already walked is a worse map than a long
  one, and the roots-only view named 14 of 42 nodes — a reader with no way to know the other 28
  existed, let alone what altitude they sat at.
- **A rung's ladder was invisible until walked.** Altitude was added precisely so generality would
  read left-to-right, and then collapsed so that it could not: the tiered columns landed nearly
  empty, with the whole shape of the ladder deferred behind clicks.
- **A multi-parented claim flickered.** It appeared as soon as *either* parent was shown and
  vanished with the last of them — correct behaviour for a rule nobody could see, and the entire
  reason `pruneShown` had to iterate to a fixpoint.
- **Two meanings on one click.** Folding a claim both put its papers away and *deleted* cards
  elsewhere on the band, which is a lot of consequence for a toggle whose readout said `3 narrower`.

So the band is now **flat**: every rung of every ladder has a card, always, at its own altitude
(31 · 8 · 2 · 1 across the four tiers). `shownBroad` still exists and still means exactly one thing —
whose block is gathered at the top and whose papers are in the column — but nothing about it decides
what *exists* on screen. `visibleBroad`, `broadRoots` and `pruneShown` are gone with the mechanism
they served, and the `▸ / ▾` caret went off the `3 narrower` pill, because there is nothing left to
unfold: the pill is a constant fact about the ladder, and its **fill** is the whole state readout.

> **Order organizes; absence doesn't.** Put what the reader asked for at the top. Never make the
> rest of the graph unmentionable to get it there.

### …and the landing column with it

The same rule applied to the papers, and it collected a larger debt there. The column now lists
**every curated paper** (69 today) in `ORDER`'s pass ranking, from boot, permanently — plus the tail
of cards `landingKeys()` already minted for the 49 uncurated papers some lateral / `answers` edge
points at, which exist so those arrows have an anchor and are not part of the curated list the header
counts. Showing a claim hoists its papers to the top of that column instead of fetching them into an
empty one.

Everything the collapse needed in order to be usable went away with it, and that is the strongest
evidence it was the wrong mechanism — the machinery was all bookkeeping for a problem it had itself
created:

| Removed | Why it existed |
|---|---|
| `landedDropped` + the per-card `×` | a card could be *put away*, so there had to be a way to put it away |
| the drop-outranks-everything rule | two sets could want the same card, so removal needed a tiebreak |
| `showBroad`'s drop-reset loop | an old `×` would otherwise silently shrink a claim asked for later |
| the lens chip's `showing 3 of 4` | a total was a lie once a drop had happened |
| `LANDING_COLLAPSED` | the DRIVE / mobile windows needed the un-collapsed path — which is now the only path |

Three things survive, with narrower jobs. **`landedStuck`** no longer means "a paper I asked for by
name" (a curated paper is already there, so naming one is a scroll-and-flash) — it means a **stub**
summoned by name, the one class of card the flat list does not carry. **`clear`** no longer empties
the column, because a flat list has nothing to empty: it *releases* — every shown claim put away,
every summoned stub dismissed — and it appears only when there is something to release. And the
per-card **provenance strip** stops being an excuse for the card's presence and becomes a block
label: with two claims gathered at the top and no visual delimiter between their blocks, `evidence
for "…"` is the only thing that says which is which. A card with nothing to say shows no strip.

> **A flat list needs no bookkeeping.** Every rule the collapsed column needed was a rule about its
> own contents. The flat one has no contents to have rules about.

The cost is scroll and layout, and it is smaller than the collapse's own performance note suggests:
`landingKeys()` had already trimmed the column from `ORDER`'s ~3.8k entries to the 118 that can carry
an edge, so the board is **8.8k px** tall rather than the ~187k px that made every forced relayout
expensive. Measured unthrottled after the change: `rebuild()` 4–5 ms, a claim click 8 ms.

The flat band costs nothing in arrow clutter, which is worth stating because it looks like it should:
edges touching a broad node are already drawn *only* while that node is isolated (`redraw`), so the
band's 31 ladder rungs stay quiet until one is hovered or clicked. What it costs is scroll — the
`synthesis · now` column is a 31-card column again, exactly the list §6 set out to shorten. The
difference is that shortening it is no longer the only tool available: the reader's attention is
placed by hoisting, and a long column below the hoisted block is inert rather than lost.

*(That last paragraph turned out to name the bug rather than excuse it — see §6.1.)*

## 6.1 The band becomes containers — drawing the relation instead of a scalar

**Date:** 2026-08-04. The library had grown to 76 curated papers and 45 broad nodes, and the ladder
had stopped being navigable. The diagnosis is one sentence:

> **The band rendered *altitude*, which is derived, instead of *containment*, which is authored.**

`broadTier` is a scalar computed from `leads_to`. Sorting cards into columns by it takes a family and
sprays it across the board — tier 0 alone held **34 of 45 cards** — and then leaves the actual
relation to an arrow. Which the viewer *deliberately does not draw*: `redraw` skips every edge
touching a broad node unless that node is isolated. The paragraph above states this as a virtue
("costs nothing in arrow clutter"), and it is the whole defect. **At rest the ladder was not drawn at
all.** It existed in the data, it was legible in `lit topics`, and on the board it was 45 loose cards
in four columns whose only relationship was a scalar you had to infer from horizontal position.

Hoisting was the mitigation and it half-worked: `hoistEls` gathered a clicked claim, **one**
generation of its children and its papers to the tops of their columns. One generation, still in
separate columns, and the grouping purely positional — nothing drew a boundary around a family. It is
the same shape of problem the landing column had to invent the `cprov` provenance strip to work
around: *adjacency is not containment, and readers do not read it as containment.*

### The fix, and why it is not the collapse returning

A family is a **container**, the same way a paper is a container of its slices. CONCEPT already says
the model is recursively containerized; `renderGraph`'s own comment already says *"the card is the
board one scale down."* This makes that true in the other direction. One synthesis column now; one
box per ladder root; the root's card is the box's header exactly as a paper's citekey header names
the container its slices sit in; everything that ladders into it nests inside, recursively.

**Containment is drawn as containment**, so the rung arrows are *deleted*, not merely dimmed —
geometry says what the arrow said, and says it without being hovered. Edge count on the landing view
went 45 → 3, and the 3 that remain are the ones geometry cannot express (below).

This is not the roots-only collapse coming back, and the test is §6's own rule:

> **Order organizes; absence doesn't.** Never make the rest of the graph unmentionable.

Containers land **open**. Every one of the 45 nodes has a card, always, exactly as on the flat band —
verified in a headless harness rather than asserted: 45 cards, 0 duplicated ids, 0 broad nodes
without a card. Nothing is revealed by a click and nothing is hidden by one. **Containment adds a
boundary and subtracts nothing**, which is precisely what the collapse could not say for itself.

What the box does spend a control on is *density*, and that control is the paper card's `.sbar` idiom
one scale up: `fold to titles` / `show statements`, per family, seeded once so a box you opened stays
open across rebuilds. **A family lands folded**, because the band is the standing *map* of what the
library claims and a map shows names — every broad node has an authored `title` for exactly this
purpose (SCHEMA §4: "the at-a-glance name, with the full statement as its gloss"). The statement is
demoted, never removed: it is the row's own hover text and one bar-click from being on screen for the
whole family. That is the same move `.bn.titled .btx` already makes on a titled card.

### The DAG is not a tree — the one thing containment cannot draw

Three of the 45 nodes have two parents, and a box cannot hold a card that belongs in two boxes.
Duplicating the card is what an outline does and what `localDag` was written to stop doing to the
paper card, so:

> **A node nests under the first parent its authored `leads_to` names, and every other parent gets a
> reference row pointing at the real card.**

Authored order, so the curator decides which parent hosts and there is no heuristic to reverse-
engineer. The reference row (`↗ <title> · nested under "…"`) is a pointer, not a copy; clicking it
scrolls to and flashes the real card. The hosting card states its other parents in turn (`also under
"…"`), so a reader who lands on the real card is not the last to know. And the cross-parent
`leads_to` keeps its **arrow** — those 3 surviving `gen` edges — because it is exactly the relation
the boxes do not express.

Two of the three (`retries-inject-load`, `hot-partitions-are-latency-sources`) have
both parents under the same root, so they never leave their box. Only
`caching-effect-is-workload-dependent` genuinely straddles two families.

**This is the number to watch.** One crossing in 45 is a rounding error and the reference row absorbs
it. If cross-root parenting becomes common as the ladder grows, that is not a rendering problem to
solve again — it is the ladder saying its roots are wrong, and the fix would be in `claims/`.

### What the band looks like now

45 nodes → **16 top-level entries**: 5 family boxes and 11 singletons (a root with nothing under it
is not a container, just the card it always was — a box around one fact is chrome).

| Family | In the ladder | Nest depth |
|---|---|---|
| `pipeline-behaviour-is-collective-dynamics` | 15 | 3 |
| `performance-and-control-share-one-substrate` | 7 | 2 |
| `performance-benchmarking` *(method)* | 3 | 1 |
| `queueing-simulation` *(method)* | 3 | 1 |
| `tuning-effect-is-workload-dependent` | 1 (+1 ref) | 1 |

plus `scale-up-or-scale-out-dichotomy`, 3 broad questions and 7 loose broad methods standing alone. Families
sort before singletons, biggest first — structure ahead of orphans.

Hoisting survives with a **narrower job**: the *family* is what travels, not the rung. Pulling a rung
to the column top would tear it out of the containment that is the entire point, and there is nothing
left to gather anyway — a claim's narrower claims are already nested directly under it. So showing a
claim places its box at the top of the synthesis column, its papers at the top of the curated list,
and scrolls to the rung itself when the rung is not the box's head.

## 7. Deliberately not decided

- **Whether claims should carry topics.** They should not, for now. A topic on a broad claim
  is arguable (nothing in the graph could derive it), but it buys nothing the paper-level
  axis does not already deliver, and it reopens a rule that is currently load-bearing.
- **Whether showing a claim should be exclusive.** It accumulates: two shown claims put both sets
  of papers in one column, in blocks, in the order you asked. The alternative is that showing a
  claim *replaces* the column with that claim's evidence, with a separately-pinned set surviving
  alongside — which would dissolve the removal problem entirely rather than making it legible.
  Accumulate was kept because comparing two claims' evidence and looking for the overlap is a
  thing a synthesis board should let you do. Revisit if that turns out never to happen in
  practice — and note that it is now a cheaper change than it was, since one gesture and one
  derived pin means exclusivity would be a rule about `shownBroad` alone. It would also have to
  say what exclusivity means *up the ladder*: showing a claim inside the block you are already
  reading should surely not put the parent away.
- **Whether the band should separate kinds.** Containers made this much less pressing without
  deciding it, which is why they did not decide it. The two broad-*method* ladders
  (`performance-benchmarking`, `queueing-simulation`) are now their
  own boxes, so 6 of the 15 methods self-segregate for free — instrumentation gathers because it
  ladders, not because a rule sorted it. What is left interleaved is the **singletons**: 7 loose
  methods and 3 broad questions standing beside `scale-up-or-scale-out-dichotomy` at the bottom of one column.
  Sorting the top level by kind would separate them, and it is a one-line change to `broadOrder`'s
  comparator — deliberately not taken, because it would make *kind* outrank *structure* in the
  standing order, and a reader looking for what the library claims should meet the biggest ladder
  first, not the first claim alphabetically after all the methods.
- **Whether a family should be able to hold a paper.** A claim's papers are still hoisted into the
  *curated list*, a column away, while its narrower claims are now inside its box. Both are "the
  thing one step down that this claim rests on" — the generalization §6 made when it merged the two
  chips into one gesture — and containment now draws one of them and not the other. Landing the
  papers inside the box too would finish that thought. Not done: a paper is a container in its own
  right, with its own slice graph, and nesting containers of one kind inside containers of another
  is a much larger claim about the view than this change was making.
