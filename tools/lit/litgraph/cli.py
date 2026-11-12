"""`lit` command-line entry point."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from .config import load_config
from .ingest import IngestError, Report, ingest
from .graph import build_graph, BuildError
from .build import emit
from .preview import build_preview_graph, emit_preview
from .quotes import polish_graph, verify_quote_locs_graph
from .serve import parse_allowed_hosts, serve


def _slug(kw: str) -> str:
    """A keyword phrase → kebab tag, matching the repo's lowercase-hyphen tag convention."""
    s = re.sub(r"[^\w\s-]", "", kw.lower())
    return re.sub(r"[\s_-]+", "-", s).strip("-")


def _print_report(r: Report) -> None:
    tag = "DRY-RUN — nothing written" if r.dry_run else "written"
    print(f"\n=== lit ingest ({tag}) ===")
    print(f"  PDF        : {r.pdf}")
    srcnote = f"; metadata via {r.metadata_source}" if r.metadata_source == "crossref" else ""
    print(f"  DOI        : {r.doi}  (via {r.doi_source}{srcnote})")
    if r.title_search_unverified:
        print("  ⚠ DOI resolved by TITLE SEARCH — verify the match is the right paper.")
    if r.metadata_source == "crossref":
        print("  ⚠ focal not in OpenAlex — metadata + references via Crossref; "
              "DOI-less refs (books) and DataCite deposits (datasets) are not auto-resolved.")
    print(f"  citekey    : {r.citekey}")
    print(f"  title      : {r.title}")
    typenote = " (defaulted — review)" if r.type_defaulted else ""
    print(f"  type       : {r.type}{typenote}")
    print(f"  year       : {r.year}")
    print(f"  venue      : {r.venue_display!r} -> {r.venue_token!r}")
    print("  authors:")
    for a in r.authors:
        roles = []
        if a.position:
            roles.append(a.position)
        if a.corresponding:
            roles.append("corresponding")
        print(f"    - {a.name}" + (f"  [{', '.join(roles)}]" if roles else ""))
    refnote = ""
    if r.n_referenced and r.n_referenced != r.n_refs:
        refnote = f" of {r.n_referenced} referenced ({r.n_referenced - r.n_refs} not resolved)"
    print(f"  references : {r.n_refs} fetched{refnote} | {len(r.stubs_added)} new stubs | "
          f"{len(r.stubs_deduped)} deduped | {r.refs_skipped} skipped")
    if r.refs_from_fulltext:
        print("  ⚠ neither OpenAlex nor Crossref carries this paper's reference list — DOIs read "
              "off the printed list in the PDF. References that print no DOI are not recovered.")
    if r.stubs_pruned:
        print(f"  promoted   : {', '.join(r.stubs_pruned)} (stub -> curated, dropped from stubs.yaml)")
    if r.stubs_only:
        print(f"  curated    : {r.curated_path}  (stubs-only run — left untouched)")
        for w in r.warnings:
            print(f"  ⚠ {w}")
        print()
        return
    print(f"  abstract   : {r.abstract_source or 'NONE — see the warning below'}")
    print(f"  curated    : {r.curated_path}")
    if r.pdf_renamed_to:
        print(f"  pdf -> {r.pdf_renamed_to}")
    if r.pdf_rename_skipped:
        print("  pdf rename : SKIPPED (target exists)")
    print(f"  fulltext   : {r.fulltext_path}")
    for w in r.warnings:
        print(f"  ⚠ {w}")
    print()


_DOI = re.compile(r"^(?:doi:|https?://(?:dx\.)?doi\.org/)?(10\.\d{4,9}/\S+)$", re.IGNORECASE)


