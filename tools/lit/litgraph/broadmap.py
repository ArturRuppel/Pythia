"""The map: the broad layer of the literature graph, and what hangs on it (`lit map`).

"The map" is the `claims/`, `questions/` and `methods/` tier (SCHEMA §4) plus every paper
slice that ladders onto it. Nothing here is authored and nothing is new graph: it is a
read-back of edges the papers already carry, so an agent (or a human at a terminal) can walk
the broad layer without parsing YAML or the viewer's graph.json.

One definition carries everything below — **a paper slice is on the map iff it reaches a
broad node**:

  - by `leads_to`, climbing any same-paper ladder first (SCHEMA §6.6 allows a local
    `leads_to`: `c2 -> c1 -> broad-slug` puts both c2 and c1 on the map, c2 *via* c1), or
  - for a claim, by `answers` naming a broad question directly.

A claim that answers a *paper* question gathered under a broad question is shown under that
question as an answer, but does not count as attached: it rests on its own `leads_to`, and
if it has none, the curator has not yet said which broad claim it supports.

The lateral balance of a broad node counts `corroborates` / `contradicts` edges landing on
it, on a broad node beneath it, or on a paper slice that hangs beneath it. Edges that land on
a whole container (the stub wildcard) are not counted — they do not say which claim they
mean. The viewer's meter (`graph.broad_meter`: support = generalizing + corroborating claims)
is reported alongside, unchanged, in the one-node view.

Terminal only, read-only, derived entirely from the loaded graph.
"""

from __future__ import annotations

import shutil
import textwrap
from dataclasses import dataclass, field

from .graph import Graph, Paper, Slice, classify_ref

KINDS = ("claim", "question", "method")
_BROAD = {"broad claim": "claim", "broad question": "question", "broad method": "method"}


def _gid(citekey: str, ref: str) -> str:
    """A ref as seen from `citekey` → a global id (local ids qualify; others pass through)."""
    return f"{citekey}:{ref}" if classify_ref(ref) == "local" else ref


@dataclass
class Hang:
    """One paper slice hanging directly on one broad node."""
    citekey: str
    slice: Slice
    via: list[str]          # same-paper slices climbed on the way, nearest first
    edge: str               # "leads_to" | "answers"
    slug: str = ""          # the broad node it hangs on

    @property
    def gid(self) -> str:
        return f"{self.citekey}:{self.slice.id}"


@dataclass
class Lateral:
    source: str             # global id of the asserting claim
    sign: str               # "corroborates" | "contradicts"
    target: str             # broad slug or global slice id


