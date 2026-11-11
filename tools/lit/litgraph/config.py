"""Deployment-local config (config.toml at the data root): paths + polite-pool mailto."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    root: Path  # holds curated/, stubs.yaml
    pdf_dir: Path | None  # external PDF dir (informational; rename happens beside the PDF)
    mailto: str  # OpenAlex/Crossref polite pool


def load_config(root: str | Path) -> Config:
    """Load `<root>/config.toml` if present; otherwise sensible defaults."""
    root = Path(root)
    cfg_path = root / "config.toml"
    data: dict = {}
    if cfg_path.exists():
        data = tomllib.loads(cfg_path.read_text())
    pdf_dir = data.get("pdf_dir")
    # A `[curation]` table (the retired reading list, `[curation] active`) may still sit in an
    # older config.toml. It is ignored, never an error: the desk replaced it, derived from each
    # paper's `pass` and `validated` (SCHEMA §4), so there is no list to keep here any more.
    return Config(
        root=Path(data.get("root", root)),
        pdf_dir=Path(pdf_dir) if pdf_dir else None,
        mailto=data.get("mailto", ""),
    )