def _collection(args) -> int:
    """`lit collection` — SCHEMA §10. Every write goes through collection.py (round-tripped,
    comments intact), and a DOI not yet in the library is minted as a stub first, so the
    collection never lists a key the build cannot resolve."""
    import datetime as dt
    from . import collection as colmod
    from .graph import load_repo
    cfg = load_config(args.root)
    action = args.action or "list"

    def keys_by_doi() -> dict[str, str]:
        from .store import load_taken
        from .citekey import _norm_doi
        return {_norm_doi(d): k for k, d in load_taken(cfg.root).items() if d}

    def label(papers, k) -> str:
        p = papers.get(k)
        if p is None:
            return f"{k}  (not in the library)"
        tier = "curated" if p.curated else "stub   "
        return f"{tier}  {k}  {p.title or ''}"

    try:
        if action == "new":
            slug = args.slug or colmod.slugify(args.title)
            date = dt.date.today().isoformat() if args.date is None else (args.date or None)
            papers, broad = load_repo(cfg.root)
            from .topics import load_topics
            if slug in broad or slug in papers or slug in load_topics(cfg.root):
                print(f"error: slug {slug!r} already names a broad slice, topic or paper — "
                      f"pass --slug", file=sys.stderr)
                return 1
            path = colmod.create(cfg.root, slug, args.title, note=args.note, date=date)
            print(f"collection → {slug} created ({path})")
            print(f"  add papers:  lit collection add {slug} <citekey|doi> ...")
            return 0

        if action == "add":
            if args.slug not in colmod.load_collections(cfg.root):
                print(f"error: no such collection: {args.slug} (create it with "
                      f"`lit collection new`)", file=sys.stderr)
                return 1
            from .ingest import IngestError, stub_for_doi
            papers, _ = load_repo(cfg.root)
            keys, failed, minted = [], [], []
            for ref in args.refs:
                m = _DOI.match(ref.strip())
                if ref in papers:
                    keys.append(ref)
                elif m:
                    try:
                        r = stub_for_doi(m.group(1), root=cfg.root, mailto=cfg.mailto,
                                         dry_run=args.dry_run)
                    except IngestError as e:
                        failed.append(f"{ref}: {e}")
                        continue
                    keys.append(r.citekey)
                    if r.created:
                        minted.append(r.citekey)
                        print(f"  + stub {r.citekey}  {r.title}  (via {r.source})")
                    else:
                        print(f"  = {ref} is already {r.citekey}")
                else:
                    failed.append(f"{ref}: not a citekey in the library, nor a DOI")
            if args.dry_run:
                print(f"DRY-RUN — would add {len(keys)} to {args.slug}: {', '.join(keys) or '-'}")
            elif keys:
                added, now = colmod.edit_papers(cfg.root, args.slug, add=keys)
                skipped = [k for k in keys if k not in added]
                print(f"collection → {len(added)} added to {args.slug}"
                      + (f" ({len(skipped)} already in it)" if skipped else "")
                      + (f", {len(minted)} new stub{'' if len(minted) == 1 else 's'}" if minted else "")
                      + f"  |  now {len(now)} paper{'' if len(now) == 1 else 's'}")
            for f in failed:
                print(f"  ⚠ {f}", file=sys.stderr)
            return 1 if failed else 0

        if action == "remove":
            if args.slug not in colmod.load_collections(cfg.root):
                print(f"error: no such collection: {args.slug}", file=sys.stderr)
                return 1
            by_doi = keys_by_doi()
            from .citekey import _norm_doi
            keys = []
            for ref in args.refs:
                m = _DOI.match(ref.strip())
                keys.append(by_doi.get(_norm_doi(m.group(1)), ref) if m else ref)
            removed, now = colmod.edit_papers(cfg.root, args.slug, remove=keys)
            missing = [k for k in keys if k not in removed]
            print(f"collection → {len(removed)} removed from {args.slug}  |  now "
                  f"{len(now)} paper{'' if len(now) == 1 else 's'}")
            for k in missing:
                print(f"  ⚠ {k}: not in {args.slug}", file=sys.stderr)
            return 1 if missing else 0

        cols = colmod.load_collections(cfg.root)
        papers, _ = load_repo(cfg.root)
        if action == "show":
            c = cols.get(args.slug)
            if c is None:
                print(f"error: no such collection: {args.slug}", file=sys.stderr)
                return 2
            ncur = sum(1 for k in c.papers if k in papers and papers[k].curated)
            print(f"{c.title}  [{args.slug}]" + (f"  {c.date}" if c.date else "")
                  + f"  — {ncur} curated, {len(c.papers) - ncur} stub/other")
            if c.note:
                print(f"  {c.note}")
            for k in c.papers:
                print(f"    {label(papers, k)}")
            return 0

        if not cols:
            print(f"no collections/ under {cfg.root}  (create one: lit collection new \"<title>\")")
            return 0
        for slug, c in sorted(cols.items(), key=lambda kv: (kv[1].date or "", kv[0]), reverse=True):
            ncur = sum(1 for k in c.papers if k in papers and papers[k].curated)
            print(f"  {slug:<32} {c.date or '':<10}  {len(c.papers):>3} papers "
                  f"({ncur} curated)  {c.title}")
        return 0
    except colmod.CollectionError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def _map(args) -> int:
    """`lit map` — read-only, derived from the loaded graph alone (no PDF / quote checks)."""
    import json
    from . import broadmap as bm
    from .topics import papers_in
    cfg = load_config(args.root)
    try:
        graph = build_graph(cfg.root)
    except BuildError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    only: set[str] | None = None
    scope = ""
    if args.tag:
        t = args.tag.lower()
        only = {ck for ck, p in graph.papers.items()
                if p.curated and t in {x.lower() for x in p.tags}}
        scope += f" [tag {args.tag}]"
    if args.topic:
        if args.topic not in graph.topics:
            print(f"error: no such topic: {args.topic}", file=sys.stderr)
            return 2
        hits = set(papers_in(graph.topics, args.topic, graph.papers))
        only = hits if only is None else only & hits
        scope += f" [topic {args.topic}]"
    ix = bm.build_index(graph, only)

    def emit(data, text: str) -> int:
        if args.json:
            if scope:
                data = {"scope": {"tag": args.tag, "topic": args.topic}, **data}
            print(json.dumps(data, indent=1, ensure_ascii=False))
        else:
            print(text, end="")
        return 0

    if args.off:
        return emit(bm.off_report(ix), bm.format_off(ix, scope))
    if args.find:
        return emit(bm.find(ix, args.find), bm.format_find(ix, args.find, args.limit))
    ref = args.ref
    if not ref:
        return emit(bm.tree(ix), (f"scope:{scope}\n" if scope else "") + bm.format_tree(ix))
    if ref in graph.broad:
        return emit(bm.node_detail(ix, ref), bm.format_node(ix, ref))
    key, _, sid = ref.partition(":")
    p = graph.papers.get(key)
    if p is not None and not p.curated:
        print(f"error: {key} is a stub (not curated) — it has no slices to place", file=sys.stderr)
        return 2
    if p is not None and key not in ix.papers:
        print(f"error: {key} is outside the{scope} scope", file=sys.stderr)
        return 2
    if p is not None:
        if sid and sid not in {s.id for s in p.slices}:
            print(f"error: {key} has no slice {sid!r}", file=sys.stderr)
            return 2
        return emit(bm.paper_detail(ix, key, sid or None), bm.format_paper(ix, key, sid or None))
    print(f"error: {ref!r} is neither a broad slug nor a curated citekey "
          f"(try: lit map --find <words>)", file=sys.stderr)
    return 2


