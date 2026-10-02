"""Library ordering and the provenance of its derived update timestamp."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from litgraph.graph import load_repo
from litgraph.build import _paper_json


def test_curation_updated_is_file_mtime(tmp_path):
    (tmp_path / "curated").mkdir()
    record = tmp_path / "curated" / "Example2020Test.yaml"
    record.write_text("title: Example\nyear: 2020\npass: 2\n")
    os.utime(record, (1700000000, 1700000000))
    (tmp_path / "stubs.yaml").write_text("Stub2021Test: {title: Stub, year: 2021}\n")
    papers, _ = load_repo(tmp_path)
    assert _paper_json(papers[record.stem], [])["curation_updated"] == 1700000000
    assert papers["Stub2021Test"].curation_updated is None


def test_sort_modes_and_missing_values():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is needed to execute library sorting")
    source = (Path(__file__).parents[1] / "litgraph/viewer/js/19-app.js").read_text()
    comparator = source[source.index("  function compareLibrary("):source.index("  function libRows(")]
    checks = r"""
    const assert = require('node:assert/strict');
    const rows = [
      {k:'B',title:'zebra',year:2024,pass:1,updated:100},
      {k:'A',title:'Alpha',year:2020,pass:4,updated:200},
      {k:'C',title:'beta',year:0,pass:null,updated:0},
      {k:'D',title:'delta',year:2024,pass:0,updated:0}
    ];
    const expected = {title:'ACDB','title-desc':'BDCA',key:'ABCD',
      new:'BDAC',old:'ABDC',updated:'ABCD','updated-old':'BACD',
      pass:'ABDC','pass-low':'DBAC'};
    for (const [sort, want] of Object.entries(expected)) {
      assert.equal([...rows].sort((a,b) => compareLibrary(a,b,sort)).map(r=>r.k).join(''), want, sort);
    }
    """
    result = subprocess.run([node, "-e", comparator + checks], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
