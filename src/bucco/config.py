"""Paths and settings shared by the extract code and the command-line tool."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

# dbt reads the same variable, so both always point at the same data folder.
DATA_DIR = Path(os.environ.get("BUCCO_DATA_DIR", REPO_ROOT / "data")).resolve()
CACHE_DIR = DATA_DIR / "cache"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
MANUAL_DIR = DATA_DIR / "manual"
MANIFEST_PATH = DATA_DIR / "manifest.jsonl"
DUCKDB_PATH = DATA_DIR / "bucco.duckdb"

REPORTS_DIR = REPO_ROOT / "reports"
TRANSFORM_DIR = REPO_ROOT / "transform"
TEAMS_SEED = TRANSFORM_DIR / "seeds" / "teams.csv"
SOURCES_PATH = REPO_ROOT / "config" / "sources.yml"


def load_sources() -> dict:
    """Read config/sources.yml."""
    with open(SOURCES_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def setting(name: str):
    """Look up one value from the `settings` block of config/sources.yml."""
    return load_sources()["settings"][name]
