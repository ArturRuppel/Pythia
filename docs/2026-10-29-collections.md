# Collections — the purpose axis

**Status:** built · **Date:** 2026-10-29
**Companions:** [SCHEMA.md §10](../SCHEMA.md) (the file format and validation) ·
[2026-08-03-topics-and-claim-altitudes.md](2026-08-03-topics-and-claim-altitudes.md) ·
[2026-07-19-tags-and-search-design.md](2026-07-19-tags-and-search-design.md)

## Why not a tag

The first want was concrete: the related-work papers gathered for a peer review, findable by
typing the review's name, say "Batching review". A tag would have done it mechanically, and it
was refused. A tag says what a paper is *about*, it stays true, and the topic axis is built on
it. "Batching review" is about no paper. It is the reason a set of papers was gathered, and it
stops mattering once the review is sent. Written as a tag it would sit on every one of those
papers forever and turn up in `lit topics --orphans` as an unfiled tag forever.

So a collection is its own thing, and the mirror image of a topic. A topic's membership is
derived from tags. A collection's membership is authored on the collection, and only there:
a paper never names its collections. It may list stubs, since a paywalled paper may never be
more than one. It is not graph (SCHEMA §10 has the rules that keep it out).

## Where it shows

- **Search, board and app.** A collection is matched by its **title or slug**, by the same
  rules as a paper (case-insensitive, whitespace terms all present). The note is not searched,
  because it is prose and "review" in a note would surface collections nobody asked for. On the
  board a hit is its own row **above** the papers. Opening it lists every paper, uncapped,
  because the list was made on purpose and "refine the search" would be the wrong answer.
  `collection:<slug>` is the box's syntax for that, the twin of `topic:<slug>`. In the app a
  hit opens the collection's own screen, with curated papers and stubs as separate sections
  using the Library's own rows.
- **Browsing.** In the app the **Topics tab leads with a Collections section** (newest date
  first). They are few, dated, and what you came back for. They head the tab without joining the
  tree, because they are not topics. A paper's or a stub's page lists **"In collections"**,
  derived in the viewer and written nowhere. On the board the library rail has a
  **collection** facet under topic. Unlike a topic facet, it does not force the scope to curated,
  because a collection may hold stubs.
- **Not** a fifth tab. Four tabs fit an iPhone's bar with room to read, and a collection is
  reached in two taps from Topics or by name from Search.

## Tooling

`lit collection new | add | remove | list | show`. `add` takes citekeys or DOIs. A DOI not in
the library is minted as a stub first (`ingest.stub_for_doi`, the same rules as an ingest's
references), so the collection never lists a key the build cannot resolve. The build fails on
an unresolved key; SCHEMA §10 says why that is an error and not a warning.
