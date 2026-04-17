"""
utils/hsk_vocab.py
------------------
Loads HSK1–HSK10 vocabulary from a local JSON file.

The UI practice selector expects this data shape:
{
  "hsk1":  [ { "character": "...", "pinyin": "...", "meaning": "...", "tones": [..] }, ... ],
  ...
  "hsk10": [ ... ]
}

If the file is missing or a level is empty, callers can fall back to the
existing beginner/intermediate/advanced pools in utils/pinyin_utils.py.
"""

from __future__ import annotations

import json
from pathlib import Path


_CACHE: dict | None = None


def _data_path() -> Path:
    from utils.config import resource_path
    return Path(resource_path("res/data/hsk_vocab.json"))


def load_hsk_data() -> dict:
    global _CACHE
    if _CACHE is not None:
        return _CACHE

    path = _data_path()
    if not path.exists():
        _CACHE = {}
        return _CACHE

    try:
        _CACHE = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        _CACHE = {}
    return _CACHE


def get_hsk_vocabulary(level: int) -> list[dict]:
    """
    Returns vocabulary list for HSK level 1..10.
    """
    level = max(1, min(10, int(level)))
    data = load_hsk_data()
    items = data.get(f"hsk{level}", [])
    return list(items) if isinstance(items, list) else []