@dataclass
class MapIndex:
    graph: Graph
    papers: dict[str, Paper]                       # the curated papers considered (filtered)
    direct: dict[str, list[Hang]]                  # broad slug -> slices hanging on it
    entries: dict[str, list[Hang]]                 # slice gid -> where it enters the map
    kids: dict[str, list[str]]                     # broad slug -> child broad slugs
    laterals_on: dict[str, list[Lateral]]          # target (slug | gid) -> edges landing there
    answered_by: dict[str, list[str]]              # question gid -> answering claim gids
    slices: dict[str, tuple[str, Slice]] = field(default_factory=dict)   # gid -> (ck, slice)

    # --- the ladder ---------------------------------------------------------

    def kind(self, slug: str) -> str:
        return _BROAD[self.graph.broad[slug].kind]

    def roots(self, kind: str) -> list[str]:
        return sorted(s for s, b in self.graph.broad.items()
                      if _BROAD[b.kind] == kind and not b.leads_to)

    def below(self, slug: str) -> set[str]:
        """The node and every broad node beneath it (its children, transitively)."""
        out: set[str] = set()
        stack = [slug]
        while stack:
            s = stack.pop()
            if s not in out:
                out.add(s)
                stack.extend(self.kids[s])
        return out

    def ancestors(self, slug: str) -> list[str]:
        """Every broad node above `slug`, nearest first (breadth-first, each once)."""
        out: list[str] = []
        frontier = list(self.graph.broad[slug].leads_to)
        while frontier:
            nxt: list[str] = []
            for s in frontier:
                if s not in out:
                    out.append(s)
                    nxt.extend(self.graph.broad[s].leads_to)
            frontier = nxt
        return out

    # --- what hangs beneath a node -----------------------------------------

    def hangs_below(self, slug: str) -> list[Hang]:
        return [h for s in sorted(self.below(slug)) for h in self.direct[s]]

    def laterals_into(self, slug: str, deep: bool = True) -> list[Lateral]:
        """Lateral edges landing on the node, on broad nodes beneath it (deep), or on the
        paper slices hanging there. Each (source, sign, target) once."""
        nodes = self.below(slug) if deep else {slug}
        targets = set(nodes) | {h.gid for s in nodes for h in self.direct[s]}
        seen: set[tuple[str, str, str]] = set()
        out: list[Lateral] = []
        for t in sorted(targets):
            for lat in self.laterals_on.get(t, []):
                k = (lat.source, lat.sign, lat.target)
                if k not in seen:
                    seen.add(k)
                    out.append(lat)
        return out

    def answers_for(self, hangs: list[Hang]) -> dict[str, list[str]]:
        """Gathered question gid -> answering claim gids."""
        return {h.gid: self.answered_by.get(h.gid, [])
                for h in hangs if h.slice.kind == "question"}

    def enters(self, gid: str) -> list[str]:
        """The broad nodes a slice hangs on directly (where it enters the map)."""
        return [h.slug for h in self.entries.get(gid, [])]

    def reach(self, gid: str) -> list[str]:
        """Entry broad nodes of a slice, then everything above them, each once."""
        out: list[str] = []
        for h in self.entries.get(gid, []):
            for s in [h.slug] + self.ancestors(h.slug):
                if s not in out:
                    out.append(s)
        return out


def build_index(g: Graph, only: set[str] | None = None) -> MapIndex:
    """Index the map over the curated papers (restricted to `only` citekeys when given)."""
    papers = {ck: p for ck, p in g.papers.items()
              if p.curated and (only is None or ck in only)}
    direct: dict[str, list[Hang]] = {s: [] for s in g.broad}
    entries: dict[str, list[Hang]] = {}
    slices: dict[str, tuple[str, Slice]] = {}
    laterals_on: dict[str, list[Lateral]] = {}
    answered_by: dict[str, list[str]] = {}

    for ck in sorted(papers):
        p = papers[ck]
        by_id = {s.id: s for s in p.slices}
        for s in p.slices:
            gid = f"{ck}:{s.id}"
            slices[gid] = (ck, s)
            # climb leads_to, through same-paper ladders, to every broad node it reaches
            found: list[tuple[str, list[str], str]] = []
            seen: set[str] = set()

            def climb(t: Slice, via: list[str]) -> None:
                if t.id in seen:
                    return
                seen.add(t.id)
                for r in t.leads_to:
                    if r in g.broad:
                        found.append((r, via, "leads_to"))
                    elif classify_ref(r) == "local" and r in by_id:
                        climb(by_id[r], via + [r])

            climb(s, [])
            if s.kind == "claim":
                for r in s.answers:
                    if r in g.broad:
                        found.append((r, [], "answers"))
                    else:
                        answered_by.setdefault(_gid(ck, r), []).append(gid)
                for sign in ("corroborates", "contradicts"):
                    for r in getattr(s, sign):
                        if classify_ref(r) == "container":
                            continue
                        t = r if r in g.broad else _gid(ck, r)
                        laterals_on.setdefault(t, []).append(Lateral(gid, sign, t))
            done: set[str] = set()
            for slug, via, edge in found:
                if slug in done:
                    continue
                done.add(slug)
                h = Hang(ck, s, via, edge, slug)
                direct[slug].append(h)
                entries.setdefault(gid, []).append(h)

    kids: dict[str, list[str]] = {s: [] for s in g.broad}
    for slug, b in g.broad.items():
        for r in b.leads_to:
            kids[r].append(slug)
    for s in kids:
        kids[s].sort()
    return MapIndex(g, papers, direct, entries, kids, laterals_on, answered_by, slices)


