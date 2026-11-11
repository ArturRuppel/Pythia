# The claim map — one page for the whole library

**Status:** prototype built (`prototypes/claim-map/`) · **Date:** 2026-08-25
**Companions:** [CONCEPT.md](../CONCEPT.md) · [SCHEMA.md](../SCHEMA.md) ·
[2026-08-03-topics-and-claim-altitudes.md](2026-08-03-topics-and-claim-altitudes.md) ·
[2026-08-05-additive-graph-views.md](2026-08-05-additive-graph-views.md)

Every view the library has is local. The column board expands one paper at a time and
[stopped scaling at 53 papers](2026-06-25-visualization-design.md); the walk shows one focus
and one relation by construction; the three earlier prototypes each draw a projection of the
authored edges, which is a diagnostic rather than an overview. At 204 curated papers, 44
broad claims and 341 attachments, nothing answers *what does the library look like from
above* — which is crowded, which is contested, which is finished.

This view does. It puts the **44 broad claims** on one page, not the 204 papers: 44 is a
number a person can look at, and the claims are the layer where the library says what is
known rather than what was read.

---

## 1. The proposal this replaced

The idea it came from was a similarity map: embed each paper's headline claim, place papers
so that near means alike, and read importance off the density of the clusters. Three things
were wrong with it, and recording them is the point of this section.

**Density-as-importance already exists, better.** Counting the papers that ladder into each
broad claim gives the same ranking, over buckets a human curated instead of buckets a
vocabulary produced.

**A title is not a claim.** `Atia2018NatPhys` is called *Geometric constraints during
epithelial jamming*, which names a subject and sells the work without stating the finding.
The library already derives a per-paper headline (`paper.head`, the terminal claim slice) for
182 of 204 papers, and it is a sentence rather than a title.

**Similarity is the wrong relation.** The four-paper dispute now sitting on
`queue-depth-encodes-saturation` fails a title embedding in both directions at once:
Bera2026's *Shape-Independent Fluidization in Epithelial Cell Monolayers* and Damavandi2025's
*Universality in the Mechanical Behavior of Vertex Models* are direct opponents on one claim
and share almost no vocabulary, while Rizzi2026's *Universal Persistent Brownian Motions in
Confluent Tissues* would land beside Damavandi on the shared "Universal" and attaches
somewhere else entirely. Two papers asserting opposite things about one quantity are the most
valuable pair in the library; a similarity layout either stacks them or scatters them at
random. Holding that dispute as one contested node is what the curation cost bought.

What survived from the proposal is its real content: **the library needs a view that fits on
one screen.** The axes below are drawn from the authored graph rather than from text.

## 2. The two axes

**x — the median publication year of the papers attached to a claim**, with the first-to-last
span and the middle half drawn behind it. This is the *is it live or is it finished* axis: a
claim whose supporters all landed 2011–2015 is settled or abandoned, one whose supporters
cluster in 2024–2026 is a frontier. Drawing the spread is not decoration. A single year for a
claim is a summary, and showing the distribution it summarises is what stops it being read as
a measurement.

**y — altitude on the claim ladder**, `leads_to` between broad claims, apex at the top. Four
rungs, 12 apex claims, 36 edges. This axis is *authored*: no vote, no tie-break, no
inference. Altitude is the longest path up rather than the shortest, so every drawn ladder
edge points upward; `verify.py` checks that numerically instead of the renderer assuming it.

**Area, not radius, carries the paper count**, so a claim with four times the support looks
four times the size. **Red means one thing**, as everywhere else in this repo: contradiction.
A filled red mark is a claim some paper contradicts outright; a red ring is a claim whose own
papers contradict each other.

## 3. Why the y axis is not a topic band

Banding by subject was the first instinct and it is not supportable. A claim carries no topic
of its own — topics are keyword containers over paper `tags`, and nothing in the graph
derives from them ([SCHEMA §9](../SCHEMA.md)) — so a claim's band would have to be a
plurality vote of its members' topics.

