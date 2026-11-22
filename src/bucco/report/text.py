"""The report's written content lives in config/report_text.yml so it can be edited (by you or
an agent) without touching code. This module loads it, checks it, and fills in placeholders."""

from __future__ import annotations

import re
from html import escape
from string import Formatter

import yaml

from bucco.config import REPO_ROOT

TEXT_PATH = REPO_ROOT / "config" / "report_text.yml"

# Placeholders each entry may use. A key missing here may not use any.
ALLOWED: dict[str, set[str]] = {
    "title": {"season"},
    "date_line": {"as_of", "opening_day_note"},
    "hero_explanation": {"low", "high"},
    "fact_beat_last": {"last_wins", "last_season"},
    "what_changed_first": {"season"},
    "what_changed_moved": {"before", "now", "delta", "before_date"},
    "what_changed_model": {"before_model"},
    "trust_intro": {"model_label", "first_season", "last_season"},
    "unknowns": {"as_of"},
    "footer": {"today", "commit_note"},
}
REQUIRED_STRINGS = [
    "kicker", "title", "date_line", "hero_explanation", "fact_above_500", "fact_beat_last",
    "what_changed_heading", "what_changed_first", "what_changed_moved", "what_changed_model",
    "what_changed_unchanged", "timeline_heading", "timeline_intro", "league_heading",
    "league_intro", "trust_heading", "trust_intro", "table_note", "past_heading", "past_intro",
    "unknowns_heading", "footer",
]
REQUIRED_BADGES = ["record", "preliminary", "late"]


class ReportTextError(ValueError):
    """The text file is missing an entry or uses a placeholder it should not."""


def _placeholders(template: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(template) if name}


def _check(key: str, template: object) -> None:
    if not isinstance(template, str) or not template.strip():
        raise ReportTextError(f"{key}: must be non-empty text")
    unknown = _placeholders(template) - ALLOWED.get(key, set())
    if unknown:
        allowed = sorted(ALLOWED.get(key, set())) or "none"
        raise ReportTextError(f"{key}: unknown placeholder(s) {sorted(unknown)}; allowed: {allowed}")


def load_text(path=TEXT_PATH) -> dict:
    """Read and validate the text file."""
    with open(path, encoding="utf-8") as f:
        text = yaml.safe_load(f) or {}
    for key in REQUIRED_STRINGS:
        if key not in text:
            raise ReportTextError(f"{key}: missing from {path.name}")
        _check(key, text[key])
    for key in REQUIRED_BADGES:
        _check(f"badges.{key}", (text.get("badges") or {}).get(key))
    unknowns = text.get("unknowns")
    if not isinstance(unknowns, list) or not unknowns:
        raise ReportTextError("unknowns: must be a non-empty list")
    for i, item in enumerate(unknowns):
        _check("unknowns", item)
    if not isinstance(text.get("model_labels"), dict):
        raise ReportTextError("model_labels: must be a mapping of model name to label")
    return text


def fill(template: str, **values: str) -> str:
    """Insert values, escape for HTML, and turn **bold** into <b>."""
    filled = template.format(**{k: str(v) for k, v in values.items()})
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escape(filled))