# --- summaries (the shapes both the text and the JSON render from) ----------


def node_summary(ix: MapIndex, slug: str) -> dict:
    b = ix.graph.broad[slug]
    kind = ix.kind(slug)
    deep = ix.hangs_below(slug)
    near = ix.direct[slug]
    out = {
        "slug": slug, "kind": kind, "title": b.title, "text": b.text,
        "parents": list(b.leads_to), "children": list(ix.kids[slug]),
        "papers": len({h.citekey for h in deep}),
        "slices": len({h.gid for h in deep}),
        "direct_papers": len({h.citekey for h in near}),
        "direct_slices": len({h.gid for h in near}),
    }
    if kind == "claim":
        lats = ix.laterals_into(slug)
        for sign, key in (("corroborates", "corroborate"), ("contradicts", "contradict")):
            got = [l for l in lats if l.sign == sign]
            out[key] = {"slices": len({l.source for l in got}),
                        "papers": len({l.source.split(":", 1)[0] for l in got})}
    if kind == "question":
        gathered = [h for h in deep if h.slice.kind == "question"]
        ans = ix.answers_for(gathered)
        answering = {c for cs in ans.values() for c in cs} | \
                    {h.gid for h in deep if h.edge == "answers"}
        out["questions"] = len({h.gid for h in gathered})
        out["answered_questions"] = sum(1 for cs in ans.values() if cs)
        out["answering_claims"] = len(answering)
        out["answered"] = bool(answering)
    return out


def tree(ix: MapIndex) -> dict:
    """Every broad node's summary, grouped by kind, in tree (display) order."""
    out: dict = {}
    for kind in KINDS:
        out[kind + "s"] = [node_summary(ix, s) for s in _tree_order(ix, kind)]
    out["totals"] = totals(ix)
    return out


def _tree_order(ix: MapIndex, kind: str) -> list[str]:
    seen: list[str] = []

    def walk(s: str) -> None:
        if s in seen:
            return
        seen.append(s)
        for c in _sorted_kids(ix, s):
            walk(c)

    for r in _sorted(ix, ix.roots(kind)):
        walk(r)
    return seen


def _sorted(ix: MapIndex, slugs) -> list[str]:
    """Most papers first, then slug: the heavy parts of the map lead."""
    return sorted(slugs, key=lambda s: (-len({h.citekey for h in ix.hangs_below(s)}), s))


def _sorted_kids(ix: MapIndex, slug: str) -> list[str]:
    return _sorted(ix, ix.kids[slug])


def _slice_row(ix: MapIndex, ck: str, s: Slice) -> dict:
    gid = f"{ck}:{s.id}"
    return {"ref": gid, "kind": s.kind, "text": s.text, "enters": ix.enters(gid),
            "reaches": ix.reach(gid)}


def _paper_head(p: Paper) -> dict:
    return {"citekey": p.citekey, "title": p.title, "year": p.year, "pass": p.pass_}


def node_detail(ix: MapIndex, slug: str) -> dict:
    """One broad node in full: the summary, then the paper slices hanging directly on it,
    grouped by paper, with the lateral edges landing on it or on them."""
    b = ix.graph.broad[slug]
    out = node_summary(ix, slug)
    out["ancestors"] = ix.ancestors(slug)
    out["child_nodes"] = [node_summary(ix, c) for c in _sorted_kids(ix, slug)]
    if out["kind"] == "claim":
        out["meter"] = {"support": b.support, "contradict": b.contradict}
    contra = {l.target for l in ix.laterals_into(slug, deep=False) if l.sign == "contradicts"}
    groups: dict[str, list[dict]] = {}
    for h in ix.direct[slug]:
        row = {"ref": h.gid, "kind": h.slice.kind, "text": h.slice.text, "via": h.via,
               "edge": h.edge, "contradicted": h.gid in contra}
        if h.slice.kind == "question":
            row["answered_by"] = [_brief(ix, c) for c in ix.answered_by.get(h.gid, [])]
        groups.setdefault(h.citekey, []).append(row)
    out["attached"] = [{**_paper_head(ix.papers[ck]), "slices": rows}
                       for ck, rows in sorted(groups.items(), key=lambda kv: (
                           ix.papers[kv[0]].year or 0, kv[0]))]
    lats = ix.laterals_into(slug, deep=False)
    for sign, key in (("corroborates", "corroborating"), ("contradicts", "contradicting")):
        out[key] = [{**_brief(ix, l.source), "target": l.target}
                    for l in lats if l.sign == sign]
    return out


