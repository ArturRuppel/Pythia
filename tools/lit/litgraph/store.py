"""Filesystem I/O: existing-key index, curated write, stubs merge, PDF rename (spec §4 D).

stubs.yaml is round-tripped with ruamel so the human's comments/formatting survive; merges
are additive and never delete.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


from .graph import classify_ref
from .yamlio import rt_yaml, safe_yaml
from .model import CuratedPaper, Stub


# Every slice-level field that carries refs (SCHEMA §6 / programme design §5), and every
# top-level group that holds slices — paper groups plus the aim-only tests/capabilities.
# Shared by _quote_sharpened_refs so a new edge or slice kind only needs adding here.
_REF_FIELDS = ("grounded_in", "leads_to", "corroborates", "contradicts", "answers",
               "discriminates", "enabled_by")
_SLICE_GROUPS_ALL = ("claims", "questions", "methods", "tests", "capabilities")


def _quote_sharpened_refs(doc) -> None:
    """Force every sharpened cross-container ref (`Key2026Journal:c4`, `@aim:c1`) sitting in a
    ref-list field to a quoted scalar, in place, before dump.

    graph.py's safe loader (libyaml, fast) is stricter than this module's round-trip parser
    (pure Python, preserves comments): in a flow sequence a plain scalar may not carry a `:`,
    so `corroborates: [Key2026Journal:c4]` round-trips fine here but aborts the whole build
    over there (graph.load_yaml's docstring has the full story). A curated file's refs aren't
    only set by this module — a curator hand-edits YAML directly — so any write that
    round-trips the *whole* document (even one only meaning to set `quote_loc` or a tag)
    re-serializes every slice's refs as-is. Quoting the sharpened ones here means the first
    store.py write to touch a file after a bad hand-edit heals it, instead of carrying the
    landmine forward untouched. Scoped to the known ref-list fields, not every string in the
    document, so a coincidental `:` in `text`/`quote`/`note` is never touched.
    """
    from ruamel.yaml.scalarstring import DoubleQuotedScalarString as DQ
    from ruamel.yaml.scalarstring import ScalarString

    for group in _SLICE_GROUPS_ALL:
        for slice_map in doc.get(group, []) or []:
            for field_name in _REF_FIELDS:
                seq = slice_map.get(field_name)
                if not seq:
                    continue
                for i, r in enumerate(seq):
                    if isinstance(r, str) and not isinstance(r, ScalarString) and classify_ref(r) == "sharpened":
                        seq[i] = DQ(r)


def curated_dir(root: Path) -> Path:
    return Path(root) / "curated"


def stubs_path(root: Path) -> Path:
    return Path(root) / "stubs.yaml"


def load_taken(root: Path) -> dict[str, str | None]:
    """Map every in-use citekey -> its DOI: curated/*.yaml stems + stubs.yaml keys."""
    root = Path(root)
    taken: dict[str, str | None] = {}
    cdir = curated_dir(root)
    if cdir.is_dir():
        for f in sorted(cdir.glob("*.yaml")):
            doi = None
            try:
                doc = safe_yaml().load(f.read_text()) or {}
                doi = doc.get("doi")
            except Exception:
                pass
            taken[f.stem] = doi
    sp = stubs_path(root)
    if sp.exists():
        stubs = safe_yaml().load(sp.read_text()) or {}
        for key, body in stubs.items():
            taken[key] = (body or {}).get("doi") if isinstance(body, dict) else None
    return taken


def write_curated(root: Path, paper: CuratedPaper, force: bool, dry_run: bool) -> Path:
    """Write curated/<citekey>.yaml; never overwrite a curated file unless `force`."""
    path = curated_dir(root) / f"{paper.citekey}.yaml"
    if path.exists() and not force:
        raise FileExistsError(f"{path} already exists (use --force to overwrite)")
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(paper.to_yaml())
    return path


def merge_stubs(root: Path, stubs: list[Stub], dry_run: bool) -> tuple[list[str], list[str]]:
    """Additively merge stub entries into stubs.yaml. Returns (added, deduped) citekeys.

    A stub whose citekey already exists is treated as deduped (left untouched). A stub
    whose citekey is already a curated paper is also skipped (handled upstream by key
    allocation, but guarded here too).
    """
    sp = stubs_path(root)
    if sp.exists():
        doc = rt_yaml().load(sp.read_text()) or {}
    else:
        from ruamel.yaml.comments import CommentedMap

        doc = CommentedMap()

    curated_stems = {f.stem for f in curated_dir(root).glob("*.yaml")} if curated_dir(root).is_dir() else set()

    added: list[str] = []
    deduped: list[str] = []
    for s in stubs:
        if s.citekey in doc or s.citekey in curated_stems:
            deduped.append(s.citekey)
            continue
        doc[s.citekey] = _to_commented(s.to_mapping())
        added.append(s.citekey)

    if not dry_run and added:
        sp.parent.mkdir(parents=True, exist_ok=True)
        with sp.open("w") as fh:
            rt_yaml().dump(doc, fh)
    return added, deduped


def prune_curated_stubs(root: Path, dry_run: bool, extra_keys: tuple[str, ...] = ()) -> list[str]:
    """Drop from stubs.yaml every key that is now a curated paper (a §6.3 collision).

    A stub is a placeholder for an un-sliced container; the moment a paper is curated
    (its `curated/<key>.yaml` exists) that placeholder is stale and must go, or the build
    fails on the curated/stub collision. `extra_keys` lets a caller name a key that is being
    promoted in the same run (e.g. dry-run, where the curated file isn't on disk yet).
    Returns the citekeys actually removed; round-trips so comments/formatting survive.
    """
    sp = stubs_path(root)
    if not sp.exists():
        return []
    doc = rt_yaml().load(sp.read_text()) or {}
    curated_stems = {f.stem for f in curated_dir(root).glob("*.yaml")} if curated_dir(root).is_dir() else set()
    curated_stems.update(extra_keys)
    removed = [k for k in list(doc) if k in curated_stems]
    if not removed:
        return []
    if not dry_run:
        for k in removed:
            del doc[k]
        with sp.open("w") as fh:
            rt_yaml().dump(doc, fh)
    return removed


def _norm_doi(doi: str | None) -> str | None:
    """Bare, lower-cased DOI for matching (OpenAlex keeps case; DOIs are case-insensitive)."""
    if not doi:
        return None
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", doi.strip(), flags=re.IGNORECASE).lower() or None


@dataclass
class EnrichResult:
    enriched: list[str]   # stubs that gained authors and/or journal
    already: list[str]    # already complete (skipped; --force re-fetches these)
    no_doi: list[str]     # no DOI on the stub — nothing to look up
    unmatched: list[str]  # had a DOI but OpenAlex returned no work / no new fields


def enrich_stubs(root: Path, oa, dry_run: bool = False, force: bool = False) -> EnrichResult:
    """Backfill `authors` + `journal` onto existing stubs.yaml entries from OpenAlex (by DOI).

    A stub written before these fields existed carries only title/year/doi/type; this fills the
    gaps in one batched query. Only stubs missing a field are fetched unless `force`. New/other
    fields and comments are round-tripped; the two added keys append to each entry.
    """
    sp = stubs_path(root)
    if not sp.exists():
        return EnrichResult([], [], [], [])
    doc = rt_yaml().load(sp.read_text()) or {}

    doi_to_keys: dict[str, list[str]] = {}
    already: list[str] = []
    no_doi: list[str] = []
    for key in list(doc):
        body = doc.get(key) or {}
        nd = _norm_doi(body.get("doi"))
        if not nd:
            no_doi.append(key)
            continue
        if body.get("authors") and body.get("journal") and not force:
            already.append(key)
            continue
        doi_to_keys.setdefault(nd, []).append(key)

    enriched: list[str] = []
    unmatched: list[str] = []
    if doi_to_keys:
        works = oa.fetch_works_by_doi(list(doi_to_keys))
        by_doi = {_norm_doi(w.doi): w for w in works if _norm_doi(w.doi)}
        for nd, keys in doi_to_keys.items():
            w = by_doi.get(nd)
            for key in keys:
                body = doc[key]
                names = [a.display_name for a in w.authors if a.display_name] if w else []
                changed = False
                if names and (force or not body.get("authors")):
                    body["authors"] = names
                    changed = True
                if w and w.venue_display and (force or not body.get("journal")):
                    body["journal"] = w.venue_display
                    changed = True
                (enriched if changed else unmatched).append(key)

    if not dry_run and enriched:
        with sp.open("w") as fh:
            rt_yaml().dump(doc, fh)
    return EnrichResult(enriched, already, no_doi, unmatched)


def _to_commented(mapping: dict):
    from ruamel.yaml.comments import CommentedMap

    cm = CommentedMap()
    for k, v in mapping.items():
        cm[k] = v
    return cm


_SLICE_GROUPS = ("claims", "questions", "methods")


def _loc_cm(page: int, rects: list[list[float]]):
    """A compact `quote_loc` mapping: page + flow-style rects rounded to 4 dp (page fractions)."""
    from ruamel.yaml.comments import CommentedMap, CommentedSeq

    rects_seq = CommentedSeq()
    for r in rects:
        row = CommentedSeq(round(float(v), 4) for v in r)
        row.fa.set_flow_style()
        rects_seq.append(row)
    loc = CommentedMap()
    loc["page"] = int(page)
    loc["rects"] = rects_seq
    return loc


def _update_quote_loc_in_place(existing, loc) -> bool:
    """Rewrite an existing `quote_loc` mapping's values *without replacing the node*.

    `quote_loc` is normally the last key of a slice, so the curator's section header introducing
    the NEXT slice ("# ── Pass-2 borrowed framing (intro citation walls) ──") is attached by
    ruamel to the end of this block — concretely to the `rects` sequence's `ca.end`, that being
    the last node before it. Assigning `slice_map["quote_loc"] = <fresh CommentedMap>` therefore
    drops the comment along with the node carrying it: `lit locate --force` over the repo deleted
    a few hundred lines of curation reasoning while reporting only that it had written
    quote_locs. Load/dump alone is byte-identical — that one assignment was the whole leak.

    Transplanting the salvaged CommentToken onto the replacement does not work: the token keeps
    the line/column of the document it was parsed from, and the emitter silently declines to
    place it. Keeping the original objects and swapping only their *contents* sidesteps the
    question — the comment never moves, so nothing has to know where it belongs.

    Returns False when the existing value isn't the shape we expect (hand-written scalar, missing
    `rects`), leaving the caller to fall back to plain assignment.
    """
    if not (hasattr(existing, "get") and hasattr(existing.get("rects"), "__setitem__")):
        return False
    existing["page"] = loc["page"]
    rects = existing["rects"]
    rects[:] = loc["rects"]              # same CommentedSeq object, new contents
    # Per-index comments inside the old rects list would now point at rows that no longer exist.
    # There are normally none (the block is machine-written), but a stale index is how a comment
    # ends up welded to the wrong rect, so drop any that fell off the end.
    stale = [i for i in getattr(existing["rects"].ca, "items", {}) if isinstance(i, int) and i >= len(rects)]
    for i in stale:
        del existing["rects"].ca.items[i]
    return True


def _place_quote_loc(slice_map, loc) -> None:
    """Set `quote_loc` on `slice_map`, positioned right after `quote` rather than appended at
    the tail of the mapping.

    A tail-appended `quote_loc` lands after any trailing comment the curator wrote (e.g. a
    `note:` followed by a section-header comment) — still valid YAML, since comments are
    ignored, but a trap: when a human later inserts new slices immediately above that comment,
    the orphaned `quote_loc` block silently re-parents onto the newly-last slice before it,
    because it was never actually attached to `quote` — only to "wherever the mapping happened
    to end". Anchoring it right after `quote` makes that mis-parenting impossible. If a
    `quote_loc` already exists (the `--force` path), overwrite in place — do not move it, so a
    re-`locate` doesn't churn the diff.
    """
    if "quote_loc" in slice_map:
        if not _update_quote_loc_in_place(slice_map["quote_loc"], loc):
            slice_map["quote_loc"] = loc
        return
    if "quote" in slice_map:
        idx = list(slice_map).index("quote")
        slice_map.insert(idx + 1, "quote_loc", loc)
    else:
        slice_map["quote_loc"] = loc


def write_quote_loc(root: Path, citekey: str, slice_id: str, page: int,
                    rects: list[list[float]]) -> Path:
    """Set (or replace) `quote_loc` on one slice of curated/<citekey>.yaml, round-tripped so
    the human's comments/formatting survive. `rects` are page fractions (0..1). Raises
    FileNotFoundError / KeyError if the file or slice id is absent."""
    path = curated_dir(root) / f"{citekey}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"no curated paper: {citekey}")
    doc = rt_yaml().load(path.read_text()) or {}

    target = None
    for group in _SLICE_GROUPS:
        for s in doc.get(group, []) or []:
            if s.get("id") == slice_id:
                target = s
                break
        if target is not None:
            break
    if target is None:
        raise KeyError(f"no slice {slice_id} in {citekey}")

    _place_quote_loc(target, _loc_cm(page, rects))
    _quote_sharpened_refs(doc)
    with path.open("w") as fh:
        rt_yaml().dump(doc, fh)
    return path


def write_quote_locs(root: Path, citekey: str, locs: dict[str, dict]) -> int:
    """Set `quote_loc` on many slices of curated/<citekey>.yaml in one round-trip (for the
    batch `lit locate`). `locs` maps slice_id -> {"page":int, "rects":[[...],...]}. Slice ids
    absent from the file are skipped. Returns the number written; writes nothing if none."""
    path = curated_dir(root) / f"{citekey}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"no curated paper: {citekey}")
    doc = rt_yaml().load(path.read_text()) or {}
    by_id: dict = {}
    for group in _SLICE_GROUPS:
        for s in doc.get(group, []) or []:
            by_id[s.get("id")] = s
    n = 0
    for sid, loc in locs.items():
        s = by_id.get(sid)
        if s is None:
            continue
        _place_quote_loc(s, _loc_cm(loc["page"], loc["rects"]))
        n += 1
    if n:
        _quote_sharpened_refs(doc)
        with path.open("w") as fh:
            rt_yaml().dump(doc, fh)
    return n


def edit_tags(root: Path, citekey: str, tags: list[str], remove: bool = False) -> list[str]:
    """Add, remove, or (with empty `tags`) just read a curated paper's `tags` list, round-tripped
    so the curator's comments/formatting survive. Adds are de-duplicated and order-preserving;
    removing the last tag drops the key entirely. A new `tags` key is inserted before `authors`
    to match the on-disk field order (SCHEMA §4). Returns the resulting tag list; writes nothing
    when reading or when the list is unchanged. Raises FileNotFoundError if the paper is absent."""
    path = curated_dir(root) / f"{citekey}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"no curated paper: {citekey}")
    doc = rt_yaml().load(path.read_text()) or {}
    current = list(doc.get("tags") or [])
    if not tags:                                   # list-only: no mutation
        return current
    if remove:
        drop = set(tags)
        result = [t for t in current if t not in drop]
    else:
        result = current + [t for t in tags if t not in current]
    if result == current:                          # nothing changed → leave the file untouched
        return current

    if not result:
        doc.pop("tags", None)                      # last tag gone → drop the key
    else:
        from ruamel.yaml.comments import CommentedSeq
        from ruamel.yaml.scalarstring import DoubleQuotedScalarString as DQ
        seq = CommentedSeq(DQ(t) for t in result)  # quote every tag → `tags: ["a", "b"]`
        seq.fa.set_flow_style()                    # flow list, matching model.to_yaml
        if "tags" in doc:
            doc["tags"] = seq                      # in place — keep its position
        elif "authors" in doc:
            doc.insert(list(doc).index("authors"), "tags", seq)
        else:
            doc["tags"] = seq
    _quote_sharpened_refs(doc)
    with path.open("w") as fh:
        rt_yaml().dump(doc, fh)
    return result


_TOP_KEY = re.compile(r"^(?P<key>[A-Za-z_][\w-]*):")
_VALIDATED_LINE = re.compile(r"^validated:[ \t]*[^#\n]*?(?P<tail>[ \t]+#.*)?$")


def _validated_line_edit(text: str, value: int) -> str | None:
    """`text` with its top-level `validated:` set to `value`, as a pure line edit: an existing line
    keeps its end-of-line comment; a new line goes directly under `pass:` (past that line's indented
    continuation — a wrapped comment), else where `pass:` would sit (after `year`, `type` or
    `title`, past a block scalar's lines). Everything else in the file stays byte-identical, which
    a ruamel round trip does not promise (it re-spaces aligned flow values). None when there is no
    anchor line to place it by; the caller then checks the result parses to the intended mapping."""
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        m = _VALIDATED_LINE.match(line.rstrip("\n"))
        if m:
            eol = "\n" if line.endswith("\n") else ""
            lines[i] = f"validated: {value}{m.group('tail') or ''}{eol}"
            return "".join(lines)
    tops = {}
    for i, line in enumerate(lines):
        m = _TOP_KEY.match(line)
        if m and m.group("key") not in tops:
            tops[m.group("key")] = i
    anchor = next((tops[k] for k in ("pass", "year", "type", "title") if k in tops), None)
    if anchor is None:
        return None
    j = anchor + 1
    while j < len(lines) and lines[j][:1] in (" ", "\t") and lines[j].strip():
        j += 1                                     # the anchor's own continuation lines
    if not lines[j - 1].endswith("\n"):
        lines[j - 1] += "\n"
    lines.insert(j, f"validated: {value}\n")
    return "".join(lines)


def _hand_on_trailing_comment(doc, key: str, new_key: str) -> None:
    """ruamel hangs everything between a scalar and the next key on the scalar: its end-of-line
    comment, that comment's indented continuation lines, and the blank lines and column-0 comments
    that really introduce the next key. Inserting `new_key` straight after `key` would land it
    below all of that — under the next section's heading comment, past a blank line. Split the
    token: `key` keeps its own comment (end-of-line plus indented continuations), and whatever
    followed that moves onto `new_key`, so the new line sits directly under `key`'s and the file
    keeps its spacing."""
    ca = doc.ca.items.get(key)
    tok = ca[2] if ca and len(ca) > 2 else None
    if tok is None:
        return
    lines = tok.value.split("\n")
    i = 0
    if lines[0].lstrip().startswith("#"):          # an end-of-line comment on `key`'s own line
        i = 1
        while i < len(lines) and lines[i][:1] in (" ", "\t") and lines[i].lstrip().startswith("#"):
            i += 1                                 # …and its indented continuation lines
    own, rest = lines[:i], "\n".join(lines[i:])
    if own:
        tok.value = "\n".join(own) + "\n"
    else:
        ca[2] = None
    if rest:
        from ruamel.yaml.error import CommentMark
        from ruamel.yaml.tokens import CommentToken
        value = rest if not own else "\n" + rest   # without an own comment, `rest` starts the line end
        doc.ca.items[new_key] = [None, None, CommentToken(value, CommentMark(0), None), None]


@dataclass
class Validation:
    citekey: str
    old: int | None          # the validated pass before (None: never validated)
    new: int                 # the validated pass after
    pass_: int               # the paper's curation pass at write time (absent counts as 0)

    @property
    def changed(self) -> bool:
        return self.old != self.new


def set_validated(root: Path, citekey: str, value: int | None = None,
                  dry_run: bool = False) -> Validation:
    """Set `validated` on curated/<citekey>.yaml — the OWNER's number (SCHEMA §4): to the paper's
    current `pass` (read from the same document being written, so it is the pass on disk at write
    time), or to `value`. Round-tripped exactly like `edit_tags`, so comments and formatting survive.
    An existing `validated:` line is set in place; a new one goes directly under `pass:` (or where
    `pass:` would be — after `year`/`type`/`title` — when the paper has none). Writes nothing when
    the value is unchanged or on `dry_run`.

    This is the one writer `lit validate` and serve's POST /validate go through. Nothing else in
    the tool writes the field: not ingest, not curation. Raises FileNotFoundError for a paper that
    is not curated and ValueError for a value outside 0–4."""
    path = curated_dir(root) / f"{citekey}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"not a curated paper: {citekey}")
    if value is not None and (isinstance(value, bool) or not isinstance(value, int)
                              or not 0 <= value <= 4):
        raise ValueError(f"validated must be an int 0–4, got {value!r}")
    text = path.read_text()
    doc = rt_yaml().load(text) or {}
    raw_pass = doc.get("pass")
    pass_ = raw_pass if isinstance(raw_pass, int) and not isinstance(raw_pass, bool) else 0
    old = doc.get("validated")
    old = old if isinstance(old, int) and not isinstance(old, bool) else None
    new = pass_ if value is None else value
    result = Validation(citekey, old, new, pass_)
    if dry_run or (not result.changed and "validated" in doc):
        return result
    edited = _validated_line_edit(text, new)
    if edited is not None and safe_yaml().load(edited) == {**safe_yaml().load(text), "validated": new}:
        path.write_text(edited)                    # byte-exact elsewhere: the common case
        return result
    # a layout the line edit does not recognise: the ruamel round trip `edit_tags` uses
    if "validated" in doc:
        doc["validated"] = new                     # in place — keep its position and comment
    else:
        anchor = next((k for k in ("pass", "year", "type", "title") if k in doc), None)
        doc.insert(list(doc).index(anchor) + 1 if anchor else 0, "validated", new)
        if anchor:
            _hand_on_trailing_comment(doc, anchor, "validated")
    _quote_sharpened_refs(doc)
    with path.open("w") as fh:
        rt_yaml().dump(doc, fh)
    return result


def write_abstract(root: Path, citekey: str, abstract: str, dry_run: bool = False) -> bool:
    """Set `abstract` on curated/<citekey>.yaml, round-tripped so the curator's comments and
    formatting survive. Inserted before `tags`/`authors` to match the on-disk field order
    (SCHEMA §4, and `model.to_yaml`'s order for a freshly ingested file). Never overwrites an
    abstract that is already there — the caller decides what is missing. Returns whether it
    wrote. Raises FileNotFoundError if the paper is absent."""
    path = curated_dir(root) / f"{citekey}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"no curated paper: {citekey}")
    doc = rt_yaml().load(path.read_text()) or {}
    if (doc.get("abstract") or "").strip():
        return False

    from ruamel.yaml.scalarstring import DoubleQuotedScalarString as DQ
    value = DQ(abstract)
    anchor = next((k for k in ("tags", "authors") if k in doc), None)
    if anchor is None:
        doc["abstract"] = value
    else:
        doc.insert(list(doc).index(anchor), "abstract", value)
    if not dry_run:
        _quote_sharpened_refs(doc)
        with path.open("w") as fh:
            rt_yaml().dump(doc, fh)
    return True


def rename_pdf(pdf_path: Path, citekey: str, dry_run: bool) -> Path | None:
    """Rename the source PDF to <dir>/<citekey>.pdf. Never clobber a different file."""
    pdf_path = Path(pdf_path)
    target = pdf_path.with_name(f"{citekey}.pdf")
    if target == pdf_path:
        return target
    if target.exists():
        return None  # refuse to clobber; caller warns
    if not dry_run:
        pdf_path.rename(target)
    return target


def write_fulltext(pdf_path: Path, citekey: str, markdown: str, dry_run: bool) -> Path:
    """Write <citekey>.md beside the (renamed) PDF."""
    target = Path(pdf_path).with_name(f"{citekey}.md")
    if not dry_run:
        target.write_text(markdown)
    return target