def _desk_scope(graph, args) -> tuple[set[str] | None, str] | int:
    """The citekeys `--collection` / `--topic` / `--tag` narrow the desk to, and a label for them;
    an int return is an exit code (an unknown collection or topic)."""
    from .topics import papers_in
    only: set[str] | None = None
    scope = ""

    def narrow(keys: set[str]) -> None:
        nonlocal only
        only = keys if only is None else only & keys

    if getattr(args, "collection", None):
        c = graph.collections.get(args.collection)
        if c is None:
            print(f"error: no such collection: {args.collection}", file=sys.stderr)
            return 2
        narrow(set(c.papers))
        scope += f" [collection {args.collection}]"
    if getattr(args, "topic", None):
        if args.topic not in graph.topics:
            print(f"error: no such topic: {args.topic}", file=sys.stderr)
            return 2
        narrow(set(papers_in(graph.topics, args.topic, graph.papers)))
        scope += f" [topic {args.topic}]"
    if getattr(args, "tag", None):
        t = args.tag.lower()
        narrow({ck for ck, p in graph.papers.items()
                if p.curated and t in {x.lower() for x in p.tags}})
        scope += f" [tag {args.tag}]"
    return only, scope


def _desk(args) -> int:
    """`lit desk` — read-only, derived from the loaded graph alone (no PDF / quote checks)."""
    import json
    from . import desk as dk
    cfg = load_config(args.root)
    try:
        graph = build_graph(cfg.root)
    except BuildError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    narrowed = _desk_scope(graph, args)
    if isinstance(narrowed, int):
        return narrowed
    only, scope = narrowed
    groups = dk.desk(graph.papers, only)
    if args.json:
        data = {"new": [r.as_json() for r in groups["new"]],
                "changed": [r.as_json() for r in groups["changed"]],
                "total": len(groups["new"]) + len(groups["changed"])}
        if scope:
            data = {"scope": {"collection": args.collection, "topic": args.topic,
                              "tag": args.tag}, **data}
        print(json.dumps(data, indent=1, ensure_ascii=False))
    else:
        print(dk.format_desk(groups, scope), end="")
    return 0