def _brief(ix: MapIndex, gid: str) -> dict:
    ck, s = ix.slices[gid] if gid in ix.slices else (gid.split(":", 1)[0], None)
    p = ix.graph.papers.get(ck)
    return {"ref": gid, "kind": s.kind if s else "", "text": s.text if s else "",
            "year": p.year if p else None, "pass": p.pass_ if p else None}


def paper_detail(ix: MapIndex, citekey: str, only: str | None = None) -> dict:
    """The reverse direction: which broad nodes each of a paper's slices reaches, and which
    are off the map — with, for an off-map slice, the broad nodes its own answers and
    lateral edges point toward (where it might be attached)."""
    p = ix.papers[citekey]
    on, off = [], []
    for s in p.slices:
        if only and s.id != only:
            continue
        gid = f"{citekey}:{s.id}"
        row = _slice_row(ix, citekey, s)
        row["via"] = sorted({v for h in ix.entries.get(gid, []) for v in h.via})
        if row["reaches"]:
            on.append(row)
        else:
            row["near"] = _near(ix, citekey, s)
            off.append(row)
    return {**_paper_head(p), "tags": list(p.tags), "on": on, "off": off,
            "counts": _counts(ix, [p])}


def _near(ix: MapIndex, ck: str, s: Slice) -> list[dict]:
    out: list[dict] = []
    for edge in ("answers", "corroborates", "contradicts"):
        for r in getattr(s, edge):
            if r in ix.graph.broad:
                out.append({"edge": edge, "target": r, "enters": [r]})
            elif ix.enters(_gid(ck, r)):
                out.append({"edge": edge, "target": _gid(ck, r), "enters": ix.enters(_gid(ck, r))})
    if s.kind == "question":
        for c in ix.answered_by.get(f"{ck}:{s.id}", []):
            out.append({"edge": "answered_by", "target": c, "enters": ix.enters(c)})
    return out


def _counts(ix: MapIndex, papers: list[Paper]) -> dict:
    out = {k: {"attached": 0, "total": 0} for k in KINDS}
    for p in papers:
        for s in p.slices:
            if s.kind not in out:
                continue
            out[s.kind]["total"] += 1
            if f"{p.citekey}:{s.id}" in ix.entries:
                out[s.kind]["attached"] += 1
    return out


def totals(ix: MapIndex) -> dict:
    ps = list(ix.papers.values())
    on = [p for p in ps if any(f"{p.citekey}:{s.id}" in ix.entries for s in p.slices)]
    return {"papers": {"attached": len(on), "total": len(ps)}, **_counts(ix, ps)}


def off_report(ix: MapIndex) -> dict:
    """Curated papers with nothing on the map (by pass), papers only partly on it (by how
    much is left), and the attached/total totals."""
    off, partial = [], []
    for ck in sorted(ix.papers):
        p = ix.papers[ck]
        c = _counts(ix, [p])
        row = {**_paper_head(p), **{k: c[k]["total"] for k in KINDS}}
        if not any(c[k]["attached"] for k in KINDS):
            off.append(row)
            continue
        left = {k: c[k]["total"] - c[k]["attached"] for k in KINDS}
        if left["claim"] or left["question"]:
            partial.append({**_paper_head(p),
                            "unattached": left, "total": {k: c[k]["total"] for k in KINDS}})
    off.sort(key=lambda r: (-(r["pass"] if r["pass"] is not None else -1),
                            -(r["year"] or 0), r["citekey"]))
    partial.sort(key=lambda r: (-(r["unattached"]["claim"] + r["unattached"]["question"]),
                                r["citekey"]))
    return {"totals": totals(ix), "off": off, "partial": partial}


