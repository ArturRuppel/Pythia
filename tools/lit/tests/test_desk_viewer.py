"""The desk in the viewer: derived from pass + validated, validated through the server, and no
trace left of the reading list it replaced. The app's own functions run under Node, cut straight
out of the bundle, so what is tested is what ships."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from litgraph.build import template_html

VIEWER = Path(__file__).parents[1] / "litgraph/viewer/js"


def _cut(text: str, start: str, end: str) -> str:
    return text[text.index(start):text.index(end, text.index(start))]


def _run(harness: str) -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed to execute viewer actions")
    card = (VIEWER / "03-card.js").read_text()
    search = (VIEWER / "14-search.js").read_text()
    app = (VIEWER / "19-app.js").read_text()
    code = (_cut(card, "function passCircle(", "function authLine(")
            + _cut(search, "async function validatePaper(", "// The pill lists the desk")
            + PRELUDE
            + _cut(app, "  const PASS = [", "  const CHEV =")
            + _cut(app, "  const validating = new Set();", "  function stubRow(")
            + _cut(app, "  const deskMeta =", "  // ── search ──")
            + harness)
    result = subprocess.run([node, "-e", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


PRELUDE = r"""
const assert = require('node:assert/strict');
const mk = (pass, validated, t) => ({cur: true, pass, validated, title: 'T', year: 2020,
  slices: [], authors: [], curation_updated: t});
