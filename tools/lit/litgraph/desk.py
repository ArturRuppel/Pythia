"""The desk: the curated papers whose curation has moved past what the owner validated.

`pass` (SCHEMA §4) is how far curation ran, and agents raise it in batches, so it no longer says
how far the *owner* engaged with a paper. `validated` is that second number, written only by the
owner (`lit validate`, the viewer's Validate action). The desk is derived from the two and never
stored:

    on the desk  iff  `validated` is absent  (new: the owner has never validated it)
                  or  `validated` != pass     (changed: absent `pass` counts as 0)

So an agent rewriting a paper at the SAME pass leaves it off the desk; only a change of `pass`
puts it back. A `validated` above `pass` is legal (the owner read further than curation ran) but
unusual, so the build flags it rather than failing.

Pure functions over the loaded `Paper`s: no PDF, no quote checks, nothing written."""

from __future__ import annotations

from dataclasses import dataclass

from .graph import Paper

# The pass rungs, by number (CURATION.md). The viewer carries the same five labels.
PASS_LABELS = ("ingested", "abstract", "intro+disc", "results", "methods")


def effective_pass(p: Paper) -> int:
    """The curation pass the desk compares against: an absent `pass` counts as 0."""
    return p.pass_ if p.pass_ is not None else 0


def status(p: Paper) -> str | None:
    """`"new"` (never validated), `"changed"` (validated at another pass), or None (off the desk,
    or not a curated paper at all)."""
    if not p.curated:
        return None
    if p.validated is None:
        return "new"
    return "changed" if p.validated != effective_pass(p) else None


def on_desk(p: Paper) -> bool:
    return status(p) is not None


@dataclass
class DeskRow:
    citekey: str
    status: str                 # "new" | "changed"
    validated: int | None
    pass_: int
    title: str
    year: int | None
    updated: float | None       # the curated YAML's mtime: the only date a paper carries

    def as_json(self) -> dict:
        return {"citekey": self.citekey, "status": self.status, "validated": self.validated,
                "pass": self.pass_, "title": self.title, "year": self.year,
                "updated": self.updated}


def _newest_first(rows: list[DeskRow]) -> list[DeskRow]:
    """Newest curation record first where a date is known, the undated after, then by citekey."""
    return sorted(rows, key=lambda r: (r.updated is None, -(r.updated or 0), r.citekey))


def desk(papers: dict[str, Paper], only: set[str] | None = None) -> dict[str, list[DeskRow]]:
    """The desk, grouped: `{"new": [...], "changed": [...]}`, each newest first. `only` narrows it
    to a set of citekeys (a collection, a topic, a tag)."""
    out: dict[str, list[DeskRow]] = {"new": [], "changed": []}
    for ck, p in papers.items():
        if only is not None and ck not in only:
            continue
        st = status(p)
        if st is None:
            continue
        out[st].append(DeskRow(ck, st, p.validated, effective_pass(p), p.title, p.year,
                               p.curation_updated))
    return {k: _newest_first(v) for k, v in out.items()}


def flags(papers: dict[str, Paper]) -> list[str]:
    """Build warnings (not errors): a `validated` above the paper's pass."""
    return [f"{ck}: validated {p.validated} is above pass {effective_pass(p)} — the owner read "
            "further than curation ran (legal, but unusual)"
            for ck, p in sorted(papers.items())
            if p.curated and p.validated is not None and p.validated > effective_pass(p)]


def label(n: int) -> str:
    return f"{n} {PASS_LABELS[n]}" if 0 <= n < len(PASS_LABELS) else str(n)


def format_desk(groups: dict[str, list[DeskRow]], scope: str = "") -> str:
    """The terminal listing: the two groups, then a one-line total."""
    lines: list[str] = []
    if scope:
        lines.append(f"scope:{scope}")
    for name, head in (("new", "new — never validated"), ("changed", "changed — curation moved")):
        rows = groups[name]
        if not rows:
            continue
        lines.append(f"{head} ({len(rows)})")
        for r in rows:
            st = (f"curated {label(r.pass_)}" if r.status == "new"
                  else f"validated {r.validated} → curated {label(r.pass_)}")
            yr = f" {r.year}" if r.year else ""
            lines.append(f"  {r.citekey:<28}{yr:<5}  {st:<34}  {r.title}")
        lines.append("")
    n_new, n_chg = len(groups["new"]), len(groups["changed"])
    lines.append(f"desk: {n_new + n_chg} papers ({n_new} new, {n_chg} changed)")
    return "\n".join(lines) + "\n"
