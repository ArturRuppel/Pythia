# tests/test_quotes.py
"""Quote polishing: artifact stripping, sentence expansion, the two-tier polish, and the
polish_graph integration (offline — inline `.md` text, no network)."""

from pathlib import Path

import fitz

from litgraph.graph import Graph, Paper, Slice
from litgraph.quotes import (polish, polish_graph, polish_quote, quote_loc_covers, strip_artifacts,
                             verify_quote_locs_graph)


# --- strip_artifacts ---------------------------------------------------------

def test_strip_numeric_bracket_cites():
    assert strip_artifacts("A jammed tissue is solid-like [1].") == "A jammed tissue is solid-like."
    assert strip_artifacts("shown before [3–5, 7] and since") == "shown before and since"


def test_strip_author_year_single_and_chain():
    assert strip_artifacts("evidence of unjamming (Spurlin et al., 2019).") == "evidence of unjamming."
    s = "termed cell unjamming (Atia et al., 2018; Garcia et al., 2015; Park et al., 2015, 2016)."
    assert strip_artifacts(s) == "termed cell unjamming."


def test_strip_markdown_emphasis_wrapped_cites():
    s = ("universal property of mammalian cells "
         "( _**Vicente- Manzanares et al., 2009**_ ).")
    assert strip_artifacts(s) == "universal property of mammalian cells."


def test_strip_figure_and_see_callouts():
    assert strip_artifacts("the shape index (Fig. 3b) determines phase") == "the shape index determines phase"
    assert strip_artifacts("as described (see Methods) below") == "as described below"


def test_keeps_content_parentheticals():
    # a name-then-year is a cite; these are not -> preserved
    for keep in ["explants (N = 16) reveals",
                 "nucleus shape (CeNuS) and low density",
                 "criteria (tumor diameter, tumor grade, lymph node status) used"]:
        assert strip_artifacts(keep) == keep


def test_mid_sentence_strip_leaves_clean_seams():
    s = "differentiation (Engler et al., 2006), fate (Chen et al., 1997), or migration."
    assert strip_artifacts(s) == "differentiation, fate, or migration."


# --- polish: expansion, tiers, fallback --------------------------------------

FULLTEXT = (
    "In gastrulation of the developing fruit fly embryo, ventral furrow formation is a "
    "signature of unjamming (Atia et al., 2018; Bi et al., 2014, 2015). "
    "The shape index, as shown in Fig. 3, determines the phase.\n"
)


def test_polish_expands_anchor_to_sentence_and_strips():
    disp, status = polish("ventral furrow formation is a signature of unjamming", FULLTEXT)
    assert status == "verbatim"
    assert disp == ("In gastrulation of the developing fruit fly embryo, ventral furrow "
                    "formation is a signature of unjamming.")


def test_polish_abbreviation_does_not_end_sentence():
    disp, status = polish("determines the phase", FULLTEXT)
    assert status == "verbatim"
    # must not break at "Fig." — the whole sentence comes back
    assert disp == "The shape index, as shown in Fig. 3, determines the phase."


def test_polish_stops_at_period_glued_to_bracket_cite():
    # a citation bracket hugging the terminal period must not hide the sentence boundary
    ft = ("cell jamming is seen in development, wound healing, and fibrosis.[16] "
          "Underlying events are coming to light.[15,17,18]\n")
    disp, status = polish("cell jamming is seen in development", ft)
    assert status == "verbatim"
    assert disp == "cell jamming is seen in development, wound healing, and fibrosis."


def test_polish_not_found_strips_without_expanding():
    disp, status = polish("a claim not present [9] in the text", FULLTEXT)
    assert status == "not_found"
    assert disp == "a claim not present in the text"


def test_polish_empty_fulltext_is_not_found():
    disp, status = polish("anything at all", "")
    assert status == "not_found"
    assert disp == "anything at all"


def test_polish_joined_quote_polishes_each_segment():
    ft = "First sentence about coupling. A middle one. Then the disruption result here.\n"
    disp, status = polish("about coupling [...] the disruption result", ft)
    assert status == "joined"
    assert disp == "First sentence about coupling. […] Then the disruption result here."


def test_polish_join_with_a_segment_absent_is_not_found():
    # the stitched-in segment is not in the paper (a superscript lost in transcription)
    ft = "The rate scales as N<sup>−1</sup> at high density. Nothing else here.\n"
    r = polish_quote("The rate scales as [...] N−1 at high density", ft)
    assert r.status == "not_found"
    assert r.missing == [2] and r.segments == 2


def test_polish_join_segments_out_of_order_is_not_found():
    ft = "First sentence about coupling. A middle one. Then the disruption result here.\n"
    r = polish_quote("the disruption result [...] about coupling", ft)
    assert r.status == "not_found" and r.missing == [2]


