# litgraph/endpoints.py
"""What the two viewer servers actually share — no HTTP framework, either way.

`lit serve` (stdlib `http.server`) and the labbook's Flask plugin expose the same viewer
over the same data. They already share the validation regexes and `locate_quote`; what they
kept re-implementing was the two things below, and both had drifted:

  * **the payload.** Each grew its own `_payload_dict`. `lit serve`'s learned `views` and
    `include_aims` (and, while the curation cockpit was still current, a `cockpit` flag —
    retired along with it, see CURATION.md); the plugin's did not, so the labbook served a
    viewer that was quietly a version behind. One function now, with the serve-only extras
    as arguments that default to off — a static `lit build` artifact still never sees them.
  * **the PDF guard.** "validate the citekey, find the file, run a pdfview function, turn
    any failure into a 404" appeared six times in the plugin and six more in `lit serve`,
    written slightly differently each time.

Nothing here imports Flask or `http.server`: failures raise `HttpError`, and each adapter
decides how to write a status and a body. That is the whole seam — it keeps this module
testable without a socket, which is how the plugin gets test coverage at all."""

from __future__ import annotations

from pathlib import Path

from litgraph.build import to_json_dict
from litgraph.graph import build_graph
from litgraph.quotes import polish_graph


class HttpError(Exception):
    """A failure with a status already decided. Adapters map it straight to a response."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def payload_dict(root: Path, pdf_dir: Path, *,
                 include_aims: bool = False, views: list[dict] | None = None) -> dict:
    """graph.json as a dict, rebuilt from the repo's YAML — the one place it is computed.

    May raise `BuildError`: a repo mid-edit is a normal state, and both servers turn that
    into a readable 500 so the fix is edit-and-refresh rather than restart. Quotes are
    polished against the `.md` full text in `pdf_dir` (falling back to the raw anchor when a
    paper has no `.md`). Each paper's `pass` and `validated` ride in it, so the viewer derives
    the desk (SCHEMA §4) from the payload alone.

    `views` and `include_aims` are serve-only: a `lit build` artifact has no server to answer
    `/views/`, so it never receives that key and never grows the dropdown it feeds."""
    graph = build_graph(root)
    polish_graph(graph, pdf_dir)
    out = to_json_dict(graph, include_aims=include_aims)
    if views:
        out["views"] = views
    return out


def pdf_path(pdf_dir: Path, key: str, key_re) -> Path:
    """`<pdf_dir>/<key>.pdf`, or a 404 — the citekey pattern is what stops path traversal.

    `key_re` is passed in rather than imported so this module stays free of the serve
    layer it is meant to be shared *by*."""
    pdf = pdf_dir / (key + ".pdf")
    if not key_re.match(key) or not pdf.is_file():
        raise HttpError(404, f"no PDF: {key}")
    return pdf


def pdf_result(pdf: Path, fn, *args, fail: str, status: int = 404):
    """Run a `pdfview` function over a PDF, turning any failure into an `HttpError`.

    The blanket except is deliberate: the callers ask for an out-of-range page or a
    malformed document, and every one of those is a 404 to the viewer rather than a
    stack trace on the curator's screen."""
    try:
        return fn(pdf, *args)
    except Exception as e:  # noqa: BLE001 — see the docstring
        raise HttpError(status, fail) from e