const PAPERS = {
  Fresh: mk(2, null, 30),        // never validated → new
  Same: mk(3, 3, 50),            // validated at its pass → off the desk
  Behind: mk(3, 1, 40),          // curation moved past → changed
  Ahead: mk(1, 2, 20),           // the owner read further → changed (and flagged by the build)
  NoPass: mk(null, 0, 10),       // absent pass counts as 0 → off the desk
  Aim: {cur: true, aim: true, pass: null, validated: null, slices: []},
};
const COLLECTIONS = {review: {title: 'Review', papers: ['Behind', 'Same']}};
const CK = ['review'];
let LIVE = true, calls = [], events = [], alerts = [], renders = 0, IDX = 'cached';
const OFFLINE = {on: false}, OFFLINE_WHY = 'needs the server: this is the read-only offline copy';
let resolveFetch;
let fetch = (url, options) => {
  calls.push([url, JSON.parse(options.body)]);
  return new Promise(resolve => { resolveFetch = resolve; });
};
const listeners = {};
const addEventListener = (type, fn) => (listeners[type] = listeners[type] || []).push(fn);
const dispatchEvent = e => { events.push(e); (listeners[e.type] || []).forEach(fn => fn(e)); };
class CustomEvent { constructor(type, opts) { this.type = type; this.detail = opts.detail; } }
const document = {querySelectorAll: () => [], body: {classList: {contains: () => false}}};
const CSS = {escape: s => s};
const alert = msg => alerts.push(msg), render = () => renders++;
const scroller = () => ({scrollTop: 0});
let handlers = [];
const act = fn => { handlers.push(fn); return 'data-a="' + (handlers.length - 1) + '"'; };
const tx = x => String(x), plural = (n, s) => n + ' ' + s + (n === 1 ? '' : 's');
const rowAuthors = () => '', push = () => { throw new Error('validating must not open a paper'); };
const S = {tab: 'desk', sort: 'new', more: {}, deskColl: ''};
const sec = (title, n) => '<h2>' + title + '</h2>';
const paged = (id, xs, n, fn) => xs.map(fn).join('');
const tap = (html, label) => {                     // the handler behind the button saying `label`
  const m = [...html.matchAll(/<button[^>]*data-a="(\d+)"[^>]*>([^<]*)<\/button>/g)]
    .find(x => x[2].includes(label));
  assert.ok(m, 'no live button: ' + label);
  return handlers[+m[1]]();
};
const listed = html => [...html.matchAll(/class="pa-key">(\w+)</g)].map(m => m[1]);
"""


def test_the_desk_derivation():
    _run(r"""
    const d = deskKeys();
    assert.deepEqual(d.new, ['Fresh']);
    assert.deepEqual(d.changed, ['Behind', 'Ahead']);            // newest curation record first
    for (const k of ['Same', 'NoPass', 'Aim']) assert.equal(deskStatus(PAPERS[k]), null, k);
    assert.equal(deskStatus(PAPERS.Fresh), 'new');
    assert.deepEqual(deskKeys(new Set(['Behind', 'Same'])), {new: [], changed: ['Behind']});
    // the board's status mark: the validated pass solid, curation ahead of it line-shaded
    assert.match(vstat(PAPERS.Fresh), />new</);
    assert.match(vstat(PAPERS.Fresh), /pc-hatch/);
    assert.match(vstat(PAPERS.Behind), /curated 3/);
    assert.match(vstat(PAPERS.Behind), /pc-hatch/);
    assert.doesNotMatch(vstat(PAPERS.Same), /vmark|pc-hatch/);
    assert.doesNotMatch(vstat(PAPERS.Ahead), /vmark|pc-hatch/);  // only curation AHEAD is marked
    """)


def test_desk_tab_lists_groups_and_validate_takes_a_row_off_without_reload():
    _run(r"""
    (async () => {
      let html = desk();
      assert.deepEqual(listed(html), ['Fresh', 'Behind', 'Ahead']);
      assert.match(html, /<h2>New<\/h2>[\s\S]*Fresh[\s\S]*<h2>Changed<\/h2>/);
      assert.match(html, /new · curated 2 intro\+disc/);
      assert.match(html, /validated 1 abstract · curated 3 results/);
      // Validate sends the pass the page SHOWED
      const pending = tap(html, 'Validate · 3 results');
      assert.equal(validating.has('Behind'), true);
      assert.match(validateControls('Behind'), /Validating…/);
      assert.match(validateControls('Behind'), /disabled/);
      await validate('Behind', 3);                       // a second tap while pending: no POST
      assert.equal(calls.length, 1);
      assert.deepEqual(calls[0], ['validate', {citekey: 'Behind', pass: 3}]);
      assert.equal(PAPERS.Behind.validated, 1);          // nothing changes before the server says so
      resolveFetch({ok: true, json: async () => ({ok: true, citekey: 'Behind', validated: 3, pass: 3})});
      await pending;
      assert.equal(PAPERS.Behind.validated, 3);
      assert.equal(events.at(-1).type, 'deskchange');
      assert.equal(events.at(-1).detail.key, 'Behind');
      assert.equal(IDX, null);                           // the library's cached status is dropped
      assert.equal(validating.size, 0);
      assert.deepEqual(listed(desk()), ['Fresh', 'Ahead']); // gone from the desk, in place
      assert.equal(alerts.length, 0);
      // a lower level: the picker offers the levels below the pass, minus the one validated
      html = validateControls('Fresh');
      assert.match(html, /1 · abstract/);
      assert.match(html, /0 · ingested/);
      const lower = tap(html, '0 · ingested');
      resolveFetch({ok: true, json: async () => ({ok: true, validated: 0, pass: 2})});
      await lower;
      assert.deepEqual(calls.at(-1), ['validate', {citekey: 'Fresh', pass: 0}]);
      assert.equal(deskStatus(PAPERS.Fresh), 'changed');   // validated 0 < pass 2: still on it
      assert.doesNotMatch(validateControls('Fresh'), /0 · ingested/);
      // failures leave the paper where it was, say so, and keep the control live
      for (const response of [{ok: false}, {ok: true, json: async () => ({ok: false})}]) {
        const failed = validate('Ahead', 1);
        resolveFetch(response);
        await failed;
        assert.equal(PAPERS.Ahead.validated, 2);
        assert.equal(validating.size, 0);
        assert.doesNotMatch(validateControls('Ahead'), /disabled/);
      }
      fetch = async () => { throw new Error('offline'); };
      await validate('Ahead', 1);
      assert.equal(alerts.length, 3);
      assert.equal(PAPERS.Ahead.validated, 2);
    })().catch(error => { console.error(error); process.exitCode = 1; });
    """)


def test_collection_filter_offline_copy_and_static_build():
    _run(r"""
    S.deskColl = 'review';
    assert.deepEqual(listed(desk()), ['Behind']);
    assert.match(desk(), /Review<i>1<\/i>/);
    S.deskColl = '';
    // offline: the desk still lists; Validate stays in place, disabled, with its reason, no handler
    OFFLINE.on = true;
    const html = desk();
    assert.deepEqual(listed(html), ['Fresh', 'Behind', 'Ahead']);
    assert.match(html, /Validating needs the server/);
    assert.match(validateControls('Fresh'), /<button class="pa-btn pa-vbtn" disabled>/);
    assert.doesNotMatch(html, /pa-(vbtn|vlevel)"[^>]*data-a=/);   // no live write control
    OFFLINE.on = false;
    // a static `lit build`: the desk lists, nothing offers to write
    LIVE = false;
    assert.deepEqual(listed(desk()), ['Fresh', 'Behind', 'Ahead']);
    assert.doesNotMatch(desk(), /Validate/);
    """)


def test_bundle_has_the_desk_tab_and_no_reading_list():
    page = template_html()
    assert 'const TABS = ["library", "topics", "desk", "search"];' in page
    assert 'desk: "Desk"' in page
    assert 'id="desk"' in page and 'id="deskPanel"' in page
    assert 'fetch("validate"' in page
    for gone in ("reading list", "reading-list", "readinglist", "Reading ·", '"Reading"', "wipPanel",
                 "GRAPH.active", "ACTIVE", '"active"', 'fetch("active"', "Curate this paper",
                 "removeFromReadingList", "moveToCurate", "showCurateMenu", "pa-reading"):
        assert gone not in page, gone
    assert not re.search(r"\breading\s*:", page)         # no "reading" tab key left
    assert not re.search(r"\bwip\b", page)                # nor the WIP panel's pill class