def test_polish_join_searches_each_segment_after_the_previous():
    # "the cells" occurs first in the opening sentence; the join's second segment must be
    # matched after "we then imaged", i.e. at its second occurrence
    ft = "the cells were plated. Later we then imaged the cells moving apart.\n"
    r = polish_quote("we then imaged [...] the cells moving", ft)
    assert r.status == "joined" and r.gaps == [1]


def test_polish_join_gaps_are_the_tightest_reading():
    # the first segment also occurs far earlier (an abstract repeating it): the gap reported
    # is to the occurrence just before the second segment, not the first match in the text
    ft = ("Cells jam at confluence. " + "Filler sentence. " * 20
          + "Cells jam at confluence, and then they stop moving.\n")
    r = polish_quote("Cells jam at confluence [...] they stop moving", ft)
    assert r.status == "joined"
    assert r.gaps == [len(", and then ")]


def test_polish_join_three_segments_reports_every_gap():
    ft = "Alpha one. Beta two. Gamma three.\n"
    r = polish_quote("Alpha one [...] Beta two [...] Gamma three", ft)
    assert r.status == "joined" and r.segments == 3 and r.gaps == [2, 2]


# --- polish_graph integration ------------------------------------------------

def _graph(*slices: Slice) -> Graph:
    p = Paper(citekey="Demo2020Jour", curated=True, title="t", type="original", year=2020,
              slices=list(slices))
    return Graph(papers={"Demo2020Jour": p}, broad={}, order=["Demo2020Jour"])


def test_polish_graph_sets_display_and_flags(tmp_path: Path):
    (tmp_path / "Demo2020Jour.md").write_text(
        "We show that cells jam near the transition (Smith et al., 2019). The end.\n",
        encoding="utf-8")
    g = _graph(
        Slice(id="c1", kind="claim", text="cells jam", quote="cells jam near the transition"),
        Slice(id="c2", kind="claim", text="absent", quote="a quote not in the md at all"),
    )
    warns = polish_graph(g, tmp_path)
    c1, c2 = g.papers["Demo2020Jour"].slices
    assert c1.quote_display == "We show that cells jam near the transition."
    assert c2.quote_display == "a quote not in the md at all"           # stripped-only fallback
    assert any("c2" in w and "not found" in w for w in warns)
    assert not any("c1" in w for w in warns)


def test_polish_graph_flags_join_by_segment(tmp_path: Path):
    (tmp_path / "Demo2020Jour.md").write_text(
        "First sentence about coupling. A middle one. Then the disruption result here.\n",
        encoding="utf-8")
    g = _graph(
        Slice(id="c1", kind="claim", text="ok", quote="about coupling [...] the disruption result"),
        Slice(id="c2", kind="claim", text="bad", quote="about coupling [...] a segment not in it"),
        Slice(id="c3", kind="claim", text="swap", quote="the disruption result [...] about coupling"),
    )
    warns = {w.split(" ", 1)[0]: w for w in polish_graph(g, tmp_path)}
    gap = len(". A middle one. Then ")
    assert warns["Demo2020Jour:c1"].endswith(
        f"authored [...] join — verify the segments (2 found in order; chars cut: {gap})")
    for sid in ("c2", "c3"):
        assert warns[f"Demo2020Jour:{sid}"].endswith(
            "quote not found verbatim in the full text: [...] segment 2 of 2 (searched in order)")


def test_polish_graph_join_without_md_is_flagged_like_a_plain_quote(tmp_path: Path):
    g = _graph(Slice(id="c1", kind="claim", text="x", quote="some anchor [...] more text"))
    assert polish_graph(g, tmp_path) == [
        "Demo2020Jour:c1 quote not found verbatim in the full text (no Demo2020Jour.md)"]


def test_polish_graph_no_md_flags_all_quotes(tmp_path: Path):
    g = _graph(Slice(id="c1", kind="claim", text="x", quote="some anchor text"))
    warns = polish_graph(g, tmp_path)   # empty dir -> no Demo2020Jour.md
    assert g.papers["Demo2020Jour"].slices[0].quote_display == "some anchor text"
    assert any("no Demo2020Jour.md" in w for w in warns)


def test_polish_graph_skips_stubs_and_quoteless(tmp_path: Path):
    p_stub = Paper(citekey="Stub2019Jour", curated=False, title="t", type="original", year=2019)
    p_stub.slices = [Slice(id="c1", kind="claim", text="x", quote="ignored")]  # stub, skip
    g = Graph(papers={"Stub2019Jour": p_stub}, broad={}, order=["Stub2019Jour"])
    assert polish_graph(g, tmp_path) == []
    assert p_stub.slices[0].quote_display is None


# --- quote_loc_covers: tolerant comparison ------------------------------------

def test_quote_loc_covers_exact_match():
    assert quote_loc_covers("cells jam near the transition", "cells jam near the transition")


