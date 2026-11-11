# Curation cockpit — redesign delta (curation is a *place*, not a mode)

**Status:** shipped (all three slices on `main`, 2026-07-09) — supersedes the global-mode framing of
[the cockpit design](2026-07-09-curation-cockpit-design.md) · **Date:** 2026-07-09 · companion to
[CURATION.md](../CURATION.md)

> **Retired (2026-08-27):** the cockpit (§§3–4: the in-progress zone as a three-pane curation
> session) is gone — curation now happens with conventional coding agents against the reading
> list. §2 (the browse view's collapsible/detachable docked PDF pane) is unaffected and still
> current. See [CURATION.md](../CURATION.md).

> **Superseded in part (2026-07-28):** §4's *three-pane* layout is gone — curation now opens three
> real OS windows, and the ttyd terminal iframe is a native emulator. See
> [curation windows](2026-07-28-curation-windows.md). Everything else here still holds: the move,
> the `active` worklist, the focus wire, the browse view.

> **Gone (2026-11-11):** the `active` worklist, `lit curate` and `POST /active` — the desk replaced
> them. See [the desk](2026-11-11-desk.md).

The cockpit doc built curation as a **global window mode** (`lit serve --curate` reshapes the whole
view). This delta rotates that: curation becomes a **per-paper place** you *move a paper into*. The
main view stays the graph; a paper you decide to curate is pulled out of it into an **in-progress
zone**, and that zone *is* the three-pane cockpit we built. **Claude lives only in the zone.**

Everything built in the parent doc survives — the focus wire, `buildWin`/`mountDoc`, the docked
pane CSS, the ttyd terminal + seed/resume wrapper. It is **recomposed, not rewritten**. What
changes is *where* each piece lives and *what triggers* it.

The arc: **browse** the graph (peek at a PDF on hover) → **right-click → curate** one paper (it
moves into the zone) → **work it in the cockpit** (you + Claude, PDF + terminal) → **finish** (it
rejoins the graph).

---

## 1. Two surfaces

| | **Main view** (browse) | **In-progress zone** (curate) |
|---|---|---|
| Layout | the graph column view, as today | the three-pane cockpit (card · PDF · terminal) |
| PDF | one **collapsible** viewer, **hover**-driven | docked PDF pane, driven by the focus wire |
| Terminal | **none** | the per-paper ttyd Claude session |
| Population | every paper **not** in progress | every paper moved in via right-click |

A paper is in exactly one surface at a time — the move is a partition, not a copy (§3).

---

## 2. Main view — the collapsible PDF viewer (§decision 2)

**Out:** the floating hover soft-preview *and* click-to-pin windows (`softEl`, `pdfWindows`,
`nudgeIfColliding`) — gone from the main view. A claim click goes back to just drilling / pinning
the edge; no PDF window spawns.

**In:** one **collapsible** PDF viewer docked to a side, toggled open/closed from the HUD. While
**open**, hovering a claim navigates the viewer to that claim's citation — page + highlight, via
the existing `resolveLoc` → `mountDoc`. While **collapsed**, hover is inert. Hovering claims across
different papers switches the document; it rests on the last-hovered citation when the pointer
leaves.

This is **client-side** — hover drives `mountDoc` directly, no `/focus` round-trip. The focus wire
stays for the *zone* (where a terminal must stay in sync); the main viewer has no terminal to sync,
so per-hover POSTs would be pure overhead. Debounced (~180 ms) like the old soft preview so
pass-through hovers don't thrash the render.

---

## 3. Curation as a per-paper move (§decision 1)

**Entry:** right-click a paper card → a context menu → **"Curate this paper."** (contextmenu event,
default browser menu suppressed. Curated papers for now; promoting a stub is a later item.)

**The move = the `active` worklist.** "Curate this paper" adds the citekey to `[curation] active`
in `config.toml` — the list that *already* is the manual in-progress worklist (the "in progress · N"
pill reads it). The main view then simply **stops drawing `active` papers**; the zone draws them.
So "move, not copy" is one persisted flag and a display partition — no new data model, and it
survives refresh because it lives in `config.toml`, re-read per request like every other edit.

**Exit is explicit (§decision 1).** Not maturity-driven — a paper at `pass` 4 can still want a look.
Finishing is symmetric: right-click in the zone → **"Return to graph"** (removes it from `active`),
or the CLI verb I run on your say-so. It then rejoins the main view at whatever maturity it reached.

**Serve endpoint.** `POST /active {citekey, active: bool}` writes the `config.toml` worklist
(add/remove), mirroring how `POST /quote_loc` writes YAML. A rebuild picks it up. Plus a CLI
`lit curate <citekey>` / `lit curate --done <citekey>` so the move is drivable from the terminal too.

---

## 4. The in-progress zone = the cockpit (§decision 3)

The zone is where the parent doc's cockpit now lives. Selecting an in-progress paper opens **its**
three-pane cockpit: the card (left), the docked PDF pane (right-top, focus-wire-driven — so my
`lit focus` and your quote-clicks both aim it), and the ttyd terminal (right-bottom) running **that
paper's** persistent Claude session. Several papers in progress → a switchable set (the pill's
prev/next, elevated from a peek into the actual workspace).

