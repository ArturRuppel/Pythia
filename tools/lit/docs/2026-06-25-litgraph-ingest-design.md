# `litgraph ingest` — design

**Status:** approved-pending-review · **Date:** 2026-06-25 · companion to
[CONCEPT.md](../../../CONCEPT.md) and [SCHEMA.md](../../../SCHEMA.md)

The first CLI for `literature_graph`. Given a human-supplied PDF of a paper, it
initializes that paper's **bibliographic skeleton** in the YAML source of truth: a
`curated/<citekey>.yaml` node (metadata + authors), a deduped `stubs.yaml` entry for
every paper it cites, and an **AI-parsable full-text artifact** (`<citekey>.md`) beside
the PDF for the future curation step to mine for quotes. It also **renames the PDF and
the full-text file to the standardized citekey** (`Ruppel2023eLife.pdf` / `.md`). It does
**not** extract affirmations or questions — that is the AI-curation step (CONCEPT §12), a
separate future tool.

Validated end-to-end against a real target,
`<pdf_dir>/Ruppel_et_al_2023_Force_propagation_eLife.pdf`
(DOI `10.7554/eLife.83588`).

---

## 1. Scope

**In scope**

- Resolve the focal paper from its PDF (DOI-anchored) and write `curated/<citekey>.yaml`
  with `title, type, year, doi, url, pdf, authors`.
- Extract the PDF's full text as **deterministic Markdown** (`pymupdf4llm`) and write it
  as `<citekey>.md` **beside the PDF** (outside git — same external dir).
- **Rename** the source PDF (and the `.md`) to the standardized citekey stem.
- Fetch the focal paper's reference list and write one bib-only stub per cited paper to
  the shared `stubs.yaml`, deduped by citekey.
- Non-interactive. Claude runs the tool; Claude + human review the written YAML together.
  `--dry-run` prints the proposed output (and planned renames) without writing.

**Out of scope (future)**

- Affirmation / question extraction, rollups, `claims/`, `questions/` (CONCEPT §12).
- The generator (YAML → `graph.db`) and catalog views.
- PDF acquisition / promotion of stubs.

---

## 2. Key decisions (each validated on the eLife target)

| Decision | Choice | Rationale / evidence |
|---|---|---|
| Stack | **Python** | Reliability-first (the only criterion the user gave); best PDF + OpenAlex/Crossref + YAML ecosystem. |
| Citation source | **DOI-anchored metadata fetch** (OpenAlex `referenced_works`), *not* PDF reference-list parsing | PDF reference parsing is the least reliable step. Validated: DOI → **86** referenced works, each with DOI/title/year. |
| Stub home | **Global `stubs.yaml`, deduped by citekey** | Schema-native (no new fields); shared cited papers become one stub. CONCEPT blesses a pre-populated "frontier of stubs". |
| Corresponding authors | **PDF is authority** (`*` markers + `For correspondence:` block) **∪ OpenAlex `is_corresponding`** | OpenAlex flagged only Schwarz and **missed Balland**; the PDF marks both. Union maximizes recall. |
| Author role model | **Split the conflated `position` enum into orthogonal axes** (see §3) | "first **and** corresponding" is common and the old single enum could not express it. |
| Interaction | **Non-interactive + `--dry-run`**; Claude-run, jointly reviewed | User: "the CLI is for you, you will run it and then we confirm validity together." |
| Author names | **OpenAlex for identity/order; Crossref for clean `family, given`** | OpenAlex gives "First Last"; re-splitting compound surnames is unreliable. Crossref splits cleanly; degrade to OpenAlex split if Crossref unavailable. |
| Full text | **Deterministic Markdown via `pymupdf4llm`**, written `<citekey>.md` beside the PDF (outside git) | The future curation step needs verbatim text for **exact quotes**; ML extractors risk altering text. Pure-Python, no infra. |
| Identifier convention | **`<Family><Year><Venue>`** CamelCase (e.g. `Ruppel2023eLife`) — supersedes SCHEMA §3 lowercase `smith2020a` | User-chosen; the key also names the PDF, the `.md`, the `curated/` file, and the `stubs.yaml` key. |
| Venue token | **ISO-4 abbreviation (LTWA-based) + small override map**, dots/spaces stripped | OpenAlex gives `display_name` but no `abbreviated_title`; ISO-4 is the *standard* abbreviation. Overrides handle brand names (`eLife`) and long titles (`BBA`). |
| PDF/`.md` rename | **Rename in place to `<citekey>.{pdf,md}`** in the external dir | User-requested; one standardized name ties file ↔ node ↔ stub key. Safe: never clobber; `--dry-run` previews. |

