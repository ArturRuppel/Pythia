# tests/test_sanitize.py
"""The one rule for third-party bibliographic markup (litgraph.sanitize.safe_html)."""
import json

import pytest

from litgraph.build import emit, to_json_dict
from litgraph.graph import build_graph
from litgraph.sanitize import safe_html


@pytest.mark.parametrize("raw, safe", [
    # publisher formatting survives
    ("The <i>RAS</i> pathway", "The <i>RAS</i> pathway"),
    ("H<sub>2</sub>O and x<sup>2</sup>", "H<sub>2</sub>O and x<sup>2</sup>"),
    ("<b>bold</b> <em>em</em> <strong>s</strong>", "<b>bold</b> <em>em</em> <strong>s</strong>"),
    ("<I>Caps</I>", "<i>Caps</i>"),
    # attributes never survive, even on an allowed tag
    ('<i onmouseover="alert(1)">x</i>', "<i>x</i>"),
    ('<sup class="a" style="b">1</sup>', "<sup>1</sup>"),
    # anything else that could open markup is shown as text
    ("<img src=x onerror=alert(1)>", "&lt;img src=x onerror=alert(1)>"),
    ("<script>alert(1)</script>", "&lt;script>alert(1)&lt;/script>"),
    ('<a href="javascript:alert(1)">click</a>', '&lt;a href="javascript:alert(1)">click&lt;/a>'),
    ("<svg/onload=alert(1)>", "&lt;svg/onload=alert(1)>"),
    ("<!-- x --> <?php ?>", "&lt;!-- x --> &lt;?php ?>"),
    ("mean <Du> of <cos 2t>", "mean &lt;Du> of &lt;cos 2t>"),
    # nesting is balanced: unclosed tags are closed, stray closes dropped, overlaps untangled
    ("<i>open <b>both", "<i>open <b>both</b></i>"),
    ("stray</b> close", "stray close"),
    ("<i><b>x</i>y</b>", "<i><b>x</b></i>y"),
    ("<i/>empty", "empty"),
    # JATS / MathML / small caps: mapped where there is a kept tag, else unwrapped to the text
    ("<jats:p>One.</jats:p><jats:p>Two <jats:italic>it</jats:italic></jats:p>", "One. Two <i>it</i>"),
    ("<jats:sub>2</jats:sub><jats:bold>b</jats:bold>", "<sub>2</sub><b>b</b>"),
    ("<scp>dna</scp> <font>f</font>", "dna f"),
    ('<mml:math xmlns:mml="http://x"><mml:msub><mml:mi>x</mml:mi><mml:mn>2</mml:mn></mml:msub></mml:math>',
     "x2"),
    # text that cannot open markup, and entities, pass through byte-identical
    ("p < 0.05 & q > 1", "p < 0.05 & q > 1"),
    ("&lt;script&gt; &amp; &eacute; &#233;", "&lt;script&gt; &amp; &eacute; &#233;"),
    ("plain", "plain"),
    ("", ""),
])
def test_safe_html(raw, safe):
    assert safe_html(raw) == safe
    assert safe_html(safe) == safe            # idempotent: a second pass changes nothing


def test_non_strings_pass_through():
    assert safe_html(None) is None and safe_html(3) == 3


def _hostile_repo(tmp_path):
    (tmp_path / "curated").mkdir()
    (tmp_path / "curated" / "Smith2020Jrnl.yaml").write_text(
        'title: "Loss of <i>Abc1</i> <img src=x onerror=alert(1)>"\n'
        'type: original\nyear: 2020\n'
        'abstract: "We show <sub>2</sub> <script>alert(2)</script>."\n'
        'authors: [{name: "Smith, <b onclick=x>J</b>"}]\n')
    (tmp_path / "stubs.yaml").write_text(
        'Doe2019Jrnl:\n'
        '  title: "<scp>tgf</scp>-beta in <i>vivo</i><a href=\'javascript:x\'>!</a>"\n'
        '  year: 2019\n  type: original\n'
        '  journal: "Cells <iframe src=//x> & Tissues"\n'
        '  authors: [{name: "Doe, A"}]\n')
    return tmp_path


def test_third_party_strings_are_safe_in_the_payload(tmp_path):
    data = to_json_dict(build_graph(_hostile_repo(tmp_path)))
    paper = data["papers"]["Smith2020Jrnl"]
    assert paper["title"] == "Loss of <i>Abc1</i> &lt;img src=x onerror=alert(1)>"
    assert paper["abs"] == "We show <sub>2</sub> &lt;script>alert(2)&lt;/script>."
    assert paper["authors"][0][0] == "Smith, <b>J</b>"
    stub = data["stubs"]["Doe2019Jrnl"]
    assert stub["title"] == "tgf-beta in <i>vivo</i>&lt;a href='javascript:x'>!&lt;/a>"
    assert stub["journal"] == "Cells &lt;iframe src=//x> & Tissues"


def test_a_sanitised_title_round_trips_through_the_built_artifact(tmp_path):
    root = _hostile_repo(tmp_path)
    out = tmp_path / "dist"
    emit(build_graph(root), out)
    data = json.loads((out / "graph.json").read_text())
    assert data["papers"]["Smith2020Jrnl"]["title"] == \
        "Loss of <i>Abc1</i> &lt;img src=x onerror=alert(1)>"
    html = (out / "index.html").read_text()
    # inlined with every "<" written as a JS \u003c escape, so it parses back to the safe string
    assert "\\u003ci>Abc1\\u003c/i> &lt;img" in html
    assert "<img src=x" not in html and "<script>alert" not in html
