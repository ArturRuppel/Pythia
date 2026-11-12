# litgraph/sanitize.py
"""One rule for third-party bibliographic markup: the viewer may render it as HTML, safely.

Titles, abstracts, author names and venue names arrive from OpenAlex / Crossref (and from a PDF's
own text) carrying real publisher markup — `<i>RAS</i>`, `H<sub>2</sub>O`, JATS `<jats:p>`,
`<scp>`, MathML. The viewer puts those strings into `innerHTML` so the formatting shows, which
means a record holding `<img src=x onerror=…>` would run script in the curator's browser.

`safe_html` is the rule, applied where the payload is built (`build.to_json_dict`) and to the one
string the server fetches live (`/stub-abstract`):

  * the inline formatting tags `i em b strong sub sup` are kept, **with every attribute dropped**
    and nesting balanced (an unclosed `<i>` is closed at the end, a stray `</b>` is dropped);
  * known *presentational* markup that has no safe attribute-free equivalent — namespaced tags
    (`jats:*`, `mml:*`, …) and `scp`, `font`, `span`, `mark`, `p`, … — is unwrapped: the tag goes,
    its text stays (`<jats:italic>` / `<jats:sub>` … map onto the kept tags first);
  * every other `<` that could open markup is escaped to `&lt;`, so `<img …>`, `<script>`,
    `<a href="javascript:…">` and an author's `<Du>` all render as the literal text they are.

Nothing else is touched. A `<` followed by anything but a letter, `/`, `!` or `?` cannot open a tag
(HTML's tokenizer emits it as text), and `&` / `>` / quotes are inert in text content, so
`p < 0.05`, `A & B` and existing entities pass through byte-identical. The output is therefore
idempotent and survives a second, viewer-side pass of the same rule (`rich` in viewer/js/09-live.js)
unchanged. It is meant for **text content only** — never interpolate it into an attribute."""

from __future__ import annotations

import re

KEEP = frozenset({"i", "em", "b", "strong", "sub", "sup"})

# Markup with a kept equivalent: JATS spells italics/bold/sub/sup out, and some feeds use the
# long names unprefixed.
_MAP = {"italic": "i", "bold": "b", "sub": "sub", "sup": "sup", "em": "em", "strong": "strong",
        "i": "i", "b": "b"}

# Unprefixed presentational / structural tags that publishers emit: unwrap them (keep the text).
# Deliberately NOT a list of every HTML element — `<a>`, `<u>`, `<c>`, `<img>`, `<script>` are
# escaped and shown as text instead, which is both safe and honest (curated prose quotes maths
# such as `<a>` or `<u>` as averages).
_UNWRAP = frozenset({"scp", "sc", "smallcaps", "font", "span", "mark", "small", "tt", "p", "div",
                     "br", "sec", "title", "label", "caption", "list", "list-item",
                     "named-content", "inline-formula", "styled-content", "monospace"})
# Unwrapped tags that separated blocks of text: leave a space where they were so words don't fuse.
_BREAK = frozenset({"p", "div", "br", "sec", "title", "label", "caption", "list", "list-item"})

# A tag-shaped run: `<`, optional `/`, a name, anything up to the next `>` (attributes), `>`.
_TAG = re.compile(r"<(/?)([A-Za-z][A-Za-z0-9:._-]*)(\s[^<>]*|/)?>")
# A `<` that the HTML tokenizer would treat as the start of markup.
_OPENER = re.compile(r"<(?=[A-Za-z/!?])")


def _classify(name: str) -> tuple[str, str | None]:
    """('keep', tag) | ('unwrap', None) | ('escape', None) for a tag name."""
    low = name.lower()
    prefix, _, local = low.rpartition(":")
    if prefix:                                    # namespaced (jats:, mml:, xlink: …): markup
        return ("keep", _MAP[local]) if local in _MAP else ("unwrap", None)
    if low in KEEP:
        return "keep", low
    if low in _UNWRAP:
        return "unwrap", None
    return "escape", None


def safe_html(s):
    """`s` with only attribute-free inline formatting left as markup (see the module docstring).

    Non-strings (None, numbers) are returned unchanged, so it can wrap optional fields."""
    if not isinstance(s, str) or "<" not in s:
        return s
    out: list[str] = []
    stack: list[str] = []
    pos = 0
    gap = False         # an unwrapped block tag sat here: one space before the next text, if any

    def emit(piece: str) -> None:
        nonlocal gap
        if not piece:
            return
        if gap and out and not out[-1][-1].isspace() and not piece[0].isspace():
            out.append(" ")
        gap = False
        out.append(piece)

    def text(chunk: str) -> None:
        emit(_OPENER.sub("&lt;", chunk))

    for m in _TAG.finditer(s):
        text(s[pos:m.start()])
        pos = m.end()
        closing, name = m.group(1) == "/", m.group(2)
        kind, tag = _classify(name)
        if kind == "escape":
            text(m.group(0))
            continue
        if kind == "unwrap":
            if name.lower().rpartition(":")[2] in _BREAK:
                gap = True
            continue
        if not closing:
            if (m.group(3) or "").rstrip().endswith("/"):
                continue                          # `<i/>`: an empty element, nothing to wrap
            stack.append(tag)
            emit(f"<{tag}>")
        elif tag in stack:
            while stack:                          # close whatever was left open inside it
                t = stack.pop()
                out.append(f"</{t}>")
                if t == tag:
                    break
        # a close with no matching open is dropped
    text(s[pos:])
    out.extend(f"</{t}>" for t in reversed(stack))
    return "".join(out)


def safe_authors(authors):
    """An author list `[[name, position, corresponding], …]` with each name made safe."""
    return [[safe_html(n), pos, corr] for n, pos, corr in authors]
