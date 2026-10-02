# litgraph/build.py
"""Emit layer: serialize a Graph to inlined JSON and write the self-contained viewer."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from litgraph.graph import Aim, BuildError, Graph, Paper, Slice, classify_ref
from litgraph.topics import keyword_closure, papers_in
from litgraph.topics import roots as topic_roots


def _up(s: Slice) -> list[str]:
    """Within-paper support refs: the local slices this one is built on (grounded_in).
    These draw the substructure skeleton inside an expanded card (e.g. m3 builds on m2)."""
    return [r for r in s.grounded_in if classify_ref(r) == "local"]


def _gen(s: Slice) -> list[str]:
    """Same-paper generalization ladder: the broader local slice(s) this one ladders into
    (leads_to → local, validated same-kind). Broad slugs go to the synthesis band (_cons);
    these nest in place — the viewer renders this slice under its broader parent."""
    return [r for r in s.leads_to if classify_ref(r) == "local"]


def _grounds(p: Paper) -> list[dict]:
    """Left-column targets: each grounded_in ref that points at a container (a source paper).
    A sharpened ref keeps its target slice id in `tid` so the viewer can anchor the edge on
    that specific slice; a plain container ref carries tid=None (the wildcard, CONCEPT §2)."""
    out = []
    for s in p.slices:
        for r in s.grounded_in:
            if classify_ref(r) in ("container", "sharpened"):
                key, _, tid = r.partition(":")
                out.append({"key": key, "tid": tid or None, "via": s.id})
    return out


def _lateral(p: Paper) -> list[dict]:
    """Lateral stance edges. Paper targets emit {key, tid, sign, via} (tid = the specific
    slice for sharpened refs, else None); broad-slug targets emit {slug, sign, via} so the
    viewer routes them to the synthesis band, not a phantom paper card."""
    out = []
    for s in p.slices:
        for sign, refs in (("corr", s.corroborates), ("contra", s.contradicts)):
            for r in refs:
                kind = classify_ref(r)
                if kind == "broad":
                    out.append({"slug": r, "sign": sign, "via": s.id})
                elif kind == "local":
                    out.append({"key": p.citekey, "tid": r, "sign": sign, "via": s.id})
                else:
                    key, _, tid = r.partition(":")
                    out.append({"key": key, "tid": tid or None, "sign": sign, "via": s.id})
    return out


def _cons(p: Paper) -> list[dict]:
    """Right-band targets: each leads_to *broad slug*. A local leads_to is a same-paper
    generalization ladder that nests in place, not a synthesis node — skip it here."""
    out = []
    for s in p.slices:
        for slug in s.leads_to:
            if classify_ref(slug) == "broad":
                out.append({"slug": slug, "via": s.id})
    return out


def _answers(p: Paper) -> list[dict]:
    """Cross-paper answers edges: a claim answering a question in another container.
    Local refs are omitted (they nest in place via the slice's own `answers` list).
    A sharpened ref keeps the target question id in `tid`; a plain container ref is the
    wildcard (tid=None); a broad-question slug routes to the synthesis band ({slug})."""
    out = []
    for s in p.slices:
        for r in s.answers:
            kind = classify_ref(r)
            if kind == "broad":
                out.append({"slug": r, "via": s.id})
            elif kind in ("container", "sharpened"):
                key, _, tid = r.partition(":")
                out.append({"key": key, "tid": tid or None, "via": s.id})
    return out


def _builds(g: Graph) -> dict[str, list[dict]]:
    """Invert cross-paper grounding: for each curated paper, the (newer) curated papers
    that build on it — the viewer's rightward "builds-on" column. Each entry names the
    building paper (`key`), its building slice (`via`), and — for a sharpened ref — the
    grounded slice of *this* paper (`tid`)."""
    idx: dict[str, list[dict]] = {}
    for q in g.papers.values():
        if not q.curated:
            continue
        for s in q.slices:
            for r in s.grounded_in:
                if classify_ref(r) not in ("container", "sharpened"):
                    continue
                key, _, tid = r.partition(":")
                target = g.papers.get(key)
                if target is not None and target.curated:
                    idx.setdefault(key, []).append(
                        {"key": q.citekey, "tid": tid or None, "via": s.id})
    return idx


def _local(refs: list[str]) -> list[str]:
    """The same-container refs in a list — the only ones a card can draw as nested rows."""
    return [r for r in refs if classify_ref(r) == "local"]


def _slice_json(s: Slice) -> dict:
    out = {"id": s.id, "kind": s.kind, "text": s.text, "color": s.color,
           "is_floor": s.is_floor, "grounded": s.grounded,
           "borrowed": s.borrowed, "answered": s.answered, "up": _up(s),
           "gen": _gen(s), "quote": s.quote, "qd": s.quote_display,
           "loc": s.quote_loc, "answers": list(s.answers)}
    # Programme fields ride along only when they carry something, so a literature card's
    # JSON is byte-identical to what it was before the programme layer existed.
    if s.kind == "test":
        out |= {"disc": _local(s.discriminates), "en": _local(s.enabled_by),
                "risk": s.at_risk}
    elif s.kind == "capability":
        out |= {"asp": s.aspirational}
    elif s.kind == "claim" and s.modality:
        out |= {"mod": s.modality, "lb": s.load_bearing, "br": s.blast_radius}
    return out


def _paper_json(p: Paper, builds: list[dict]) -> dict:
    return {
        "cur": p.curated, "pass": p.pass_, "type": p.type, "year": p.year,
        "curation_updated": p.curation_updated,
        "title": p.title, "authors": [[n, pos, corr] for n, pos, corr in p.authors],
        "tags": p.tags, "note": p.note, "abs": p.abstract, "head": p.head,
        "slices": [_slice_json(s) for s in p.slices],
        "grounds": _grounds(p), "lateral": _lateral(p), "cons": _cons(p),
        "ans": _answers(p), "builds": builds,
    }


def _aim_json(a: Aim, builds: list[dict]) -> dict:
    """An aim, serialized into the card shape the viewer already knows. `aim: True` is the
    one flag the template branches on — it swaps the entry groups from a paper's rhetoric
    (novel / borrowed / open) to a programme's (hypotheses / assumptions / tests)."""
    return {
        "cur": True, "aim": True, "pass": None, "type": "aim", "year": None,
        "title": a.title, "authors": [], "tags": a.tags, "note": a.note, "abs": None,
        "head": [s.text for s in a.slices if s.kind == "claim" and not s.leads_to],
        "slices": [_slice_json(s) for s in a.slices],
        "grounds": _grounds(a), "lateral": _lateral(a), "cons": _cons(a),
        "ans": _answers(a), "builds": builds,
    }


def _narrative_card_json(grant: str, n) -> dict:
    """A narrative (programme design §7, extended — narrative.py) serialized into the SAME card
    shape a paper or an aim gets, keyed `~<grant>`.

    It used to be a display-only blob — `{sections: [{bullets: [{text, refs}]}]}` — that the
    viewer drew as a static panel with each bullet's refs as inert chips. The chips were the
    defect. A bullet's citations are the one thing a reader wants to *follow*, and a chip is a
    dead end everywhere else in this viewer draws an arrow. So a **bullet becomes a slice** and
    its **refs become the ordinary `grounds` / `cons` edges** every other container emits; that
    alone is enough for the narrative to read the way a paper's card reads — open it, and each
    sentence has arrows running to the cards it rests on.

    This is a rendering decision, not a schema one, and the design's §7 invariant is untouched:
    the shape is built here at emit time, never enters `g.papers` / `g.broad` / `g.aims`, and
    nothing emergent reads it. Deleting programme/narrative/ still leaves the computed graph
    byte-identical (tests/test_narrative.py holds exactly that).

    `sections` survives beside `slices` as pure ordering — which bullets stand under which
    headline. That IS the narrative's content (it is a linearization), and a support DAG has
    nowhere to put it: the bullets have no edges to each other at all.
    """
    slices, grounds, cons, sections = [], [], [], []
    for i, sec in enumerate(n.sections, 1):
        ids = []
        for j, b in enumerate(sec.bullets, 1):
            sid = f"s{i}b{j}"
            ids.append(sid)
            slices.append({"id": sid, "kind": "bullet", "text": b.text, "color": "narrative",
                           "is_floor": False, "grounded": bool(b.refs), "borrowed": False,
                           "answered": False, "up": [], "gen": [], "quote": None, "qd": None,
                           "loc": None, "answers": [], "nref": len(b.refs)})
            for r in b.refs:
                if classify_ref(r) == "broad":
                    cons.append({"slug": r, "via": sid})
                else:                                   # container | sharpened (local is invalid)
                    key, _, tid = r.partition(":")
                    grounds.append({"key": key, "tid": tid or None, "via": sid})
        sections.append({"title": sec.title, "bullets": ids})
    return {
        "cur": True, "narr": True, "pass": None, "type": "narrative", "year": None,
        "title": n.title or grant, "authors": [], "tags": [], "note": None, "abs": None,
        "head": [], "budget": n.page_budget, "sections": sections,
        "slices": slices, "grounds": grounds, "lateral": [], "cons": cons,
        "ans": [], "builds": [],
    }


def _narrative_json(g: Graph) -> dict:
    """`{"~<grant>": card}` — the narrative layer as cards (see _narrative_card_json). Keyed with
    the `~` sigil for the same reason an aim is keyed with `@`: one namespace for everything a
    card can be, and a glance at a key says which kind it names."""
    return {f"~{grant}": _narrative_card_json(grant, n) for grant, n in g.narrative.items()}


def _topics_json(g: Graph) -> dict:
    """The topic axis (SCHEMA §9), reduced to what the viewer needs to run a saved search —
    it must never re-walk `broader` itself. `keywords` is the full closure (own + everything
    beneath via `broader`), not just the topic's own list, and `papers` is already filtered to
    curated citekeys (`papers_in` gates on that). `{}` when the repo has no topics/ tree, so a
    viewer built against such a repo renders exactly as it did before this axis existed."""
    root_slugs = set(topic_roots(g.topics))
    return {slug: {"title": t.title, "note": t.note or "", "broader": list(t.broader),
                   "keywords": sorted(keyword_closure(g.topics, slug)),
                   "papers": papers_in(g.topics, slug, g.papers),
                   "root": slug in root_slugs}
            for slug, t in g.topics.items()}


def to_json_dict(g: Graph, active: "tuple[str, ...]" = (),
                 include_aims: bool = False) -> dict:
    """Serialize the graph for the viewer. Aims — and the narrative axis that orders them —
    are **off by default**: the landing view is paper-centric (it sorts by pass / year /
    authors, none of which an aim has), so they are not papers and must not stand among them.

    With the flag on they ride in the payload but claim **no place on the board**: `order` is
    built from papers alone, so nothing puts a programme card in the landing column. They are
    reached by asking for them — the HUD's programme pill opens one aim, or a whole proposal
    (`preview.isolate_proposal`), on its own page. That is a reversal: they used to render as a
    standing "programme lane" left of the landing column, which put a grant's argument in front
    of a reader who came to browse the literature. See docs/2026-08-02-programme-graph-design.md.

    One flag for both axes — they are the same "the programme layer" toggle — and a repo with
    neither carries no cost either way (`g.aims`/`g.narrative` empty → nothing added)."""
    builds = _builds(g)
    curated = {ck: _paper_json(p, builds.get(ck, [])) for ck, p in g.papers.items() if p.curated}
    if include_aims:
        curated |= {slug: _aim_json(a, builds.get(slug, [])) for slug, a in g.aims.items()}
    stubs = {ck: {"title": p.title, "year": p.year, "type": p.type, "doi": p.doi,
                  "journal": p.journal,
                  "authors": [[n, pos, corr] for n, pos, corr in p.authors]}
             for ck, p in g.papers.items() if not p.curated}
    broad = {slug: {"kind": b.kind, "title": b.title, "text": b.text,
                    "meter": ({"s": b.support, "c": b.contradict}
                              if b.kind == "broad claim" else None),
                    "leads_to": list(b.leads_to)}
             for slug, b in g.broad.items()}
    # `active` is the manual in-progress list (config.toml); keep only citekeys that are actually
    # curated papers, preserving the given order. Empty for static `lit build` (the WIP panel is
    # serve-only), so a shared artifact never carries the curator's private worklist.
    active_curated = [k for k in active if k in curated]
    # Unlike `active` above, topics carry no worklist or server state — they are public library
    # structure, so (per SCHEMA §9) they belong in both a static `lit build` and `lit serve` alike.
    out = {"papers": curated, "broad": broad, "stubs": stubs, "order": g.order,
           "active": active_curated, "topics": _topics_json(g)}
    # Narrative rides along with aims (see the flag's docstring above) and only when there is
    # one: a repo with no programme/narrative/ tree must not grow an empty key, matching every
    # other optional axis's "absent means absent" contract.
    if include_aims and g.narrative:
        out["narrative"] = _narrative_json(g)
    return out


_VIEWER = Path(__file__).parent / "viewer"
_SHELL = _VIEWER / "shell.html"
_PWA_ASSETS = ("manifest.webmanifest", "icon-192.png", "icon-512.png",
               "apple-touch-icon.png")
_TOKEN_START = "/*__GRAPH_JSON__*/"
_TOKEN_END = "/*__END__*/"
_CSS_MARK = "/*@LITGRAPH_CSS@*/"
_JS_MARK = "/*@LITGRAPH_JS@*/"


def _concat(subdir: str) -> str:
    """The viewer's `subdir` modules, in filename order, as one blob.

    The numeric filename prefixes ARE the load order — the viewer is one script
    in one scope (no imports, no bundler), so a module that reads another's const
    at parse time must come after it. Renaming a file renumbers its position.
    Each file stores its slice plus one trailing newline; dropping that newline
    and rejoining with "\\n" is exactly the inverse of the split."""
    files = sorted((_VIEWER / subdir).glob(f"*.{subdir}"))
    if not files:
        raise BuildError(f"viewer/{subdir}/ has no modules — the install is incomplete")
    return "\n".join(f.read_text(encoding="utf-8")[:-1] for f in files)


def template_html() -> str:
    """The viewer page with its modules inlined and the graph slot still empty.

    The shipped artifact is one self-contained file with no external requests
    (it has to open from file:// and from a phone with no network), so the split
    into viewer/css/ + viewer/js/ is a *source* split that this reassembles."""
    shell = _SHELL.read_text(encoding="utf-8")
    for mark, sub in ((_CSS_MARK, "css"), (_JS_MARK, "js")):
        if mark not in shell:
            raise BuildError(f"viewer/shell.html has lost its {mark} marker")
        shell = shell.replace(mark, _concat(sub))
    return shell


def render_html(payload: str) -> str:
    """The self-contained viewer page for a graph.json payload (JSON inlined).
    Escapes "<" so a "</script>" inside any paper's text can't close the tag;
    \\u003c is a valid JS string escape that parses back to "<"."""
    inline = payload.replace("<", "\\u003c")
    template = template_html()
    start = template.index(_TOKEN_START)
    end = template.index(_TOKEN_END) + len(_TOKEN_END)
    return template[:start] + inline + template[end:]


def emit(g: Graph, out: Path) -> None:
    """Write graph.json and a self-contained index.html (JSON inlined) into `out`.

    `include_aims=True`: `lit build`'s shared artifact carries the programme lane (aims +
    narrative) alongside the paper board (to_json_dict's own docstring has the reasoning).
    The paper-centric `order`/landing sort is untouched either way — that list is built from
    `g.papers` alone and was never a function of this flag."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(to_json_dict(g, include_aims=True), ensure_ascii=False)
    (out / "graph.json").write_text(payload, encoding="utf-8")
    (out / "index.html").write_text(render_html(payload), encoding="utf-8")
    for name in _PWA_ASSETS:
        shutil.copy2(_VIEWER / name, out / name)
