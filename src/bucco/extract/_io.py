"""Helpers shared by the extract modules: HTTP requests, Parquet writes, the run log."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import requests

from bucco.config import MANIFEST_PATH

log = logging.getLogger(__name__)

# A generic name on purpose. No personal details go out with requests.
USER_AGENT = "bucco-forecasting/0.1 (personal research project)"


def utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get(url: str, params: dict | None, retries: int, timeout: int,
         pause: float) -> requests.Response:
    """GET a URL. Retries with a growing wait, then gives up."""
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, params=params, timeout=timeout,
                                    headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
            time.sleep(pause)  # be polite to the API
            return response
        except requests.RequestException as error:
            last_error = error
            log.warning("GET %s failed (attempt %d of %d): %s", url, attempt, retries, error)
            time.sleep(2 ** attempt)
    raise RuntimeError(f"GET {url} failed after {retries} attempts") from last_error


def get_json(url: str, params: dict | None = None, retries: int = 3,
             timeout: int = 60, pause: float = 0.5) -> dict:
    """GET a URL and return the parsed JSON."""
    return _get(url, params, retries, timeout, pause).json()


def get_text(url: str, params: dict | None = None, retries: int = 3,
             timeout: int = 60, pause: float = 0.5) -> str:
    """GET a URL and return the body as text (for CSV downloads)."""
    response = _get(url, params, retries, timeout, pause)
    response.encoding = response.encoding or "utf-8"
    return response.text


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_parquet(df: pd.DataFrame, path: Path) -> Path:
    """Write a Parquet file. Goes through a temp file so a crash never leaves half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    df.to_parquet(tmp, index=False)
    tmp.replace(path)
    return path


def record_run(source: str, dataset: str, path: Path, rows: int, **extra) -> None:
    """Add one line to data/manifest.jsonl: what was saved, when, and its checksum."""
    entry = {
        "retrieved_at": utc_now_iso(),
        "source": source,
        "dataset": dataset,
        "path": str(path),
        "rows": rows,
        "sha256": sha256_file(path),
        **extra,
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