That vote is a near-tie almost everywhere. Across the 14 leaf topics the winning topic's
share has a **median of 0.22**, and it is **under 40% for 38 of the 42** claims whose papers
carry tags. Dropping the methods subtree barely moves it (median 0.29, 33 of 42 under 40%).
`queue-depth-encodes-saturation` is the clearest case: Saturation & queueing 19,
Performance 19, Methods & tooling 18. Any lane assignment there is a coin flip rendered as
a fact.

So topic is a **filter** in this view, which is a use that does not require picking a winner,
and the lane it would have owned goes to the ladder.

## 4. Two derivations that needed a decision

**Membership is the ladder union the signed axis.** A paper attaches to a claim if it
`leads_to` it *or* takes a signed position on it, so a paper that only contradicts a claim
still counts as being in the conversation about it. Where a paper does both — the intended
encoding of a counterexample, per Bera2026's curation note — the sign wins over the ladder.

**The two kinds of dispute stay apart.** Only 14 signed edges name a broad claim directly;
260 name another paper's slice. When both endpoints of one of those sit under the same claim,
that is a disagreement *inside* the claim rather than *with* it, and it is much the commoner
case: 9 claims carry one, led by `queue-depth-encodes-saturation` with 8 pairs. The two
counts are never summed, and the readout lists the pairs by name.

**A programme aim is not evidence.** `graph.papers` carries the programme's aims alongside
the literature (`type: "aim"`). They are dropped everywhere: counting `@adaptive-batching`
would put the lab's own proposal into a claim's support meter, and it did, until `verify.py`
caught the resulting disagreement with the `meter` the generator already computes.

## 5. What is in the folder

| File | |
|---|---|
| `index.html` · `style.css` | the one screen; the house Modernist tokens, no CDN |
| `derive.js` | pure: `graph.json` → the map's model. No DOM, no I/O |
| `map-view.js` | one renderer: axes, lane packing, ladder, marks |
| `app.js` | state, the readout, and every number in the chrome |
| `serve.py` | `python3 serve.py --graph /path/to/dist/graph.json [--port 8004]` |
| `verify.py` | **run first.** The numeric model, checked against the real library |
| `verify_headless.mjs` | the same numbers out of `derive.js`, so the JS port cannot drift |

Neither `verify` file ships with the view; both exist because the arithmetic decided the
design, and the topic-band measurement in `verify.py` is the evidence for §3.

A pinned claim is written into the query string (`?claim=<slug>`), so one claim's readout is
a link, and the panel is reachable without a pointer.

### How it is served

Registered in `serve.py`'s `_VIEWS`, so it appears in the board's renderings dropdown and is
served at **`/views/claim-map/`** by `lit serve` like the other three. It fetches a *relative*
`graph.json`, which the server answers with its own live payload — so the map reads the graph
rebuilt from YAML, not a stale `dist/` artifact, and it needs no rebuild step of its own. The
standalone `serve.py` in the folder still works for looking at one committed build.

Both handoff seams are wired, in both directions:

| | |
|---|---|
| board → map | the renderings dropdown (`viewer/js/16-renderings.js`) |
| map → board | `← board` in the header, shown only when `location.pathname` starts `/views/` |
| map → board, by name | every paper in the readout, and the claim's own title, link to `/?goto=<spec>` |

`?goto=` takes a broad slug as readily as a citekey ([17-handoff.js](../tools/lit/litgraph/viewer/js/17-handoff.js)),
so the claim title hands the board the claim and hoists its papers, while a paper row hands it
that paper's card. Nothing new was invented for either direction.

## 6. Open

- **Labels truncate at 38 characters** (17 of 44). The full title is in the tooltip and the
  readout. A second label row per mark, or leader lines into the gutter, would fix it
  properly.
- **Citation edges are not drawn.** Counts are deliberately absent — citation count tracks age
  and venue more than quality, and sizing by it would launder that bias into a picture that
  looks objective. The honest use is the edge set: who cites whom *inside* the library, which
  would show whether a crowded claim is one conversation or several groups not reading each
  other. OpenAlex already supplies it at ingest.
- **The x axis has no notion of a claim's own age**, only its papers'. A claim minted in 2026
  over papers from 2011 sits where its evidence sits, which is right for "is it live" and
  wrong for "when did we notice". The second reading would need a mint date the schema does
  not record.