**Claude lives only here.** The main view has no terminal. A session exists only while its paper is
in the zone; "Return to graph" leaves the transcript on disk (resumable if you re-curate later),
per the parent doc's file-persistence model — still nothing to reap.

**`lit serve --curate` retires as a global flag (§decision 3).** A plain `lit serve` now grows all
of it: the collapsible viewer, the right-click move, and the zone. ttyd is spawned by `lit serve`
whenever it's installed (curation can begin anytime), with the same graceful pane-only degradation
when it isn't. The `cockpit` payload injection stays, but it now means "terminal features
available," not "the whole window is curate mode." The three-pane layout renders only when you're
*in* a paper's cockpit.

---

## 5. Reuse / retire ledger

**Carries over unchanged:** `/focus` GET/POST + poll · `buildWin` / `mountDoc` / `resolveLoc` · the
docked-pane CSS (→ both the collapsible viewer and the zone's PDF pane) · the ttyd launch +
`curate_session.sh` seed/resume wrapper · the `active` list + "in progress" pill (→ the zone) ·
`lit focus`.

**Retires / changes:** the floating soft-preview and click-to-pin windows (removed from main view) ·
`lit serve --curate` as a *global* mode (folded into plain `lit serve`) · `?curate` URL toggle
(the zone is entered by moving a paper, not by a mode switch).

---

## 6. Build slices

1. **Collapsible hover-viewer (main view).** Rip out the floating soft-preview + pinned windows;
   add the collapsible viewer; hover a claim → `mountDoc` it. Pure client-side, no state, no server
   change. Ships on its own and is the cleanest first cut.
2. **The move.** Right-click menu → "Curate this paper"; `POST /active` + the `config.toml` write +
   `lit curate` CLI; main view filters out `active` papers.
3. **The zone as cockpit.** Render `active` papers as entrable cockpits (relocate the terminal +
   focus-wire PDF pane from the retired global `--curate`); symmetric "Return to graph"; drop the
   global flag / `?curate`.

Dependency is one-directional: slice 1 is standalone; 2 needs no viewer work from 1; 3 composes 2's
zone with the parent doc's terminal. Each is a clean stopping point.

**All three shipped** (2026-07-09): (1) `eeafad8`, (2) `35c82ab`, (3) this commit. The global
`--curate` flag and `?curate` toggle are retired — `lit serve` always offers the terminal (via ttyd
when installed) and the cockpit renders only when you enter a paper's zone. The zone's left card is a
`/preview.html?key=…&drive=1` iframe whose quote-clicks POST `/focus`; the parent polls `/focus` while
the zone is open and re-aims a `.pw-zone` pane re-parented into the overlay's top-right cell; the
terminal stays pinned to the zone's paper even as the pane roams to a cited paper.

---

## 7. Open questions

- **Collapsible viewer side & default state.** Which edge, how wide, open or closed on load. Cosmetic
  — settle in build 1.
- **Right-click on a stub.** "Curate this paper" could *promote* a stub (ingest + move). Deferred;
  curated-only for now.
- **Zone with many papers in progress.** Prev/next set is the default; a small list/switcher may
  read better once there are more than a couple. Revisit when it's populated.
- **Hover target precision.** Only quote-bearing claim rows navigate; hovering a non-quoted slice or
  the card body should leave the viewer where it is (not blank it).
