"""Collections (SCHEMA §10) — papers gathered for a purpose: a review, a grant, a talk.

The third way into the library, and kept apart from the other two on purpose. The claim
ladder answers *what is known*; the topic axis answers *what papers do I have on X* and stays
true for as long as the papers do. A collection answers *why were these papers gathered*: it
is time-bound (it has a date, and the review it served gets submitted), and a paper's being in
one says nothing about what the paper is about. Using `tags` for it would put that purpose on
the paper, where it would outlive the purpose and pollute the topic axis that reads tags.

So the shape is the mirror image of a topic. A topic's membership is *derived* (from tags) and
nothing is written on the paper; a collection's membership is *authored*, on the collection
only, and still nothing is written on the paper — a paper never names its collections. A
collection may list stubs as well as curated papers (a paywalled related-work paper may only
ever be a stub). It is not a slice and not in the graph: no edge targets it, no emergent
property reads it, and its slug is kept disjoint from every name a ref can resolve to.
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field
from pathlib import Path

from ruamel.yaml.error import YAMLError
from .yamlio import rt_yaml, safe_yaml


_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass
class Collection:
    slug: str
    title: str
    note: str | None = None
    date: str | None = None                             # ISO date, as authored
    papers: list[str] = field(default_factory=list)     # citekeys, curated or stub, as authored


class CollectionError(Exception):
    """Raised on a SCHEMA §10 validation failure, or a CLI edit that cannot apply. The message
    names the offending collection."""


def collections_dir(root) -> Path:
    return Path(root) / "collections"


def slugify(title: str) -> str:
    """A title -> kebab slug, the convention every other slug in the repo follows."""
    s = re.sub(r"[^\w\s-]", "", title.lower()).replace("_", " ")
    return re.sub(r"[\s-]+", "-", s).strip("-")


def _date_str(v) -> str | None:
    # The safe loader turns an unquoted `2026-10-29` into a datetime.date; keep it as text so
    # the viewer and the CLI see exactly what was written.
    if v is None or v == "":
        return None
    return v.isoformat() if isinstance(v, (_dt.date, _dt.datetime)) else str(v)


def load_collections(root) -> dict[str, Collection]:
    """Parse collections/*.yaml. Returns {} when the repo has none — the axis is optional,
    exactly as topics/ and programme/ are."""
    out: dict[str, Collection] = {}
    for f in sorted(collections_dir(root).glob("*.yaml")):
        # Name the file: ruamel is handed text, so its own errors say only
        # `in "<unicode string>", line N` — the same guard topics.load_topics carries.
        try:
            raw = safe_yaml().load(f.read_text()) or {}
        except YAMLError as e:
            raise CollectionError(f"{f}: {e}") from e
        out[f.stem] = Collection(
            slug=f.stem,
            title=str(raw.get("title") or ""),
            note=raw.get("note"),
            date=_date_str(raw.get("date")),
            papers=[str(k) for k in (raw.get("papers") or [])],
        )
    return out


def validate_collections(collections: dict[str, Collection], papers,
                         reserved: set[str] | None = None) -> None:
    """SCHEMA §10 validation. Fails the build on:

    - a missing `title` (it is what search matches, so a collection without one is unfindable);
    - a citekey that is neither a curated paper nor a stub. This is an error, not a warning,
      because the collection file is the ONE place membership is authored — a citekey that
      resolves nowhere is a dangling ref in the SCHEMA §6 rule 1 sense, not a curation signal
      like a dead topic keyword. `lit collection add` mints a stub for any DOI it is handed, so
      there is always a way to make the ref resolve;
    - a citekey listed twice in one collection;
    - a slug that is not kebab-case, or that also names a claim/question/method/topic or a
      citekey (`reserved`). The disjointness is what keeps a collection from ever reading as an
      edge target: refs resolve bare names against those namespaces only.
    """
    reserved = reserved or set()
    for slug, c in collections.items():
        if not _SLUG.match(slug):
            raise CollectionError(f"collection slug {slug!r} is not kebab-case (SCHEMA §10)")
        if slug in reserved:
            raise CollectionError(
                f"collection slug {slug!r} also names a broad slice, topic or paper (SCHEMA §10)")
        if not c.title.strip():
            raise CollectionError(f"{slug}: collection has no title (SCHEMA §10)")
        seen: set[str] = set()
        for k in c.papers:
            if k in seen:
                raise CollectionError(f"{slug}: {k} is listed twice (SCHEMA §10)")
            seen.add(k)
            if k not in papers:
                raise CollectionError(
                    f"{slug}: {k} is neither a curated paper nor a stub (SCHEMA §10) — "
                    f"add it by DOI (`lit collection add {slug} <doi>`) to mint the stub")


def memberships(collections: dict[str, Collection]) -> dict[str, list[str]]:
    """Invert membership: citekey -> the slugs of the collections listing it. Derived for
    display only — the paper itself never names a collection."""
    out: dict[str, list[str]] = {}
    for slug, c in sorted(collections.items()):
        for k in c.papers:
            out.setdefault(k, []).append(slug)
    return out


# ── writes (the `lit collection` CLI) ─────────────────────────────────────────────────────
# Round-tripped with ruamel so a curator's comments and hand-ordering survive, the same
# contract store.py keeps for curated files and stubs.yaml.

def _path(root, slug: str) -> Path:
    return collections_dir(root) / f"{slug}.yaml"


def create(root, slug: str, title: str, note: str | None = None,
           date: str | None = None) -> Path:
    """Write a new, empty collections/<slug>.yaml. Refuses to overwrite one that exists."""
    from ruamel.yaml.comments import CommentedMap, CommentedSeq
    from ruamel.yaml.scalarstring import DoubleQuotedScalarString as DQ

    if not _SLUG.match(slug):
        raise CollectionError(f"collection slug {slug!r} is not kebab-case")
    path = _path(root, slug)
    if path.exists():
        raise CollectionError(f"collection {slug!r} already exists ({path})")
    doc = CommentedMap()
    doc["title"] = DQ(title)
    if date:
        doc["date"] = DQ(date)
    if note:
        doc["note"] = DQ(note)
    doc["papers"] = CommentedSeq()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        rt_yaml().dump(doc, fh)
    return path


def edit_papers(root, slug: str, add: list[str] = (), remove: list[str] = ()) -> tuple[list[str], list[str]]:
    """Append `add` (de-duplicated, order-preserving) and drop `remove` from a collection's
    `papers`. Returns (changed, current): the citekeys actually added/removed, and the list as
    it now stands. Writes nothing when nothing changes. Resolution of each citekey is the
    caller's job; the build validates it regardless."""
    from ruamel.yaml.comments import CommentedSeq

    path = _path(root, slug)
    if not path.is_file():
        raise CollectionError(f"no such collection: {slug} (create it with `lit collection new`)")
    doc = rt_yaml().load(path.read_text()) or {}
    seq = doc.get("papers")
    if seq is None:
        seq = doc["papers"] = CommentedSeq()
    changed: list[str] = []
    for k in add:
        if k not in seq:
            seq.append(k)
            changed.append(k)
    for k in remove:
        while k in seq:
            seq.remove(k)
            if k not in changed:
                changed.append(k)
    if changed:
        with path.open("w") as fh:
            rt_yaml().dump(doc, fh)
    return changed, [str(k) for k in seq]
