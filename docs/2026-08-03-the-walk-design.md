# THE WALK — one focus, one relation, no drawn edges

**Status:** **shipped in the viewer as a toggle** (2026-08-04); design direction below ·
**Date:** 2026-08-03 · supersedes nothing — the column board of
[2026-06-25-visualization-design.md](2026-06-25-visualization-design.md) is untouched and
remains the landing view.

> **Retired in part (2026-08-27):** the curation cockpit this doc mentions — the DRIVE card
> window, its `contents` button, the focus wire, "Reachable from the cockpit" below — is gone.
> The walk itself is a viewer feature and is unaffected: it still swaps the board in the ordinary
> graph viewer exactly as the first bullet below describes. See [CURATION.md](../CURATION.md).

- **In the viewer:** the `walk` button in the HUD (or the `w` key) swaps the board for the
  walk and back. One or the other, never both — the same full-pane exchange the library
  makes. Reading state on each side survives the toggle.
- **In the curation cockpit:** the same view, as a `contents` button in the DRIVE card
  window — see §3.5.
- **Mockup:** [`mockups/litgraph-walk.html`](mockups/litgraph-walk.html) — standalone,
  synthetic library generated to the measured statistics of the real one. Kept because it
  is the thing you can open next to `litgraph-columns.html` and judge side by side —
  but it **predates the `contains` roster** (§2, Rule 0) and has only the five relation tabs.
  The shipped viewer is the reference.

---

## 1. The diagnosis — measured, not felt

Taken from the real `dist/graph.json` (a few dozen curated papers, some hundreds of slices,
thousands of stubs, a few dozen broad slices). The four most matured papers are shown as
hubs A–D:

| focus | board spawns | board draws |
|---|---|---|
| hub A | 57 cards | 88 edges |
| hub B | 51 cards | 71 edges |
| hub C | 50 cards | 71 edges |
| hub D | 44 cards | 74 edges |
| **median paper** | **4 cards** | — |

Three things follow.

**The fanout is bimodal, and the cause is curation maturity.** The median paper spawns 4
cards; the papers we actually work on spawn 40–57. The board is tuned for the median and
collapses exactly where the work went. This is not random — `pass` predicts it, because a
matured paper is precisely one that has acquired slices, sources, a ladder and stances.
*The board gets worse as the library gets better.*

**Five relations share one canvas.** `grounds` is a DAG, within-paper support is a tree,
the `leads_to` ladder is a chain, `answers` is bipartite, stance is a signed relation.
Each has a different natural layout. Superimposed, none of them is readable. We are not
looking at a messy graph — we are looking at five graphs on one sheet of paper.

**Stance has no layout home, by design.** The 2026-06-25 doc says `corroborate` /
`contradict` draw "at wherever they already sit." One curated paper has 19.
Those are the strokes that cross the whole board, because they connect cards whose
column positions are unrelated to each other.

Hover-isolation (TODO, landed) is the tell: it exists because the resting state is
already unreadable. It is a transient fix for a persistent problem.

## 2. The move — walk one relation, render it as a tree

**Default view = one focus + one relation, as an indented tree, with no SVG edge layer
at all.** Zero lines means zero crossings, permanently, at any library size.

Same focus as the table above, in the walk (depth 2, sibling cap 7):

| focus | grounds | builds | gen | answers | stance | *board* |
|---|---|---|---|---|---|---|
| hub A | 4 | 4 | 15 | 16 | 16 | *58c / 89e* |
| hub B | 4 | 4 | 15 | 8 | 2 | *51c / 71e* |
| hub C | 1 | 4 | 15 | 6 | 0 | *50c / 71e* |
| hub D | 1 | 1 | 10 | 9 | 10 | *44c / 74e* |

Every relation, on every hub, stays inside one screen. (Measured against the shipped
viewer, not the mockup — hence the small drift from §1, which predates the `builds` fix
in §3.)

### The four rules

**1 · Every relation you are not walking is a badge, not a line.** Each row carries
`⊣3 ⊢2 ⤴1 ?1 ⚖2`. Clicking a badge draws nothing — it *pivots*: that node becomes the
focus and that relation becomes the walk. Navigation replaces superposition.

**2 · The DAG becomes a tree by repetition.** A node reached twice renders fully once and
elsewhere as a dim `↩ also under <key>` that jumps to the canonical occurrence. This is
already how the within-paper substructure view behaves, and it is the one part of the
current viewer that stays legible at depth.

**3 · Stance gets a ledger, not an arrow.** "What contradicts this" is a different
question from "what grounds this." Answering it with a stroke across a board is why the
board looks the way it does. Instead: the claim at the top, corroborating evidence in the
left column, contradicting in the right, each entry drilling to its quote. An endpoint
resting on a container renders as `▸ not yet sliced` — the CONCEPT §2 wildcard, visible
rather than silently mis-drawn.

**4 · The budget makes mess structurally impossible.** A depth cap and a sibling cap
bound what can render. Beyond them: a chip with a count. The citation wall folds *by
construction*, never by clean-up — and the readout in the HUD states, for every focus,
what the board would have drawn instead.

### Rule 0 · one tab is not a relation at all

