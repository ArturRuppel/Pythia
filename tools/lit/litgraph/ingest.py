"""Orchestrate a single PDF ingest (spec §4 Stages A–D) into a reviewable Report."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import pdf as pdfmod
from . import store
from .citekey import _norm_doi, make_citekey
from .fulltext import extract_abstract, extract_reference_dois, to_markdown_report
from .model import Author, CuratedPaper, Stub, Work, map_type
from .roles import resolve_roles
from .sources.crossref import Crossref
from .sources.openalex import OpenAlex
from .venue import venue_token


class IngestError(Exception):
    """Unrecoverable ingest problem (no resolvable DOI, etc.)."""


@dataclass
class Report:
    pdf: str
    doi: str | None = None
    doi_source: str = ""  # "--doi" | "pdf" | "title-search"
    metadata_source: str = "openalex"  # "openalex" | "crossref" (focal metadata + refs origin)
    title_search_unverified: bool = False
    citekey: str = ""
    title: str = ""
    type: str = ""
    type_defaulted: bool = False
    year: int | None = None
    venue_display: str | None = None
    venue_token: str = ""
    authors: list[Author] = field(default_factory=list)
    n_referenced: int = 0  # ids in the focal work's reference list
    n_refs: int = 0  # references actually returned by OpenAlex
    refs_from_fulltext: bool = False  # neither API carried refs; DOIs read off the printed list
    stubs_only: bool = False  # backfill run: stubs merged, curated file / PDF / .md untouched
    stubs_added: list[str] = field(default_factory=list)
    stubs_deduped: list[str] = field(default_factory=list)
    stubs_pruned: list[str] = field(default_factory=list)  # stubs promoted to curated (§6.3 self-heal)
    refs_skipped: int = 0
    abstract_source: str = ""  # "openalex"/"crossref" | "fulltext:heading" | "fulltext:byline" | ""
    curated_path: str = ""
    pdf_renamed_to: str | None = None
    pdf_rename_skipped: bool = False
    fulltext_path: str | None = None
    dry_run: bool = False
    warnings: list[str] = field(default_factory=list)


def _enrich_names(work: Work, crossref_pairs: list[tuple[str, str]]) -> None:
    """Overwrite OpenAlex 'First Last' names with Crossref family/given when aligned."""
    if len(crossref_pairs) == len(work.authors) and crossref_pairs:
        for a, (fam, given) in zip(work.authors, crossref_pairs):
            a.family, a.given = fam, given


def _resolve_focal(pdf_path: str, doi_override: str | None, oa: OpenAlex, cr: Crossref, report: Report) -> Work:
    def _by_doi(doi: str, source: str) -> Work | None:
        """OpenAlex first, then Crossref (for papers OpenAlex hasn't indexed yet)."""
        work = oa.fetch_work(doi)
        if work is not None:
            report.doi_source, report.metadata_source = source, "openalex"
        else:
            work = cr.fetch_work(doi)
            if work is not None:
                report.doi_source, report.metadata_source = source, "crossref"
        if work is not None:
            # OpenAlex lowercases DOIs; keep the caller's canonical casing.
            work.doi = _prefer_casing(doi, work.doi)
        return work

    if doi_override:
        work = _by_doi(doi_override, "--doi")
        if work is None:
            raise IngestError(f"--doi {doi_override} did not resolve in OpenAlex or Crossref")
        return work
    doi = pdfmod.extract_doi(pdf_path)
    if doi:
        work = _by_doi(doi, "pdf")
        if work is not None:
            return work
    # Fallback: title search (OpenAlex only).
    title = pdfmod.extract_title(pdf_path)
    if title:
        work = oa.search_by_title(title)
        if work is not None:
            report.doi_source = "title-search"
            report.metadata_source = "openalex"
            report.title_search_unverified = True
            return work
    raise IngestError(
        "could not resolve a DOI from the PDF (no embedded DOI, title search failed). "
        "Re-run with --doi <doi>."
    )


def _resolve_ref_dois(dois: list[str], oa: OpenAlex, cr: Crossref) -> list[Work]:
    """Resolve a Crossref reference DOI list to Works: OpenAlex batch, Crossref per-DOI fallback.

    Unresolvable DOIs (e.g. DataCite dataset deposits Crossref doesn't carry) are dropped.
    """
    by_doi = {_norm_doi(w.doi): w for w in oa.fetch_works_by_doi(dois) if w.doi}
    out: list[Work] = []
    for d in dois:
        work = by_doi.get(_norm_doi(d)) or cr.fetch_work(d)
        if work is not None:
            out.append(work)
    return out


def _reference_text(pdf_path: str, citekey: str) -> str:
    """Full text to scan for a printed reference list: the stored `<citekey>.md` if this
    paper was already ingested, else a fresh extraction.

    Preferring the stored copy keeps a backfill run cheap and, more importantly, stable:
    re-extracting can hand a scanned page to pymupdf4llm's OCR path, which fails outright on
    a machine without tesseract language data — for a file we already have on disk.
    """
    stored = Path(pdf_path).with_name(f"{citekey}.md")
    if stored.is_file():
        return stored.read_text()
    return to_markdown_report(pdf_path)[0]  # residual is warned about on the .md-writing path


def _prefer_casing(local: str, canonical: str | None) -> str | None:
    """Keep `local`'s casing when it equals `canonical` case-insensitively."""
    if canonical and local and local.lower() == canonical.lower():
        return local
    return canonical


def _year_str(year: int | None) -> str:
    return str(year) if year is not None else ""


def ingest(
    pdf_path: str,
    *,
    root: str | Path,
    mailto: str = "",
    doi: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    stubs_only: bool = False,
    openalex: OpenAlex | None = None,
    crossref: Crossref | None = None,
) -> Report:
    root = Path(root)
    oa = openalex or OpenAlex(mailto=mailto)
    cr = crossref or Crossref(mailto=mailto)
    report = Report(pdf=str(pdf_path), dry_run=dry_run, stubs_only=stubs_only)

    # A/B — focal work.
    work = _resolve_focal(pdf_path, doi, oa, cr, report)
    report.doi = work.doi
    # Crossref-sourced focal already has clean family/given; only enrich OpenAlex names.
    if report.metadata_source != "crossref":
        _enrich_names(work, cr.author_names(work.doi) if work.doi else [])

    # Author roles: union OpenAlex order/flags with PDF markers.
    families = [a.family for a in work.authors]
    page_text = pdfmod.extract_text(pdf_path, max_pages=2)
    markers = pdfmod.extract_author_markers(page_text, families)
    authors = resolve_roles(work.authors, markers)

    # Citekey allocation (against existing keys; grows as references are added).
    taken = store.load_taken(root)
    vtoken = venue_token(work.venue_display)
    citekey = make_citekey(work.authors[0].family if work.authors else "", _year_str(work.year), vtoken, taken, work.doi)
    taken[citekey] = work.doi

    rtype = map_type(work.type_raw)
    report.citekey = citekey
    report.title = work.title
    report.type = rtype
    report.type_defaulted = rtype == "original" and (work.type_raw or "").lower() not in ("article", "journal-article", "original")
    report.year = work.year
    report.venue_display = work.venue_display
    report.venue_token = vtoken
    report.authors = authors

    paper = CuratedPaper(
        citekey=citekey,
        title=work.title,
        type=rtype,
        year=work.year,
        doi=work.doi,
        url=f"https://doi.org/{work.doi}" if work.doi else None,
        pdf=f"{citekey}.pdf",
        abstract=work.abstract,
        authors=authors,
    )

    # C — references -> stubs. OpenAlex ids when the focal came from OpenAlex; otherwise the
    # Crossref reference DOI list (resolved via OpenAlex batch + Crossref fallback). When
    # neither API carries references — the publisher never deposited them, and OpenAlex
    # mirrors Crossref here — fall back to the DOIs printed in the PDF's own reference list.
    if work.referenced_works:
        refs = oa.fetch_works(work.referenced_works)
        report.n_referenced = len(work.referenced_works)
    elif work.referenced_dois:
        refs = _resolve_ref_dois(work.referenced_dois, oa, cr)
        report.n_referenced = len(work.referenced_dois)
    else:
        focal = _norm_doi(work.doi) if work.doi else None
        # Journal footers repeat the focal DOI inside the reference section; drop it or the
        # paper cites itself.
        printed = [d for d in extract_reference_dois(_reference_text(pdf_path, citekey))
                   if _norm_doi(d) != focal]
        report.refs_from_fulltext = bool(printed)
        report.n_referenced = len(printed)
        refs = _resolve_ref_dois(printed, oa, cr) if printed else []
    report.n_refs = len(refs)
    stubs: list[Stub] = []
    for ref in refs:
        fam = ref.authors[0].family if ref.authors else ""
        if not fam and ref.year is None:
            report.refs_skipped += 1
            continue
        rvtoken = venue_token(ref.venue_display)
        rkey = make_citekey(fam, _year_str(ref.year), rvtoken, taken, ref.doi)
        taken[rkey] = ref.doi
        stubs.append(Stub(citekey=rkey, title=ref.title, year=ref.year, doi=ref.doi,
                          type=map_type(ref.type_raw),
                          authors=[a.display_name for a in ref.authors if a.display_name],
                          journal=ref.venue_display))

    # D — writes / rename. A stubs-only run backfills the reference frontier of a paper that
    # is already ingested (and possibly curated): it merges stubs and touches nothing else,
    # so a card built on top of the earlier ingest survives intact. Without it the only way
    # back into Stage C's merge is a re-ingest, which `write_curated` refuses (rightly)
    # unless --force, and --force would flatten the card.
    if stubs_only:
        report.curated_path = str(store.curated_dir(root) / f"{citekey}.yaml")
    else:
        # Abstract fallback. Springer Nature and Elsevier deposit none to Crossref, and OpenAlex
        # mirrors Crossref for abstracts, so `abstract_inverted_index` is null for most of the
        # Nature family — the metadata simply does not exist to fetch. The paper's own full text
        # has it, so read it from there (fulltext.extract_abstract). Done here, before the
        # curated file is written, and the same markdown is reused as `<citekey>.md` below, so
        # this costs no extra pymupdf4llm pass. Silence is the thing being fixed: a curated file
        # with no abstract and no complaint is how four papers reached the in-progress worklist
        # missing one, so every branch here says what happened.
        markdown: str | None = None
        residual: tuple[str, ...] = ()
        if paper.abstract:
            report.abstract_source = report.metadata_source
        else:
            markdown, residual = to_markdown_report(pdf_path)
            hit = extract_abstract(markdown, families)
            if hit is None:
                report.warnings.append(
                    f"no abstract: {report.metadata_source} carries none for this DOI and none "
                    f"could be anchored in the full text — add it to {citekey}.yaml by hand")
            else:
                paper.abstract = hit.text
                report.abstract_source = f"fulltext:{hit.anchor}"
                if hit.anchor == "byline":
                    report.warnings.append(
                        "abstract read from the full text's unlabelled lead paragraph (the paper "
                        "prints no 'Abstract' heading) — check it against the PDF")
                if hit.artifacts:
                    report.warnings.append(
                        "abstract may carry PDF text-layer damage (fused words: "
                        f"{', '.join(hit.artifacts)}) — fix by hand in {citekey}.yaml")

        curated_path = store.write_curated(root, paper, force=force, dry_run=dry_run)
        report.curated_path = str(curated_path)

        renamed = store.rename_pdf(Path(pdf_path), citekey, dry_run=dry_run)
        if renamed is None:
            report.pdf_rename_skipped = True
            report.warnings.append(f"{citekey}.pdf already exists beside the source — left the PDF in place")
            md_source = Path(pdf_path)
        else:
            report.pdf_renamed_to = str(renamed)
            md_source = renamed if not dry_run else Path(pdf_path)

        if dry_run:
            report.fulltext_path = str(Path(pdf_path).with_name(f"{citekey}.md"))
        else:
            if markdown is None:  # not already extracted for the abstract fallback above
                markdown, residual = to_markdown_report(str(md_source))
            # Reported here rather than at extraction so it fires on both paths: the abstract
            # fallback above may have done the pymupdf4llm pass already.
            if residual:
                report.warnings.append(
                    "legacy publisher-font encoding: ligatures and dashes were repaired, but "
                    "decimal points read as colons and multiplication signs as '3' "
                    f"({', '.join(repr(s) for s in residual)}) — check any numeric quote "
                    "against the PDF by eye")
            report.fulltext_path = str(store.write_fulltext(md_source, citekey, markdown, dry_run=False))

    added, deduped = store.merge_stubs(root, stubs, dry_run=dry_run)
    report.stubs_added = added
    report.stubs_deduped = deduped
    # This paper (and any earlier-curated one) is no longer a stub: drop the stale entry so
    # the build never trips the §6.3 curated/stub collision. `extra_keys` names the focal key
    # because in a dry run its curated file isn't on disk to be swept up.
    report.stubs_pruned = store.prune_curated_stubs(root, dry_run=dry_run, extra_keys=(citekey,))
    return report


@dataclass
class DoiStub:
    """What `stub_for_doi` resolved a DOI to. `created` is False when the DOI already named a
    paper in the library (curated or stub) and nothing was fetched or written."""
    citekey: str
    title: str = ""
    created: bool = False
    source: str = ""        # "openalex" | "crossref" | "" (already in the library)


def stub_for_doi(
    doi: str,
    *,
    root: str | Path,
    mailto: str = "",
    dry_run: bool = False,
    openalex: OpenAlex | None = None,
    crossref: Crossref | None = None,
) -> DoiStub:
    """Resolve a DOI to a citekey in the library, minting a `stubs.yaml` entry when it is not
    there yet — for `lit collection add`, which must accept a paper nobody has ingested or
    cited (a paywalled related-work paper may only ever be a stub).

    The stub is built exactly as Stage C builds a reference's: OpenAlex first, Crossref for
    what OpenAlex has not indexed, the same `<Family><Year><Venue>` key allocated against every
    key in use (a same-DOI key is reused, a clash gets its a/b/c suffix), and the same additive,
    comment-preserving `merge_stubs`. Like the focal paper of an ingest, the first author's
    family name is taken from Crossref's split when OpenAlex supplied the byline, because
    OpenAlex hands back one display string and splitting "Ana van der Berg" is a guess.
    """
    root = Path(root)
    want = _norm_doi(doi)
    if not want:
        raise IngestError(f"not a DOI: {doi!r}")
    taken = store.load_taken(root)
    for key, kdoi in taken.items():
        if _norm_doi(kdoi) == want:
            return DoiStub(citekey=key, title="", created=False)

    oa = openalex or OpenAlex(mailto=mailto)
    cr = crossref or Crossref(mailto=mailto)
    bare = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi.strip(), flags=re.IGNORECASE)
    work, source = oa.fetch_work(bare), "openalex"
    if work is None:
        work, source = cr.fetch_work(bare), "crossref"
    if work is None:
        raise IngestError(f"{bare} did not resolve in OpenAlex or Crossref")
    work.doi = _prefer_casing(bare, work.doi) or bare
    if source == "openalex":
        _enrich_names(work, cr.author_names(work.doi))

    fam = work.authors[0].family if work.authors else ""
    if not fam and work.year is None:
        raise IngestError(f"{bare}: no first author and no year — cannot build a citekey; "
                          f"add the stub to stubs.yaml by hand")
    key = make_citekey(fam, _year_str(work.year), venue_token(work.venue_display), taken, work.doi)
    stub = Stub(citekey=key, title=work.title, year=work.year, doi=work.doi,
                type=map_type(work.type_raw),
                authors=[a.display_name or f"{a.given} {a.family}".strip() for a in work.authors
                         if a.display_name or a.family],
                journal=work.venue_display)
    added, _ = store.merge_stubs(root, [stub], dry_run=dry_run)
    return DoiStub(citekey=key, title=work.title, created=bool(added), source=source)
