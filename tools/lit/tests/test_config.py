# tests/test_config.py
"""config.toml loading — and the retired reading list (`[curation] active`) staying retired."""
import dataclasses

import litgraph.config as config
from litgraph.config import load_config


def test_defaults_without_a_config_file(tmp_path):
    cfg = load_config(tmp_path)
    assert cfg.root == tmp_path and cfg.pdf_dir is None and cfg.mailto == ""


def test_a_leftover_curation_table_loads_and_is_ignored(tmp_path):
    """A data repo still carrying the reading list's `[curation] active` must load without error:
    the desk replaced it (SCHEMA §4), so the table is dead weight until someone deletes it."""
    (tmp_path / "config.toml").write_text(
        '# my library config\n'
        'mailto = "me@example.org"  # polite pool\n'
        'pdf_dir = "/data/pdfs"\n'
        '\n'
        '[curation]\n'
        'active = ["Chen2021Sys", "Kumar2020Net"]\n'
    )
    cfg = load_config(tmp_path)
    assert cfg.mailto == "me@example.org"
    assert str(cfg.pdf_dir) == "/data/pdfs"
    assert "active" not in {f.name for f in dataclasses.fields(cfg)}


def test_the_reading_list_writer_is_gone():
    assert not hasattr(config, "set_active")