---

## 3. Author-role model change (SCHEMA + CONCEPT + example)

The current model conflates two orthogonal axes in one field:
`position: corresponding | first | middle`. This is the same conflation CONCEPT §6
already fixed once (splitting `backing` into orthogonal *evidence* and *citation* axes).
Apply the same move:

- **`position`** — `first | middle | last` (default `middle`). An **authorship tier**,
  *not* a strict byline index: **multiple authors may be `first`** (co-first / "contributed
  equally"); typically one `last` (senior author). Equal-contribution authors are simply
  additional `first`s — there is no separate `equal_contrib` flag.
- **`corresponding`** — optional `true` (absent ⇒ false). An **independent role**; any
  number of authors may carry it.
- Present-address (`‡`) and other byline footnotes are **not modeled**.

**Files to update** (part of implementation):

- `SCHEMA.md` §4 (author field row), §6 rule 6 (enums: `position ∈ {first,middle,last}`,
  add `corresponding ∈ {true}`).
- `CONCEPT.md` §4 and §13 (the `Author → Paper` edge attribute).
- `example/curated/ruppel2023.yaml` (fictional data — re-express under the new model;
  also rename the file under the new identifier convention, §3a).

**Expected `authors` block for the real eLife paper** (the acceptance target):

```yaml
authors:
  - {name: "Ruppel, Artur",       position: first}                    # co-first (†)
  - {name: "Wörthmüller, Dennis", position: first}                    # co-first (†)
  - {name: "Misiak, Vladimir"}
  - {name: "Kelkar, Manasi"}
  - {name: "Wang, Irène"}
  - {name: "Moreau, Philippe"}
  - {name: "Méry, Adrien"}
  - {name: "Révilloud, Jean"}
  - {name: "Charras, Guillaume"}
  - {name: "Cappello, Giovanni"}
  - {name: "Boudou, Thomas"}
  - {name: "Schwarz, Ulrich S",                  corresponding: true}  # byline-middle + corresponding
  - {name: "Balland, Martial",   position: last, corresponding: true}
```

---

## 3a. Identifier convention (supersedes SCHEMA §3)

The citekey becomes **`<Family><Year><Venue>`**, CamelCase, e.g. `Ruppel2023eLife`. It is
the single canonical id used for: the PDF filename, the `.md` filename, the
`curated/<key>.yaml` stem, and the `stubs.yaml` key.

- **Family** — first author's family name, ASCII-folded (`Wörthmüller → Worthmuller`,
  `Méry → Mery`), non-alphanumerics dropped, multi-token surnames Title-Cased and joined
  (`van der Berg → VanDerBerg`).
- **Year** — 4-digit publication year.
- **Venue** — ISO-4 abbreviation of `source.display_name` (LTWA-based library), dots and
  spaces stripped; a small curated **override map** for brand names and awkward titles.
  Worked examples:

  | journal (`display_name`) | venue token |
  |---|---|
  | eLife | `eLife` (override — no ISO-4 abbrev) |
  | Biophysical Journal | `BiophysJ` |
  | Developmental Cell | `DevCell` |
  | Biochimica et Biophysica Acta (BBA) - Molecular Cell Research | `BBA` (override) |

- **Disambiguation** — if two distinct DOIs collapse to the same key, append `a/b/c`. The
  venue token already separates same-author/same-year papers in different journals.
- **Same-DOI idempotence** — a key that resolves to the same DOI already present is reused,
  not suffixed (so re-ingesting, or two papers citing the same work, converge).

A reference with **no venue** in OpenAlex falls back to `<Family><Year>` (venue omitted),
flagged in the report.

---

## 4. Pipeline

### Stage A — Resolve the focal DOI
1. Extract text from the first ~2 pages + embedded PDF/XMP metadata.
2. Regex candidate DOIs: `10\.\d{4,9}/[-._;()/:A-Za-z0-9]+`; choose the best candidate
   (dedupe; prefer one also present in metadata or repeated in text).