The four rules above are about relations, and that was the hole. **Every tab was a relation,
so a slice only existed if it participated in one** — and a claim you have written but not yet
wired participates in none. Measured on the real library: **about a fifth of all slices (22%) were
unreachable from their own paper at any depth on any tab**, concentrated in the papers under
active curation (hub D hid 10 of 31). The board never had this problem — expanding
a card lists its slice rows — so the walk had introduced a regression precisely in the "let me
check what I wrote" motion.

**`contains` is now the first tab, and it is a roster rather than a walk.** Containment is what
a paper *is* (CONCEPT: a container of slices), not something you follow. Consequences:

- **Uncapped and unfolded.** The budget exists to stop a *walk* exploding; you cannot sift
  thoroughly through something the view is allowed to elide. The depth/sibling sliders are
  hidden on this tab because they would be lying.
- **Grouped by kind**, with `all · claims · questions · methods` filters, each entry carrying
  its weld quote (which drives the PDF, as everywhere else).
- **Unwired is a first-class state.** A slice no edge touches is flagged, and filterable on its
  own. That is not an error — it is the curation frontier *inside* a paper, and it was invisible
  before. **About one slice in eight** today.
- **A paper opens here**, which also settles the first §5 question below: not the ladder, not
  `grounds` — its own contents.

## 3. What the integration cost, and what it taught

Wiring the walk onto the real emitted JSON (rather than the mockup's own generator) turned
up three things the synthetic data could not have shown:

- **`builds` is not shaped like `grounds`.** In a `builds` record (build.py `_builds`),
  `key` *and* `via` both name the **building** paper — its citekey and its building slice —
  while `tid` names the slice of *this* paper being built on. Reading `via` as ours mints a
  cross-product id belonging to neither paper. It silently resolved to a real-looking node
  whenever the two papers happened to share a slice id, which is often.
- **The broad band has its own internal ladder.** `BROAD[slug].leads_to` climbs broad → broad
  up to the apexes the library is capped at. Index only the paper→broad `cons` edges and the
  four apex claims read as empty nodes — the exact opposite of the truth, since they sit at
  the top of the ladder.
- **A stance endpoint may rest on a container.** `{tid: null}` is the CONCEPT §2 unsharpened
  wildcard, not a miss. The ledger renders it as `▸ not yet sliced` rather than dropping it.

- **Within-paper support had no inverse.** `up` (build.py `_up` = `grounded_in` restricted to
  local refs) was indexed one way only, while the local `gen` ladder indexed both. So a
  measurement floor that three claims in the paper rest on read as *nothing builds on this* —
  inverting the truth about the most load-bearing slice in the paper. Caught by the roster's
  `unwired` census flagging floors, which are the last thing that could deserve the label; the
  count fell from 107 to 64 once the inverse existed.

None of these are visible at mockup scale; all four were caught by exercising every node
against every relation on the real library.

### Reachable from the cockpit

The walk was excluded from the DRIVE card window on the grounds that it carries only one paper.
That was backwards: the card window is *where curation happens*, and "did I account for every
slice I wrote" is the question being asked there. The card now carries the same view, labelled
**`contents`** because that is the half of it that matters in a one-paper window:

- The library rail is dropped (nothing to list) and the card's own paper is the standing focus;
  the root crumb returns to that paper rather than to an unreachable landing splash.
- Quote clicks POST the weld to the **focus wire** instead of aiming a local dock — the card
  window owns no dock, exactly as its board rows already behave.
- **The hot reload re-indexes it.** The card refreshes in place when the YAML changes underneath
  (an agent writing a pass, `lit tag`, an edit by hand); the roster rebuilds from the same
  refilled objects and holds its scroll. A slice that has just been written must never be missing
  from the one view whose whole promise is completeness.

## 4. What this does not change

The data model is untouched — no new fields, no authored layout. The walk reads the same
emitted JSON. `grounds` / `builds` / `gen` / `answers` / stance are the relations SCHEMA
already validates, and the emergent colouring rule (CONCEPT §3: colour is computed, never
tagged) carries over unchanged.

**The column board is untouched.** It remains the landing view and keeps every gesture it
had; the walk is a second view beside it, not a replacement, and which one is "default" is
a question to answer after living with both. The PDF dock spans the seam — hovering or
clicking a weld quote in the walk aims it exactly as a slice row does on the board.

## 5. Open questions, for after looking at it

- ~~**Does a paper open on the ladder or on `grounds`?**~~ **Settled: neither.** A paper opens
  on its own `contains` roster. The question was malformed — it asked which *relation* to land
  on, and the answer is that landing on a relation at all was the mistake. (`grounds` at paper
  granularity remains nearly empty, 1–4 rows, because only 13 curated→curated grounding edges
  exist library-wide; that is now a fact the roster's badges show rather than a landing.)
- **What is the roster's write half?** It is currently read-only, and it is exactly the surface
  where "this slice is unwired" wants a next action — pick its parent, ladder it, mark it a
  floor. The tool proposes and the human disposes (CURATION.md), so this would be a request to
  the session in the terminal window, not a direct YAML write from the viewer.
- **Two relations at once, ever?** `gen` + `answers` around one claim is tempting. It is
  also exactly how the board started.
- **Where does the topic axis attach** — the rail filters by it today; it may deserve to
  be a walkable relation of its own.
- **Does the repeat marker scale?** On a heavily shared support (a much-cited method) the
  tree could show the same node a dozen times before the reader notices they are repeats.