def _validate(args) -> int:
    """`lit validate` — the owner records the pass they have validated (SCHEMA §4)."""
    from . import store
    from .desk import desk as desk_of, label
    cfg = load_config(args.root)
    scoped = args.all or args.collection
    if scoped and args.citekeys:
        print("error: name citekeys or a scope (--all / --collection), not both", file=sys.stderr)
        return 2
    if scoped and args.level is not None:
        print("error: --pass applies to named papers; --all / --collection validate each "
              "paper at its own current pass", file=sys.stderr)
        return 2
    if not scoped and not args.citekeys:
        print("error: name a citekey, or validate a scope with --all / --collection",
              file=sys.stderr)
        return 2
    keys = list(args.citekeys)
    if scoped:
        # the desk needs the graph (collections resolve against it); named papers do not, so a
        # library mid-edit elsewhere never stops the owner validating the paper they just read
        try:
            graph = build_graph(cfg.root)
        except BuildError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        narrowed = _desk_scope(graph, args)
        if isinstance(narrowed, int):
            return narrowed
        groups = desk_of(graph.papers, narrowed[0])
        keys = [r.citekey for r in groups["new"] + groups["changed"]]
    tag = "DRY-RUN — nothing written" if args.dry_run else "written"
    changed, failed = 0, 0
    for k in keys:
        try:
            v = store.set_validated(cfg.root, k, args.level, dry_run=args.dry_run)
        except FileNotFoundError as e:
            print(f"error: {e}", file=sys.stderr)
            failed += 1
            continue
        before = "new" if v.old is None else f"validated {v.old}"
        ahead = f"  (above curated {v.pass_})" if v.new > v.pass_ else ""
        if v.changed:
            changed += 1
            print(f"  {k}: {before} → validated {label(v.new)}{ahead}")
        else:
            print(f"  {k}: already validated {label(v.new)}")
    print(f"lit validate ({tag}): {changed} changed, {len(keys) - changed - failed} unchanged"
          + (f", {failed} not curated" if failed else ""))
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lit", description="literature_graph tools")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ing = sub.add_parser("ingest", help="initialize a paper node + citation stubs from a PDF")
    p_ing.add_argument("pdf", help="path to the paper PDF")
    p_ing.add_argument("--doi", help="override the focal DOI (skips PDF extraction)")
    p_ing.add_argument("--root", default=".", help="data root holding curated/ and stubs.yaml (default: .)")
    p_ing.add_argument("--dry-run", action="store_true", help="print the plan; write/rename nothing")
    p_ing.add_argument("--force", action="store_true", help="overwrite an existing curated/<citekey>.yaml")
    p_ing.add_argument("--stubs-only", action="store_true",
                       help="backfill citation stubs for an already-ingested paper: merge stubs and "
                            "leave curated/<citekey>.yaml, the PDF and the .md untouched")

    p_build = sub.add_parser("build", help="build the static graph viewer from a data repo")
    p_build.add_argument("--root", default=".", help="data root (curated/, stubs.yaml, ...)")
    p_build.add_argument("--out", default=None,
                         help="output dir (default: <root>/dist)")

    p_prev = sub.add_parser("preview", help="render one paper's local subgraph in isolation "
                                            "(curation: see a proposition as it'll look)")
    p_prev.add_argument("citekey", nargs="?",
                        help="focal paper citekey, an aim as \"@<slug>\", or a whole proposal "
                             "as \"~<grant>\" (default: --scratch file stem)")
    p_prev.add_argument("--scratch", default=None,
                        help="a curated-schema YAML to overlay as the focal paper (or an "
                             "aim-schema YAML with an \"@<slug>\" key) — propose before "
                             "tokenizing into curated/ or programme/aims/")
    p_prev.add_argument("--root", default=".", help="data root (curated/, stubs.yaml, ...)")
    p_prev.add_argument("--out", default=None, help="output dir (default: <root>/dist)")
    p_prev.add_argument("--pdf-dir", default=None,
                        help="dir holding <citekey>.md for quote polishing "
                             "(default: config.toml pdf_dir, else <root>/pdfs)")

    p_loc = sub.add_parser("locate", help="resolve each curated quote's place in its PDF and "
                                          "store it as quote_loc (full-coverage highlight anchors)")
    p_loc.add_argument("--root", default=".", help="data root (curated/, stubs.yaml, ...)")
    p_loc.add_argument("--pdf-dir", default=None,
                       help="dir holding <citekey>.pdf files "
                            "(default: config.toml pdf_dir, else <root>/pdfs)")
    p_loc.add_argument("--force", action="store_true",
                       help="re-resolve quotes that already have a quote_loc (default: keep them)")
    p_loc.add_argument("--dry-run", action="store_true", help="report what would be located; write nothing")

    p_srv = sub.add_parser("serve", help="serve the viewer over HTTP: rebuild on refresh, "
                                         "PDF hover-preview and click-to-open")
    p_srv.add_argument("--root", default=".", help="data root (curated/, stubs.yaml, ...)")
    p_srv.add_argument("--host", default="127.0.0.1",
                       help="bind address (default: 127.0.0.1)")
    p_srv.add_argument("--port", type=int, default=8000, help="port (default: 8000)")
    p_srv.add_argument("--pdf-dir", default=None,
                       help="dir holding <citekey>.pdf files "
                            "(default: config.toml pdf_dir, else <root>/pdfs)")
    p_srv.add_argument("--read-only", action="store_true",
                       help="refuse the endpoints that write the repo or spawn an agent "
                            "(for a mirror serving a checkout it does not author)")
    p_srv.add_argument("--allow-host", action="append", default=[], metavar="NAME[:PORT]",
                       help="also answer requests whose Host header is NAME (repeatable). "
                            "Loopback names are always allowed; add the public name of a "
                            "reverse proxy in front of a loopback bind. Also read from "
                            "LIT_ALLOWED_HOSTS (comma-separated) and config.toml allowed_hosts")

    p_enr = sub.add_parser("enrich", help="backfill authors + journal onto existing stubs.yaml "
                                          "entries from OpenAlex (by DOI)")
    p_enr.add_argument("--root", default=".", help="data root (curated/, stubs.yaml, config.toml)")
    p_enr.add_argument("--force", action="store_true",
                       help="re-fetch stubs that already have authors + journal (overwrite them)")
    p_enr.add_argument("--dry-run", action="store_true", help="report what would change; write nothing")

    p_abs = sub.add_parser("abstracts", help="backfill missing abstracts onto curated papers from "
                                             "their stored full text (for the publishers that "
                                             "deposit none to OpenAlex/Crossref)")
    p_abs.add_argument("citekeys", nargs="*", help="papers to fill (omit for every curated paper)")
    p_abs.add_argument("--root", default=".", help="data root (curated/, pdfs/, config.toml)")
    p_abs.add_argument("--dry-run", action="store_true", help="report what would change; write nothing")

    p_tag = sub.add_parser("tag", help="add / remove / list a curated paper's tags "
                                       "(free-form curator labels; searchable in the viewer)")
    p_tag.add_argument("citekey", help="curated paper to tag")
    p_tag.add_argument("tags", nargs="*", help="tag(s) to add (omit to just list the current tags)")
    p_tag.add_argument("--remove", action="store_true", help="remove the given tag(s) instead of adding")
    p_tag.add_argument("--suggest", action="store_true", help="propose tags from the paper's author-keyword "
                                                              "line (Pass 1); prints candidates, writes nothing")
    p_tag.add_argument("--root", default=".", help="data root (curated/, stubs.yaml, config.toml)")

    p_top = sub.add_parser("topics", help="report the topic axis (SCHEMA §9): the tree with paper "
                                          "counts, or one topic's papers; --orphans finds tags no "
                                          "topic files and keywords no paper carries")
    p_top.add_argument("slug", nargs="?",
                       help="one topic — list the papers it reaches (omit for the whole tree)")
    p_top.add_argument("--orphans", action="store_true",
                       help="report unfiled tags, dead keywords and stranded papers instead")
    p_top.add_argument("--strict", action="store_true",
                       help="exit non-zero if --orphans flags anything (for CI)")
    p_top.add_argument("--root", default=".", help="data root (topics/, curated/, ...)")

    p_col = sub.add_parser("collection", help="papers gathered for a purpose — a review, a grant, a "
                                              "talk (SCHEMA §10): create, add/remove papers, list")
    col = p_col.add_subparsers(dest="action")
    c_new = col.add_parser("new", help="create an empty collection")
    c_new.add_argument("title", help='what it is for, as you would search for it, e.g. "Batching review"')
    c_new.add_argument("--slug", default=None, help="file name stem (default: the title in kebab-case)")
    c_new.add_argument("--note", default=None, help="free-text gloss: what the papers were gathered for")
    c_new.add_argument("--date", default=None,
                       help="ISO date the collection is for (default: today; --date '' for none)")
    c_add = col.add_parser("add", help="add papers by citekey or DOI; a DOI not yet in the library "
                                       "becomes a new stub (OpenAlex, else Crossref)")
    c_add.add_argument("slug", help="the collection")
    c_add.add_argument("refs", nargs="+", help="citekeys and/or DOIs (10.xxxx/..., doi.org URLs)")
    c_add.add_argument("--dry-run", action="store_true",
                       help="resolve and report; write neither the collection nor stubs.yaml")
    c_rm = col.add_parser("remove", help="drop papers from a collection (the papers stay in the library)")
    c_rm.add_argument("slug", help="the collection")
    c_rm.add_argument("refs", nargs="+", help="citekeys and/or DOIs already in the collection")
    col.add_parser("list", help="every collection, newest first (the default)")
    c_show = col.add_parser("show", help="one collection's papers, curated and stubs")
    c_show.add_argument("slug", help="the collection")
    # --root is accepted before or after the action. SUPPRESS on the actions is what makes that
    # work: an action that sets no default leaves the value `lit collection --root X` put there.
    p_col.add_argument("--root", default=".", help="data root (collections/, curated/, stubs.yaml)")
    for c in col.choices.values():
        c.add_argument("--root", default=argparse.SUPPRESS,
                       help="data root (collections/, curated/, stubs.yaml)")

    p_prog = sub.add_parser("programme", help="report the programme graph's emergent state: "
                                              "load-bearing assumptions by blast radius, tests at "
                                              "risk, aspirational capabilities, open questions, orphans")
    p_prog.add_argument("--root", default=".", help="data root (programme/, curated/, ...)")
    p_prog.add_argument("--strict", action="store_true",
                        help="exit non-zero if anything is flagged (for CI)")

    p_map = sub.add_parser("map", help="read back the broad layer (claims/, questions/, methods/) "
                                       "and what hangs on it: the ladder, one node's papers, one "
                                       "paper's reach, what is off the map, a phrase finder")
    p_map.add_argument("ref", nargs="?",
                       help="a broad slug (that node and its papers), a curated <Citekey> (which "
                            "broad nodes its slices reach), or <Citekey>:<id> (one slice); omit "
                            "for the whole ladder")
    m_mode = p_map.add_mutually_exclusive_group()
    m_mode.add_argument("--off", action="store_true",
                        help="curated papers with no slice on the map (by pass), papers only "
                             "partly on it, and attached/total totals")
    m_mode.add_argument("--find", nargs="+", metavar="WORD",
                        help="case-insensitive match (every word): broad nodes first, then "
                             "paper slice texts")
    p_map.add_argument("--tag", default=None,
                       help="consider only curated papers carrying this tag")
    p_map.add_argument("--topic", default=None,
                       help="consider only curated papers this topic reaches (SCHEMA §9)")
    p_map.add_argument("--limit", type=int, default=40,
                       help="--find: paper slices listed in text mode (default 40; --json lists all)")
    p_map.add_argument("--json", action="store_true", help="machine-readable output, stable keys")
    p_map.add_argument("--root", default=".", help="data root (claims/, questions/, methods/, curated/)")

    p_desk = sub.add_parser("desk", help="the papers whose curation moved past what you validated: "
                                         "new (never validated) and changed (validated N, pass M)")
    p_desk.add_argument("--collection", default=None, help="only papers in this collection")
    p_desk.add_argument("--topic", default=None, help="only papers this topic reaches (SCHEMA §9)")
    p_desk.add_argument("--tag", default=None, help="only papers carrying this tag")
    p_desk.add_argument("--json", action="store_true", help="machine-readable output, stable keys")
    p_desk.add_argument("--root", default=".", help="data root (curated/, collections/, topics/)")

    p_val = sub.add_parser("validate", help="record the pass you have validated on a paper "
                                            "(the owner's number; agents never run this)")
    p_val.add_argument("citekeys", nargs="*", help="curated paper(s) to validate")
    p_val.add_argument("--pass", dest="level", type=int, default=None, choices=range(5),
                       metavar="N", help="validate at N (0–4) instead of the paper's current pass")
    v_scope = p_val.add_mutually_exclusive_group()
    v_scope.add_argument("--collection", default=None,
                         help="validate every paper of this collection that is on the desk")
    v_scope.add_argument("--all", action="store_true", help="validate every paper on the desk")
    p_val.add_argument("--dry-run", action="store_true", help="print what would change; write nothing")
    p_val.add_argument("--root", default=".", help="data root (curated/, collections/)")

    args = parser.parse_args(argv)

    if args.command == "ingest":
        if not Path(args.pdf).is_file():
            print(f"error: no such PDF: {args.pdf}", file=sys.stderr)
            return 2
        cfg = load_config(args.root)
        try:
            report = ingest(
                args.pdf,
                root=cfg.root,
                mailto=cfg.mailto,
                doi=args.doi,
                dry_run=args.dry_run,
                force=args.force,
                stubs_only=args.stubs_only,
            )
        except IngestError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        except FileExistsError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        _print_report(report)
        return 0

    if args.command == "build":
        cfg = load_config(args.root)
        out = Path(args.out) if args.out else cfg.root / "dist"
        pdf_dir = cfg.pdf_dir or cfg.root / "pdfs"
        try:
            graph = build_graph(cfg.root)
        except BuildError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        for w in polish_graph(graph, pdf_dir):
            print(f"quote-flag: {w}", file=sys.stderr)
        for w in verify_quote_locs_graph(graph, pdf_dir):
            print(f"quote-flag: {w}", file=sys.stderr)
        from .desk import flags as desk_flags
        for w in desk_flags(graph.papers):
            print(f"desk-flag: {w}", file=sys.stderr)
        emit(graph, out)
        print(f"built {len(graph.papers)} papers -> {out}/index.html")
        return 0

    if args.command == "topics":
        from .graph import load_repo
        from .topics import (TopicError, children, coverage, keyword_closure,
                             load_topics, papers_in, roots, validate_topics)
        cfg = load_config(args.root)
        papers, broad = load_repo(cfg.root)          # skips the full slice validate: topics
        topics = load_topics(cfg.root)               # are independent of the graph by design
        if not topics:
            print(f"no topics/ tree under {cfg.root}", file=sys.stderr)
            return 1
        try:
            validate_topics(topics, set(broad))
        except TopicError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1

        if args.orphans:
            unfiled, dead, stranded = coverage(topics, papers)
            for label, items, gloss in (
                ("unfiled tags", unfiled, "on a paper, in no topic — the topic layer is behind"),
                ("dead keywords", dead, "in a topic, on no paper — a typo or a renamed tag"),
                ("stranded papers", stranded, "curated, reached by no topic"),
            ):
                print(f"{label} ({len(items)}) — {gloss}")
                for i in items:
                    print(f"    {i}")
            return 1 if (args.strict and (unfiled or dead or stranded)) else 0

        if args.slug:
            if args.slug not in topics:
                print(f"error: no such topic: {args.slug}", file=sys.stderr)
                return 2
            hits = papers_in(topics, args.slug, papers)
            t = topics[args.slug]
            print(f"{t.title or args.slug} — {len(hits)} paper{'' if len(hits) == 1 else 's'}"
                  f"  [{', '.join(sorted(keyword_closure(topics, args.slug)))}]")
            for ck in hits:
                print(f"    {ck}  {papers[ck].title}")
            return 0

        kids = children(topics)
        seen: set[str] = set()

        def show(slug: str, depth: int) -> None:
            n = len(papers_in(topics, slug, papers))
            kw = len(keyword_closure(topics, slug))
            mark = " ↑" if len(topics[slug].broader) > 1 and slug in seen else ""
            print(f"  {'    ' * depth}{'· ' if depth else ''}{slug:<{36 - 4 * depth}}"
                  f"{n:>4} paper{' ' if n == 1 else 's'}  {kw:>3} keywords{mark}")
            seen.add(slug)
            for c in kids[slug]:
                show(c, depth + 1)

        for r in roots(topics):
            show(r, 0)
        ncur = sum(1 for p in papers.values() if p.curated)
        print(f"\n{len(topics)} topics over {ncur} curated papers "
              f"(a topic may appear under several parents; ↑ = repeat)")
        return 0

    if args.command == "preview":
        citekey = args.citekey or (Path(args.scratch).stem if args.scratch else None)
        if not citekey:
            print("error: give a citekey or --scratch <file>", file=sys.stderr)
            return 2
        cfg = load_config(args.root)
        out = Path(args.out) if args.out else cfg.root / "dist"
        pdf_dir = Path(args.pdf_dir) if args.pdf_dir else (cfg.pdf_dir or cfg.root / "pdfs")
        scratch = Path(args.scratch) if args.scratch else None
        if scratch is not None and not scratch.is_file():
            print(f"error: no such scratch file: {scratch}", file=sys.stderr)
            return 2
        try:
            graph = build_preview_graph(cfg.root, citekey, scratch)
        except BuildError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        for w in polish_graph(graph, pdf_dir):
            if w.startswith(f"{citekey}:"):        # only the focal paper's quote flags matter here
                print(f"quote-flag: {w}", file=sys.stderr)
        html = emit_preview(graph, citekey, out)
        print(f"preview {citekey} -> {html}")
        return 0

    if args.command == "locate":
        from ruamel.yaml import YAML
        from . import store
        from .serve import locate_quote
        cfg = load_config(args.root)
        pdf_dir = Path(args.pdf_dir) if args.pdf_dir else (cfg.pdf_dir or cfg.root / "pdfs")
        reader = YAML(typ="safe")
        located = papers = missing = 0
        for f in sorted((cfg.root / "curated").glob("*.yaml")):
            key = f.stem
            pdf = pdf_dir / f"{key}.pdf"
            if not pdf.is_file():
                continue
            doc = reader.load(f.read_text()) or {}
            locs: dict[str, dict] = {}
            for group in ("claims", "questions", "methods"):
                for s in doc.get(group, []) or []:
                    q = s.get("quote")
                    if not q or (s.get("quote_loc") and not args.force):
                        continue
                    loc = locate_quote(pdf, q)
                    if loc:
                        locs[s["id"]] = loc
                    else:
                        missing += 1
                        print(f"  ⚠ {key}:{s['id']} could not be located", file=sys.stderr)
            if locs:
                papers += 1
                located += len(locs)
                if not args.dry_run:
                    store.write_quote_locs(cfg.root, key, locs)
        tag = "DRY-RUN — nothing written" if args.dry_run else "written"
        print(f"lit locate ({tag}): {located} quote_loc across {papers} papers"
              + (f"; {missing} not located" if missing else ""))
        return 0

    if args.command == "serve":
        cfg = load_config(args.root)
        pdf_dir = Path(args.pdf_dir) if args.pdf_dir else (cfg.pdf_dir or cfg.root / "pdfs")
        try:
            build_graph(cfg.root)   # fail fast on a broken repo; later edits 500 per request
        except BuildError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        try:
            serve(cfg.root, pdf_dir, host=args.host, port=args.port,
                  read_only=args.read_only,
                  allowed_hosts=parse_allowed_hosts(cfg.allowed_hosts,
                                                    os.environ.get("LIT_ALLOWED_HOSTS", ""),
                                                    args.allow_host))
        except OSError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        return 0

    if args.command == "tag":
        from . import store
        cfg = load_config(args.root)
        if args.suggest:
            from .fulltext import extract_keywords
            pdf_dir = cfg.pdf_dir or cfg.root / "pdfs"
            md = pdf_dir / f"{args.citekey}.md"
            if not md.is_file():
                print(f"error: no full text to scan: {md}", file=sys.stderr)
                return 1
            kws = extract_keywords(md.read_text())
            if not kws:
                print(f"{args.citekey}: no author-keyword line found in the full text")
                return 0
            slugs = [_slug(k) for k in kws]
            print(f"author keywords ({len(kws)}): " + " · ".join(kws))
            print("  " + " ".join(["lit", "tag", args.citekey, *slugs]))
            return 0
        try:
            tags = store.edit_tags(cfg.root, args.citekey, args.tags, remove=args.remove)
        except FileNotFoundError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        shown = ", ".join(tags) if tags else "(no tags)"
        if not args.tags:
            print(f"{args.citekey}: {shown}")
        else:
            verb = "removed from" if args.remove else "added to"
            print(f"tag → {', '.join(args.tags)} {verb} {args.citekey}  |  now: {shown}")
        return 0

    if args.command == "collection":
        return _collection(args)

    if args.command == "programme":
        from .programme import format_report, report as programme_report
        cfg = load_config(args.root)
        try:
            graph = build_graph(cfg.root)
        except BuildError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        if not graph.aims:
            print(f"no programme/aims/ under {cfg.root} — nothing to report")
            return 0
        rep = programme_report(graph)
        print(format_report(rep))
        return 1 if (args.strict and not rep.clean) else 0

    if args.command == "map":
        return _map(args)

    if args.command == "desk":
        return _desk(args)

    if args.command == "validate":
        return _validate(args)

    if args.command == "enrich":
        from . import store
        from .sources.openalex import OpenAlex
        cfg = load_config(args.root)
        oa = OpenAlex(mailto=cfg.mailto)
        try:
            res = store.enrich_stubs(cfg.root, oa, dry_run=args.dry_run, force=args.force)
        except Exception as e:  # network/parse — report, don't traceback
            print(f"error: {e}", file=sys.stderr)
            return 1
        tag = "DRY-RUN — nothing written" if args.dry_run else "written"
        print(f"lit enrich ({tag}): {len(res.enriched)} enriched, {len(res.already)} already "
              f"complete, {len(res.no_doi)} without DOI, {len(res.unmatched)} unmatched")
        for k in res.unmatched:
            print(f"  ⚠ {k}: no OpenAlex match / nothing to add", file=sys.stderr)
        return 0

    if args.command == "abstracts":
        from .abstracts import backfill
        cfg = load_config(args.root)
        res = backfill(cfg.root, cfg.pdf_dir, dry_run=args.dry_run,
                       only=tuple(args.citekeys))
        tag = "DRY-RUN — nothing written" if args.dry_run else "written"
        print(f"lit abstracts ({tag}): {len(res.filled)} filled, {len(res.already)} already "
              f"had one, {len(res.unanchored)} unanchored, {len(res.no_fulltext)} without a .md")
        for key, anchor in res.filled:
            # The anchor is the whole point of the report: a "heading" fill copied a section the
            # paper itself labelled Abstract, a "byline" fill took the unlabelled lead paragraph
            # and is the one to spot-check against the PDF.
            note = "  ← unlabelled lead paragraph, check against the PDF" if anchor == "byline" else ""
            print(f"  + {key} ({anchor}){note}")
        for key, artifacts in res.flagged:
            print(f"  ⚠ {key}: PDF text-layer damage in the abstract ({', '.join(artifacts)}) "
                  f"— fix by hand", file=sys.stderr)
        for key in res.unanchored:
            print(f"  ⚠ {key}: nothing anchored safely in the full text — add the abstract by hand",
                  file=sys.stderr)
        for key in res.no_fulltext:
            print(f"  ⚠ {key}: no <citekey>.md beside the PDF — re-ingest to write one",
                  file=sys.stderr)
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