def test_quote_loc_covers_tolerates_ligatures():
    # the PDF text layer yields a ligature glyph where the authored quote spells it out
    assert quote_loc_covers("the tissue is ﬂuid-like at low density",
                             "the tissue is fluid-like at low density")


def test_quote_loc_covers_tolerates_end_of_line_hyphenation():
    for extracted, quote in [
        ("a three-dimen-\nsional structure emerges", "a three-dimensional structure emerges"),
        ("carefully consid-\nered before publication", "carefully considered before publication"),
        ("worth ex-\nplaining in detail here", "worth explaining in detail here"),
    ]:
        assert quote_loc_covers(extracted, quote)


def test_quote_loc_covers_tolerates_arbitrary_whitespace():
    assert quote_loc_covers("cells   jam\nnear   the\ntransition", "cells jam near the transition")


def test_quote_loc_covers_tolerates_watermark_prefix_junk():
    # a diagonal "Downloaded from ..." watermark bleeds a few glyphs into the clip rect
    for junk in ("gpg", "ygyy", "p"):
        extracted = junk + "cells jam near the transition boundary"
        assert quote_loc_covers(extracted, "cells jam near the transition boundary")


def test_quote_loc_covers_flags_a_genuinely_different_sentence():
    extracted = "temperature increases steadily throughout the whole experiment"
    quote = "cells jam near the transition boundary in every replicate"
    assert not quote_loc_covers(extracted, quote)


def test_quote_loc_covers_is_inconclusive_on_tiny_inputs():
    # too short to fingerprint reliably -> prefer the false negative, don't flag
    assert quote_loc_covers("ab", "cells jam near the transition")
    assert quote_loc_covers("cells jam near the transition", "ab")
    assert quote_loc_covers("", "cells jam near the transition")


# --- verify_quote_locs_graph: PDF-backed integration --------------------------

def _rect_frac(page: "fitz.Page", text: str) -> list[list[float]]:
    w, h = page.rect.width, page.rect.height
    return [[r.x0 / w, r.y0 / h, r.x1 / w, r.y1 / h] for r in page.search_for(text)]


def _two_line_pdf(path: Path) -> None:
    with fitz.open() as doc:
        pg = doc.new_page()
        pg.insert_text((72, 100), "cells jam near the transition boundary")
        pg.insert_text((72, 140), "temperature increases steadily afterward")
        doc.save(str(path))


def test_verify_quote_locs_graph_passes_a_correct_weld(tmp_path: Path):
    pdf_path = tmp_path / "Demo2020Jour.pdf"
    _two_line_pdf(pdf_path)
    with fitz.open(pdf_path) as doc:
        good_rects = _rect_frac(doc[0], "cells jam near the transition boundary")
    g = _graph(Slice(id="c1", kind="claim", text="x", quote="cells jam near the transition boundary",
                      quote_loc={"page": 0, "rects": good_rects}))
    assert verify_quote_locs_graph(g, tmp_path) == []


def test_verify_quote_locs_graph_flags_a_mis_parented_weld(tmp_path: Path):
    # simulates the silent re-parenting bug: a slice's quote_loc ends up pointing at a
    # DIFFERENT slice's sentence (store._place_quote_loc fixes the write path; this is the
    # standing check that would have caught it even if the write path regressed).
    pdf_path = tmp_path / "Demo2020Jour.pdf"
    _two_line_pdf(pdf_path)
    with fitz.open(pdf_path) as doc:
        wrong_rects = _rect_frac(doc[0], "temperature increases steadily afterward")
    g = _graph(Slice(id="c1", kind="claim", text="x", quote="cells jam near the transition boundary",
                      quote_loc={"page": 0, "rects": wrong_rects}))
    warns = verify_quote_locs_graph(g, tmp_path)
    assert len(warns) == 1
    assert "c1" in warns[0] and "quote_loc does not cover its quote" in warns[0]


def test_verify_quote_locs_graph_skips_missing_pdf_and_uncovered_slices(tmp_path: Path):
    g = _graph(
        Slice(id="c1", kind="claim", text="x", quote="anything at all"),                # no quote_loc
        Slice(id="c2", kind="claim", text="y", quote_loc={"page": 0, "rects": [[0, 0, 1, 1]]}),  # no quote
    )
    assert verify_quote_locs_graph(g, tmp_path) == []   # no Demo2020Jour.pdf on disk -> skipped


def test_verify_quote_locs_graph_flags_out_of_range_page(tmp_path: Path):
    pdf_path = tmp_path / "Demo2020Jour.pdf"
    _two_line_pdf(pdf_path)
    g = _graph(Slice(id="c1", kind="claim", text="x", quote="cells jam near the transition boundary",
                      quote_loc={"page": 3, "rects": [[0.1, 0.1, 0.5, 0.2]]}))
    warns = verify_quote_locs_graph(g, tmp_path)
    assert len(warns) == 1 and "c1" in warns[0] and "out of range" in warns[0]