def find(ix: MapIndex, words: list[str]) -> dict:
    """Case-insensitive, every word must occur: broad nodes (slug, title, text) first, then
    paper slice texts."""
    ws = [w.lower() for w in words if w.strip()]

    def hit(*hay: str) -> bool:
        h = " ".join(x for x in hay if x).lower()
        return all(w in h for w in ws)

    broad = [node_summary(ix, s) for s, b in sorted(ix.graph.broad.items())
             if hit(s, b.title, b.text)]
    sl = [_slice_row(ix, ck, s) for gid, (ck, s) in ix.slices.items() if hit(s.text)]
    sl.sort(key=lambda r: (not r["reaches"], r["ref"]))
    return {"query": " ".join(words), "broad": broad, "slices": sl}


# --- text rendering ---------------------------------------------------------


def _width() -> int:
    return max(60, shutil.get_terminal_size((120, 24)).columns)


def _cut(s: str, n: int) -> str:
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: max(0, n - 1)] + "…"


def _label(b: dict) -> str:
    return b.get("title") or b.get("text") or ""


def _lat(d: dict) -> str:
    c, x = d.get("corroborate", {}).get("slices", 0), d.get("contradict", {}).get("slices", 0)
    return " ".join(([f"+{c}"] if c else []) + ([f"−{x}"] if x else []))


def format_tree(ix: MapIndex) -> str:
    W = _width()
    t = tree(ix)
    by = {d["slug"]: d for k in KINDS for d in t[k + "s"]}
    out: list[str] = []
    slugw = min(46, max([len(s) + 2 * _depth(ix, s) for s in by] + [20]) + 2)

    for kind in KINDS:
        nodes = t[kind + "s"]
        if not nodes:
            continue
        out.append("")
        if kind == "question":
            out.append(f"broad questions ({len(nodes)})   gathered questions · answered · "
                       "answering claims · papers")
        else:
            out.append(f"broad {kind}s ({len(nodes)})   papers · slices beneath (direct)"
                       + (" · +corroborating −contradicting slices" if kind == "claim" else ""))
        shown: set[str] = set()

        def line(slug: str, depth: int) -> None:
            d = by[slug]
            multi = len(d["parents"]) > 1
            repeat = slug in shown
            mark = (" ↑" if repeat else " ⇈") if multi else ""
            head = f"  {'  ' * depth}{slug}"
            if kind == "question":
                nums = (f"{d['questions']:>4}q {d['answered_questions']:>3}✓ "
                        f"{d['answering_claims']:>3}a {d['papers']:>4}p")
            else:
                nums = f"{d['papers']:>4}p {d['slices']:>4}s ({d['direct_slices']:>3})"
                if kind == "claim":
                    nums += f" {_lat(d):<7}"
            row = f"{head:<{slugw}}{nums}  "
            title = _label(d) + (" (children shown above)" if repeat and d["children"] else "")
            out.append(row + _cut(title, max(10, W - len(row) - len(mark))) + mark)
            if repeat:
                return
            shown.add(slug)
            for c in _sorted_kids(ix, slug):
                line(c, depth + 1)

        for r in _sorted(ix, ix.roots(kind)):
            line(r, 0)

    tot = t["totals"]
    out.append("")
    out.append("on the map: " + _totals_line(tot))
    out.append("⇈ = several parents, shown under each; ↑ = a repeat (its children appear once)."
               "  lit map <slug> · lit map <Citekey> · lit map --off · lit map --find <words>")
    return "\n".join(out).lstrip("\n") + "\n"


def _depth(ix: MapIndex, slug: str) -> int:
    ps = ix.graph.broad[slug].leads_to
    return 0 if not ps else 1 + max(_depth(ix, p) for p in ps)


def _pct(attached: int, total: int) -> str:
    a, n = attached, total
    return f"{a}/{n} ({100 * a / n:.0f}%)" if n else "0/0"