3. Validate by resolving in OpenAlex.
4. Fallbacks, in order: `--doi` override (wins outright) → for a *known* DOI not yet in
   OpenAlex, **Crossref metadata fallback** (`metadata_source = crossref`, flagged in the
   report — covers papers published too recently to be indexed) → OpenAlex **title search**
   (title from PDF metadata / first heading), take the top hit and **flag low-confidence
   in the report** → otherwise hard-fail with a clear "pass `--doi`" message.

### Stage B — Focal metadata → `curated/<citekey>.yaml`
- **OpenAlex work**: `title, publication_year, type, doi, authorships`
  (order, `author_position`, `is_corresponding`, `display_name`, raw markers).
- **Crossref work** (by DOI): author `family`/`given` → `"family, given"`; fall back to
  splitting the OpenAlex `display_name` on the last space if Crossref is unavailable.
- **Type map** → `{original|review|methods|perspective|commentary}`: `review → review`,
  everything else `→ original` (default), **flagged** in the report for human override.
- **Corresponding set** = union(PDF `*`-marked authors, PDF `For correspondence:`
  email→author map, OpenAlex `is_corresponding`).
- **Positions**: byline index 0 → `first`; members of an equal-contribution group
  (PDF `†` + "contributed equally") that includes the front → `first`; byline index n-1 →
  `last`; otherwise `middle`.
- **citekey**: `<Family><Year><Venue>` per §3a (`Ruppel2023eLife`), disambiguated (§5).
- **`pdf`**: store the post-rename filename `<citekey>.pdf`.

### Stage B′ — Full text → `<citekey>.md` (beside the PDF)
- Extract the whole PDF to Markdown with `pymupdf4llm` (deterministic; section headings;
  de-hyphenation + whitespace/ligature/zero-width normalization so quotes match verbatim).
- Write `<citekey>.md` next to the PDF in the external dir (outside git). Skipped under
  `--dry-run` (the report states it would be written). This is the artifact the future
  curation step mines for exact `quote`s.

### Stage C — References → stub records
- **OpenAlex focal**: read the focal work's `referenced_works` (list of OpenAlex IDs) and
  batch-fetch (~50 IDs/request, paginated) selecting
  `id, doi, display_name, publication_year, authorships, type`.
- **Crossref focal** (fallback, Stage A): read the reference DOI list from the Crossref
  record instead, then resolve those DOIs to works — OpenAlex batch (`filter=doi:…`) with a
  per-DOI Crossref fallback. DOI-less references (e.g. books) and DataCite deposits (e.g.
  Zenodo datasets) Crossref doesn't carry are **not auto-resolved** (add manually if wanted).
- Per reference → stub `{title, year, doi?, type?}`; citekey `<Family><Year><Venue>` per
  §3a (venue omitted if OpenAlex has none).
- Keep DOI-less references (schema `doi` is optional). Skip a reference missing **both**
  author and year (warn; partial graph is valid).
- **One stub on its own** (added 2026-10-29, `ingest.stub_for_doi`): `lit collection add <slug>
  <doi>` needs a stub for a paper nobody has ingested or cited. Same rules as a reference — a DOI
  already in the library returns its key and fetches nothing; otherwise OpenAlex, then Crossref,
  the same citekey allocation and the same additive `merge_stubs` — plus the focal paper's
  Crossref family-name split for the first author (SCHEMA §10).

### Stage D — Write / merge / rename
- **Rename** the source PDF to `<pdf_dir>/<citekey>.pdf` (a move, in place). Never clobber
  an existing different file; if `<citekey>.pdf` already exists, leave the source and warn.
- `curated/<citekey>.yaml`: **refuse to overwrite** an existing file unless `--force`.
- `stubs.yaml`: `ruamel.yaml` round-trip (preserves human comments/formatting); **additive
  merge**, never deletes. Dedupe by citekey. A reference whose citekey is already a
  `curated/` paper (same DOI) is **not** added as a stub. A citekey collision with a
  *different* DOI gets an `a/b/c` suffix.
- `--dry-run`: print proposed file contents, planned renames, and the evidence report;
  write/rename nothing.
- **Evidence report** (so joint review is fast): focal DOI + how it was found; type guess;
  per-author `position`/`corresponding` with the signal that set each; venue→token per
  paper; planned PDF/`.md` renames; #refs fetched, #new stubs, #deduped, #skipped.

---

## 5. Components (`litgraph/` package)

Each unit has one purpose, a small interface, and is independently testable.

