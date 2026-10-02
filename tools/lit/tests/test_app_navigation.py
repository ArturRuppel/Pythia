"""Execute the app's navigation against a small browser-history adapter."""
import shutil
import subprocess
from pathlib import Path

import pytest

APP = Path(__file__).parents[1] / "litgraph/viewer/js/19-app.js"


@pytest.mark.parametrize("scenario", [
    """
    push({t:'paper', key:'Source', focus:'c1'});
    push({t:'slice', pk:'Source', id:'m1'});
    for (let i = 0; i < 20; i++) {
      push({t:'slice', pk:'Source', id:'c1'});
      assert.equal(S.stacks.library.length, 1);
      assert.equal(S.future.library.length, 1);
      push({t:'slice', pk:'Source', id:'m1'});
      assert.equal(S.stacks.library.length, 2);
      assert.equal(S.future.library.length, 0);
    }
    const count = entries.length;
    push({t:'slice', pk:'Source', id:'m1'});
    assert.equal(entries.length, count);
    push({t:'ledger', node:{t:'slice', pk:'Source', id:'m1'}});
    assert.equal(S.stacks.library.length, 3);
    """,
    """
    push({t:'paper', key:'Review'});
    push({t:'slice', pk:'Review', id:'b1'});
    push({t:'paper', key:'Source', focus:'c2'});
    travel(1);
    assert.equal(S.future.library.length, 2);
    travel(3);
    assert.equal(S.stacks.library[2].focus, 'c2');
    travel(1);
    push({t:'paper', key:'OtherSource'});
    assert.equal(S.future.library.length, 0);
    assert.equal(S.stacks.library[1].key, 'OtherSource');
    """,
    """
    push({t:'paper', key:'Review'});
    const prior = structuredClone(entries.at(-1));
    push({t:'paper', key:'Source', focus:'c2'});
    const next = structuredClone(entries.at(-1));
    events.popstate({state:prior});
    assert.equal(S.stacks.library.length, 1);
    assert.equal(S.future.library[0].focus, 'c2');
    events.popstate({state:next});
    assert.equal(S.stacks.library[1].focus, 'c2');
    assert.equal(prior.pythia.stacks.library.length, 1);
    """,
    """
    push({t:'paper', key:'Review'});
    push({t:'paper', key:'Source'});
    travel(1);
    tabTo('topics');
    push({t:'broad', slug:'rigidity'});
    tabTo('library');
    assert.equal(S.future.library[0].key, 'Source');
    travel(2);
    assert.equal(S.stacks.library[1].key, 'Source');
    tabTo('library');
    assert.equal(S.stacks.library.length, 0);
    assert.equal(S.future.library.length, 0);
    """,
])
def test_evidence_navigation(scenario):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed to execute viewer navigation")
    source = APP.read_text()
    navigation = source[source.index("  function saveNav("):source.index("  function remember(")]
    harness = r"""
    const assert = require('node:assert/strict');
    const S = {tab:'library', stacks:{library:[], topics:[], reading:[], search:[]},
      future:{library:[], topics:[], reading:[], search:[]}, q:'', pos:{}};
    const entries = [], events = {};
    const history = {
      pushState: s => entries.push(structuredClone(s)),
      replaceState: s => {entries[entries.length-1] = structuredClone(s);}
    };
    const addEventListener = (name, fn) => events[name] = fn;
    const keepPos = () => {}, render = () => {}, remember = () => {};
    const posKey = () => S.tab + '/' + S.stacks[S.tab].length;
    const document = {body:{classList:{contains:() => true}}};
    """
    result = subprocess.run([node, "-e", harness + navigation + scenario],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("scenario", [
    """
    const f = claimFamilies(['broad','narrow','support','alone'], [
      {parent:'broad', child:'narrow', label:'Narrower claim'},
      {parent:'narrow', child:'support', label:'Supporting claim'},
      {parent:'broad', child:'outside'}]);
    assert.deepEqual(f.roots, ['broad','alone']);
    assert.equal(f.children.get('broad')[0].child, 'narrow');
    assert.equal(f.children.get('narrow')[0].label, 'Supporting claim');
    """,
    """
    const f = claimFamilies(['a','b','shared'], [
      {parent:'a',child:'shared'}, {parent:'b',child:'shared'},
      {parent:'a',child:'shared'}]);
    assert.deepEqual(f.roots, ['a','b']);
    assert.equal(f.children.get('a').length, 1);
    assert.equal(f.children.get('b').length, 0);
    assert.equal(f.refs.get('b')[0].child, 'shared');
    """,
    """
    const f = claimFamilies(['a','b','c'], [
      {parent:'a',child:'b'}, {parent:'b',child:'c'},
      {parent:'c',child:'a'}, {parent:'a',child:'a'}]);
    assert.deepEqual(f.roots, ['a']);
    const visited = [];
    function walk(id) {visited.push(id); f.children.get(id).forEach(e => walk(e.child));}
    f.roots.forEach(walk);
    assert.deepEqual(visited, ['a','b','c']);
    assert.equal(f.refs.get('c')[0].child, 'a');
    """,
])
def test_claim_families(scenario):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed to execute viewer structure")
    source = APP.read_text()
    function = source[source.index("  function claimFamilies("):source.index("  function claimFamilyView(")]
    result = subprocess.run([node, "-e", "const assert = require('node:assert/strict');" + function + scenario],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
