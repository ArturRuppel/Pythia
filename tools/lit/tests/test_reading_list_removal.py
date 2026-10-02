"""Execute reading-list changes offline, including failed and repeated taps."""
import shutil
import subprocess
from pathlib import Path

import pytest

VIEWER = Path(__file__).parents[1] / "litgraph/viewer/js"


def test_reading_list_removal():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed to execute viewer actions")
    search = (VIEWER / "14-search.js").read_text()
    app = (VIEWER / "19-app.js").read_text()
    helper = search[search.index("async function removeFromReadingList("):search.index("// LIVE-gated:")]
    controls = app[app.index("  const removingReading ="):app.index("  function stubRow(")]
    reading = app[app.index("  function reading(){"):app.index("  // ── search ──")]
    harness = r"""
const assert = require('node:assert/strict');
const GRAPH = {active:['Paper','Other']}, ACTIVE = new Set(GRAPH.active);
let LIVE = true, calls = [], events = [], updates = 0, alerts = [], renders = 0;
let resolveFetch;
let fetch = (url, options) => {
  calls.push([url, JSON.parse(options.body)]);
  return new Promise(resolve => { resolveFetch = resolve; });
};
const dispatchEvent = e => events.push(e);
class CustomEvent { constructor(type, opts) { this.type = type; this.detail = opts.detail; } }
const syncLanding = () => updates++, redraw = () => {};
const alert = msg => alerts.push(msg), render = () => renders++;
const scroller = () => ({scrollTop:42});
let handlers = [];
const act = fn => { handlers.push(fn); return 'data-a="'+handlers.length+'"'; };
const tx = x => x, plural = (n, s) => n+' '+s, pm = () => '', rowAuthors = () => '';
const push = () => { throw new Error('Removal must not open a paper'); };
const S = {tab:'reading', sort:'new'};
const PAPERS = {Paper:{title:'Paper title',pass:2,slices:[]}, Other:{pass:4,slices:[]}};
const SL = {Paper:{},Other:{}}, PK = ['Paper','Other'], SK = [], cites = {};
const PASS = ['Uncurated','Bibliography','Skeleton','Contextualized','Curated'];
const sec = title => '<h2>'+title+'</h2>', paged = (id, xs, n, fn) => xs.map(fn).join('');
const stubRow = () => '';
(async () => {
  let html = reading();
  assert.equal((html.match(/Remove from reading list/g)||[]).length, 2);
  const removal = handlers[1]();
  assert.equal(removingReading.has('Paper'), true);
  assert.match(readingRemoveButton('Paper'), /disabled/);
  await removeReading('Paper');
  assert.equal(calls.length, 1);
  assert.deepEqual(calls[0], ['active',{citekey:'Paper',active:false}]);
  assert.deepEqual(GRAPH.active, ['Paper','Other']);
  resolveFetch({ok:true,json:async () => ({ok:true})});
  await removal;
  assert.deepEqual(GRAPH.active, ['Other']);
  assert.equal(ACTIVE.has('Paper'), false);
  assert.equal(updates, 1);
  assert.equal(events[0].type, 'readinglistchange');
  assert.equal(events[0].detail.removed, 'Paper');
  assert.equal(readingRemoveButton('Paper'), '');
  assert.equal(removingReading.size, 0);
  assert.equal(alerts.length, 0);
  for (const response of [{ok:false}, {ok:true,json:async () => ({ok:false})}]) {
    const failed = removeReading('Other');
    resolveFetch(response);
    await failed;
    assert.deepEqual(GRAPH.active, ['Other']);
    assert.equal(ACTIVE.has('Other'), true);
    assert.equal(removingReading.size, 0);
    assert.doesNotMatch(readingRemoveButton('Other'), /disabled/);
  }
  fetch = async () => { throw new Error('offline'); };
  await removeReading('Other');
  assert.equal(alerts.length, 3);
  assert.equal(updates, 1);
  LIVE = false;
  assert.equal(readingRemoveButton('Other'), '');
  assert.doesNotMatch(reading(), /Remove from reading list/);
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    result = subprocess.run([node, "-e", helper + controls + reading + harness],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