| Module | Responsibility | Key interface |
|---|---|---|
| `cli.py` | Arg parsing; invoke ingest; print report | `lit ingest <pdf> [--doi] [--root] [--dry-run] [--force]` |
| `config.py` | Load `config.toml` | `load_config(root) -> Config(root, pdf_dir, mailto)` |
| `pdf.py` | PDF reading (text/metadata/markers) | `extract_doi`, `extract_title`, `extract_author_markers` (`*`/`†`/correspondence emails) |
| `fulltext.py` | PDF → AI-parsable Markdown | `to_markdown(pdf_path) -> str` (pymupdf4llm + normalization) |
| `sources/openalex.py` | OpenAlex client | `fetch_work(doi)`, `search_by_title(t)`, `fetch_works(ids)` |
| `sources/crossref.py` | Crossref client (author names only) | `fetch_work(doi)` |
| `venue.py` | Journal name → venue token | `venue_token(display_name) -> str` (ISO-4 + override map) |
| `model.py` | Normalized dataclasses + schema serialization | `Work`, `Author`, `CuratedPaper`, `Stub`; `to_yaml()` |
| `citekey.py` | Citekey generation | `make_citekey(family, year, venue, taken) -> str` (ASCII-fold + suffix) |
| `roles.py` | Merge OpenAlex + PDF signals | `resolve_roles(authorships, markers) -> [Author]` |
| `store.py` | Filesystem I/O + merge + rename | read existing citekeys; `merge_stubs` (ruamel); `write_curated`; `rename_pdf`; existence checks |
| `ingest.py` | Orchestrate stages A–D | `ingest(pdf, opts) -> Report` |

PDF text/marker fixtures and recorded API JSON make every unit testable offline.

---

## 6. Config — `config.toml` at the data root

```toml
root    = "."                      # holds curated/, stubs.yaml
pdf_dir = "/path/to/Literature"
mailto  = "you@example.org"        # OpenAlex/Crossref polite pool
```

---

## 7. Error handling

- No DOI in PDF, no `--doi`, no confident title match → exit non-zero with a clear message.
- OpenAlex unreachable → try Crossref for the focal paper; references **require** OpenAlex
  (Crossref's reference array is lower quality) → write the focal skeleton, warn that refs
  were skipped (partial success is allowed).
- HTTP: timeouts + retry/backoff, always with the polite-pool `mailto`.
- Reference missing author **and** year → skip + warn.
- `curated/<citekey>.yaml` exists → refuse unless `--force`.

---

## 8. Testing

Offline & deterministic via recorded fixtures (canned OpenAlex/Crossref JSON for
`eLife.83588` + a handful of its references; a saved PDF-text snippet for marker parsing).

- **Unit**: DOI regex; citekey `<Family><Year><Venue>` build + ASCII-fold + disambiguation;
  `venue.venue_token` (eLife/BiophysJ/DevCell/BBA override cases); type map; `Work`
  normalization; `roles.resolve_roles` (the Balland union case; Ruppel/Wörthmüller
  co-first); stub merge/dedup/suffix in a temp root; author-marker parsing.
- **Integration**: ingest from a fixture (DOI-bypass) into a temp root with a tiny stub PDF
  → assert the exact `curated/Ruppel2023eLife.yaml`, the `stubs.yaml` entries (86 refs → N
  stubs), the PDF rename to `Ruppel2023eLife.pdf`, and that `Ruppel2023eLife.md` is written;
  `--dry-run` writes/renames nothing.
- The real eLife PDF is the **manual acceptance** target; the `example/` tree's fictional
  DOIs are not used in tests.

---

## 9. Known limitations / future

- Title-search fallback is best-effort and flagged for human confirmation.
- `type` beyond `original`/`review` is human-set (services can't tell perspective/commentary).
- Equal-contribution detection depends on PDF footnote text; co-*last* groups handled by
  symmetric last-grouping; the report flags inferred groupings.
- Venue token relies on an ISO-4 library (imperfect) + a hand-maintained override map; the
  report shows each `display_name → token` so wrong ones are caught in joint review.
- The PDF rename mutates the user's external dir (a move). It never clobbers; `--dry-run`
  previews. The `.md` is regenerable, so losing it is harmless.
- `methods`/affirmation extraction/the generator are later tools.

---

## 10. CLI surface

```
lit ingest <pdf> [--doi DOI] [--root DIR] [--dry-run] [--force]
lit collection add <slug> <citekey|doi>... [--root DIR] [--dry-run]   # mints stubs (Stage C rules)
```
