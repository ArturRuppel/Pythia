"""Execute the offline copy's service worker (viewer/sw.js) against an in-memory cache.

The worker decides where every answer comes from when the app is installed: cached PDFs cut
to byte ranges, the page and graph from the server unless it is down, and nothing else
touched. Node provides Request/Response/Headers/Blob; the worker's globals are stubbed."""
import shutil
import subprocess
from pathlib import Path

import pytest

SW = Path(__file__).parents[1] / "litgraph/viewer/sw.js"

HARNESS = r"""
const assert = require('node:assert/strict');
const ROOT = 'https://host.example:8000/';
const store = new Map();                 // the one cache: absolute URL -> Response
const caches = {
  open: async () => ({ match: async (u) => (store.has(u) ? store.get(u).clone() : undefined) }),
  keys: async () => ['pythia-offline-v1'], delete: async () => true,
};
let net = null, fetched = [];            // what the "server" does with the next request
const fetch = (req) => { fetched.push(req.url); return net(req); };
const listeners = {};
const self = { registration: { scope: ROOT }, location: { origin: 'https://host.example:8000' },
               addEventListener: (t, fn) => { listeners[t] = fn; }, skipWaiting() {},
               clients: { claim: async () => {} } };
const setTimeout = (fn) => globalThis.setTimeout(fn, 0);   // the 4 s timeout, after the microtasks
const clearTimeout = (t) => globalThis.clearTimeout(t);
""" + "\n{SW}\n" + r"""
const PDF = new Uint8Array(Array.from({length: 100}, (_, i) => i));
store.set(ROOT + 'pdf/Key2020Abc.pdf', new Response(PDF, {headers: {'Content-Type': 'application/pdf',
  'Content-Length': '100', 'X-Pythia-Version': 'v1'}}));
store.set(ROOT, new Response('<!DOCTYPE html><html lang="en"><body>copy</body></html>',
  {headers: {'Content-Type': 'text/html; charset=utf-8', 'X-Pythia-Synced': '1700000000000'}}));
store.set(ROOT + 'graph.json', new Response('{"papers":{}}', {headers: {'Content-Type': 'application/json'}}));

function req(path, {method = 'GET', mode = 'cors', cache = 'default', range} = {}) {
  const headers = new Headers(range ? {Range: range} : {});
  return {url: new URL(path, ROOT).href, method, mode, cache, headers};
}
async function dispatch(r) {
  let answer = null;
  listeners.fetch({request: r, respondWith: (p) => { answer = p; }});
  return answer && await answer;
}
const down = () => Promise.reject(new TypeError('Failed to fetch'));
const status = (s) => () => Promise.resolve(new Response('server ' + s, {status: s}));
const hang = () => new Promise(() => {});

(async () => {
  net = down;
  // PDFs: from the copy, whole or in ranges
  let r = await dispatch(req('pdf/Key2020Abc.pdf'));
  assert.equal(r.status, 200);
  assert.equal(r.headers.get('Accept-Ranges'), 'bytes');
  assert.equal((await r.arrayBuffer()).byteLength, 100);
  r = await dispatch(req('pdf/Key2020Abc.pdf', {range: 'bytes=10-19'}));
  assert.equal(r.status, 206);
  assert.equal(r.headers.get('Content-Range'), 'bytes 10-19/100');
  assert.equal(r.headers.get('Content-Length'), '10');
  assert.deepEqual([...new Uint8Array(await r.arrayBuffer())], [10,11,12,13,14,15,16,17,18,19]);
  r = await dispatch(req('pdf/Key2020Abc.pdf', {range: 'bytes=90-'}));
  assert.equal(r.headers.get('Content-Range'), 'bytes 90-99/100');
  r = await dispatch(req('pdf/Key2020Abc.pdf', {range: 'bytes=-5'}));
  assert.equal(r.headers.get('Content-Range'), 'bytes 95-99/100');
  assert.deepEqual([...new Uint8Array(await r.arrayBuffer())], [95,96,97,98,99]);
  r = await dispatch(req('pdf/Key2020Abc.pdf', {range: 'bytes=50-500'}));
  assert.equal(r.headers.get('Content-Range'), 'bytes 50-99/100');
  r = await dispatch(req('pdf/Key2020Abc.pdf', {range: 'bytes=100-'}));
  assert.equal(r.status, 416);
  assert.equal(r.headers.get('Content-Range'), 'bytes */100');
  r = await dispatch(req('pdf/Key2020Abc.pdf', {range: 'bytes=-0'}));
  assert.equal(r.status, 416);
  r = await dispatch(req('pdf/Key2020Abc.pdf', {range: 'bytes=0-1,5-6'}));   // multi-range: whole body
  assert.equal(r.status, 200);
  assert.equal(fetched.length, 0, 'a cached PDF never touches the server');
  // a PDF not copied yet goes to the server
  net = () => Promise.resolve(new Response('fresh', {status: 200}));
  r = await dispatch(req('pdf/Other2021Xyz.pdf'));
  assert.equal(await r.text(), 'fresh');

  // the page: server first; the marked copy when it is unreachable, 502s through a proxy, or hangs
  net = () => Promise.resolve(new Response('<html>live</html>', {status: 200}));
  r = await dispatch(req('?view=app', {mode: 'navigate'}));
  assert.equal(await r.text(), '<html>live</html>');
  for (const how of [down, status(502), status(503), hang]) {
    net = how;
    r = await dispatch(req('?view=app', {mode: 'navigate'}));
    const text = await r.text();
    assert.match(text, /<html data-offline="1700000000000" lang="en">/);
    assert.equal(r.status, 200);
  }
  net = status(500);                       // a BuildError is the server talking: pass it on
  r = await dispatch(req('', {mode: 'navigate'}));
  assert.equal(r.status, 500);
  net = down;
  r = await dispatch(req('index.html', {mode: 'navigate'}));
  assert.match(await r.text(), /data-offline/);
  // a view's graph.json is the one cached graph
  r = await dispatch(req('views/claim-map/graph.json'));
  assert.equal(await r.text(), '{"papers":{}}');
  // a live-only page explains itself instead of a browser error
  r = await dispatch(req('preview.html?key=x', {mode: 'navigate'}));
  assert.equal(r.status, 503);
  assert.match(await r.text(), /needs the Pythia server/);

  // left alone entirely: the sync's own fetches, writes, server-only reads, other origins
  assert.equal(await dispatch(req('pdf/Key2020Abc.pdf', {cache: 'no-store'})), null);
  assert.equal(await dispatch(req('offline.json', {cache: 'no-store'})), null);
  assert.equal(await dispatch(req('active', {method: 'POST'})), null);
  assert.equal(await dispatch(req('page/Key2020Abc/0.jpg?w=640')), null);
  assert.equal(await dispatch(req('https://elsewhere.example/pdf/Key2020Abc.pdf')), null);
})().catch((e) => { console.error(e); process.exitCode = 1; });
"""


def test_offline_worker_routes_and_ranges():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed to execute the service worker")
    script = HARNESS.replace("\n{SW}\n", "\n" + SW.read_text() + "\n")
    result = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