def _totals_line(tot: dict) -> str:
    return (f"papers {_pct(**tot['papers'])} · claims {_pct(**tot['claim'])} · "
            f"questions {_pct(**tot['question'])} · methods {_pct(**tot['method'])}")


def _wrap(s: str, indent: str, W: int, first: str | None = None) -> list[str]:
    return textwrap.wrap(" ".join((s or "").split()), width=max(40, W),
                         initial_indent=indent if first is None else first,
                         subsequent_indent=indent) or [indent]


def _route(r: dict) -> str:
    """`→ entry  ↑ above · above` — the entry nodes, then everything above them."""
    above = [s for s in r["reaches"] if s not in r["enters"]]
    return "→ " + ", ".join(r["enters"]) + (f"  (above: {' · '.join(above)})" if above else "")


def _pp(year, pass_) -> str:
    return f"{year if year is not None else '?'}, pass {pass_ if pass_ is not None else '?'}"


def format_node(ix: MapIndex, slug: str) -> str:
    W = _width()
    d = node_detail(ix, slug)
    out = [f"broad {d['kind']}  {slug}"]
    if d["title"]:
        out.append(f"  {d['title']}")
    out += _wrap(d["text"], "    ", W)
    out.append("")
    out.append(f"  parents   : {', '.join(d['parents']) or '— (a root)'}")
    if len(d["ancestors"]) > len(d["parents"]):
        out.append(f"  above     : {' · '.join(d['ancestors'])}")
    if d["child_nodes"]:
        out.append("  children  :")
        cw = max(len(c["slug"]) for c in d["child_nodes"])
        for c in d["child_nodes"]:
            head = f"    {c['slug']:<{cw}} {c['papers']:>4}p {c['slices']:>4}s  "
            out.append(head + _cut(_label(c), max(10, W - len(head))))
    else:
        out.append("  children  : —")
    line = (f"  beneath   : {d['papers']} papers, {d['slices']} slices; directly "
            f"{d['direct_papers']} papers, {d['direct_slices']} slices")
    out.append(line)
    if d["kind"] == "claim":
        out.append(f"  lateral   : +{d['corroborate']['slices']} corroborating, "
                   f"−{d['contradict']['slices']} contradicting slices beneath "
                   f"(meter: {d['meter']['support']} support, {d['meter']['contradict']} contradict)")
    if d["kind"] == "question":
        state = "answered" if d["answered"] else "open"
        out.append(f"  state     : {state} — {d['answered_questions']} of {d['questions']} gathered "
                   f"questions answered, {d['answering_claims']} answering claims")

    out.append("")
    out.append(f"  attached directly ({d['direct_slices']} slices, {d['direct_papers']} papers)")
    for grp in d["attached"]:
        out.append(f"    {grp['citekey']}  ({_pp(grp['year'], grp['pass'])})  "
                   + _cut(grp["title"], max(10, W - 30 - len(grp["citekey"]))))
        for r in grp["slices"]:
            tags = []
            if r["via"]:
                tags.append("via " + " › ".join(r["via"]))
            if r["edge"] == "answers":
                tags.append("answers it")
            if r["contradicted"]:
                tags.append("CONTRADICTED")
            tail = f"  [{'; '.join(tags)}]" if tags else ""
            sid = r["ref"].split(":", 1)[1]
            out += _wrap(r["text"] + tail, " " * 12, W, first=f"      {sid:<5} ")
            for a in r.get("answered_by", []):
                out += _wrap(f"← {a['ref']}  {a['text']}", " " * 12, W)
    if not d["attached"]:
        out.append("    —")
    if d["children"]:
        out.append(f"    (+ {d['slices'] - d['direct_slices']} more beneath the children: "
                   "lit map <child>)")
    for key, label in (("contradicting", "contradicting"), ("corroborating", "corroborating")):
        if d[key]:
            out.append("")
            out.append(f"  {label} ({len(d[key])})")
            for r in d[key]:
                tgt = "it" if r["target"] == slug else r["target"]
                out += _wrap(f"{r['ref']}  ({_pp(r['year'], r['pass'])})  {r['text']}  [→ {tgt}]",
                             "    ", W)
    return "\n".join(out) + "\n"


def format_paper(ix: MapIndex, citekey: str, only: str | None = None) -> str:
    W = _width()
    d = paper_detail(ix, citekey, only)
    out = [f"{citekey}  ({_pp(d['year'], d['pass'])})  {d['title']}"]
    c = d["counts"]
    out.append("  on the map: " + " · ".join(f"{k}s {c[k]['attached']}/{c[k]['total']}"
                                             for k in KINDS))
    for key, label in (("on", "on the map"), ("off", "off the map")):
        rows = d[key]
        if not rows:
            continue
        out.append("")
        out.append(f"  {label} ({len(rows)})")
        for r in rows:
            sid = r["ref"].split(":", 1)[1]
            head = f"    {sid:<5} {r['kind'][0]}  "
            out.append(head + _cut(r["text"], max(10, W - len(head))))
            if r["reaches"]:
                via = f"  (via {', '.join(r['via'])})" if r["via"] else ""
                out += _wrap(_route(r) + via, " " * 13, W)
            for n in r.get("near", []):
                tail = (f" → {', '.join(n['enters'])}"
                        if n["enters"] and n["enters"] != [n["target"]] else "")
                out += _wrap(f"~ {n['edge'].replace('_', ' ')} {n['target']}{tail}", " " * 13, W)
    return "\n".join(out) + "\n"


def format_off(ix: MapIndex, scope: str = "") -> str:
    W = _width()
    r = off_report(ix)
    out = [f"off the map{scope}: {len(r['off'])} of {r['totals']['papers']['total']} curated "
           "papers have no slice on any broad node"]
    kw = max([len(x["citekey"]) for x in r["off"] + r["partial"]] + [12])
    by_pass: dict = {}
    for row in r["off"]:
        by_pass.setdefault(row["pass"], []).append(row)
    for ps, rows in by_pass.items():
        out.append("")
        out.append(f"  pass {ps if ps is not None else '?'} ({len(rows)})")
        for row in rows:
            head = (f"    {row['citekey']:<{kw}} {row['year'] or '?':>4}  "
                    f"{row['claim']:>3}c {row['question']:>2}q {row['method']:>2}m  ")
            out.append(head + _cut(row["title"], max(10, W - len(head))))
    if r["partial"]:
        out.append("")
        out.append(f"  partly on the map ({len(r['partial'])}) — unattached / total")
        for row in r["partial"]:
            u, t = row["unattached"], row["total"]
            head = (f"    {row['citekey']:<{kw}} {_pp(row['year'], row['pass']):<14} "
                    f"claims {u['claim']:>3}/{t['claim']:<3}  questions {u['question']:>2}/"
                    f"{t['question']:<2}  methods {u['method']:>2}/{t['method']:<2}")
            out.append(head)
    out.append("")
    out.append("on the map: " + _totals_line(r["totals"]))
    return "\n".join(out) + "\n"


def format_find(ix: MapIndex, words: list[str], limit: int = 40) -> str:
    W = _width()
    r = find(ix, words)
    out = [f"broad nodes matching {r['query']!r} ({len(r['broad'])})"]
    bw = max([len(b["slug"]) for b in r["broad"]] + [16])
    for b in r["broad"]:
        head = f"    {b['slug']:<{bw}} {b['kind'][0]} {b['papers']:>3}p  "
        out.append(head + _cut(_label(b), max(10, W - len(head))))
    out.append("")
    n = len(r["slices"])
    out.append(f"paper slices matching ({n}" + (f", first {limit}" if n > limit else "") + ")")
    rw = max([len(s["ref"]) for s in r["slices"][:limit]] + [16])
    for s in r["slices"][:limit]:
        head = f"    {s['ref']:<{rw}} {s['kind'][0]}  "
        out.append(head + _cut(s["text"], max(10, W - len(head))))
        out += _wrap(_route(s) if s["reaches"] else "(off the map)", " " * 8, W)
    return "\n".join(out) + "\n"
