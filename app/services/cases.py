"""Load and search help-desk past cases (dummy data)."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "data" / "cases.json"
INQUIRIES_PATH = ROOT / "data" / "inquiries.json"

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}
PRIORITY_LABEL = {"high": "高", "medium": "中", "low": "低"}


@lru_cache(maxsize=1)
def _raw() -> dict[str, Any]:
    with DATA_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def reload() -> None:
    _raw.cache_clear()


def get_contact() -> dict[str, Any]:
    return dict(_raw()["contact"])


def get_categories() -> list[dict[str, str]]:
    return list(_raw()["categories"])


def get_meta() -> dict[str, Any]:
    return dict(_raw()["meta"])


def all_cases() -> list[dict[str, Any]]:
    return list(_raw()["cases"])


def category_label(category_id: str) -> str:
    for c in get_categories():
        if c["id"] == category_id:
            return c["label"]
    return category_id


def get_case(case_id: str) -> dict[str, Any] | None:
    for case in all_cases():
        if case["id"] == case_id:
            return dict(case)
    return None


def _normalize(text: str) -> str:
    t = text.casefold()
    t = t.replace("ｗｉ－ｆｉ", "wifi").replace("wi-fi", "wifi").replace("wi‑fi", "wifi")
    t = t.replace("　", " ")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _tokens(query: str) -> list[str]:
    q = _normalize(query)
    if not q:
        return []
    # split on spaces and common punctuation; keep short Japanese chunks as whole
    parts = re.split(r"[\s,、。・/／|]+", q)
    return [p for p in parts if p]


def _haystack(case: dict[str, Any]) -> str:
    parts = [
        case.get("id", ""),
        case.get("title", ""),
        case.get("symptom", ""),
        case.get("environment", ""),
        case.get("resolution_summary", ""),
        " ".join(case.get("keywords") or []),
        " ".join(case.get("related_tags") or []),
        " ".join(case.get("steps") or []),
        " ".join(case.get("if_unresolved") or []),
        category_label(case.get("category", "")),
    ]
    return _normalize(" ".join(parts))


def _score_case(case: dict[str, Any], tokens: list[str], raw_q: str) -> float:
    if not tokens and not raw_q:
        return 1.0
    hay = _haystack(case)
    score = 0.0
    full = _normalize(raw_q)
    if full and full in hay:
        score += 12.0
    title = _normalize(case.get("title", ""))
    symptom = _normalize(case.get("symptom", ""))
    keywords = [_normalize(k) for k in (case.get("keywords") or [])]

    for tok in tokens:
        if tok in title:
            score += 6.0
        if tok in symptom:
            score += 3.0
        for kw in keywords:
            if tok in kw or kw in tok:
                score += 5.0
                break
        if tok in hay:
            score += 1.5
        # light fuzzy: shared prefix length for tokens >= 2
        if len(tok) >= 2:
            for kw in keywords:
                if kw.startswith(tok) or tok.startswith(kw):
                    score += 2.0
                    break
    return score


def search_cases(
    q: str = "",
    category: str = "all",
    sort: str = "relevance",
) -> list[dict[str, Any]]:
    """Return cases filtered by category and fuzzy keyword score."""
    tokens = _tokens(q)
    results: list[dict[str, Any]] = []
    for case in all_cases():
        if category and category != "all" and case.get("category") != category:
            continue
        score = _score_case(case, tokens, q)
        if tokens and score <= 0:
            continue
        item = dict(case)
        item["_score"] = score
        item["category_label"] = category_label(case.get("category", ""))
        item["priority_label"] = PRIORITY_LABEL.get(case.get("priority", ""), case.get("priority", ""))
        results.append(item)

    if sort == "priority":
        results.sort(
            key=lambda c: (
                PRIORITY_ORDER.get(c.get("priority", "low"), 9),
                -c.get("_score", 0),
                c.get("id", ""),
            )
        )
    elif sort == "updated":
        results.sort(key=lambda c: (c.get("updated_at", ""), c.get("id", "")), reverse=True)
    elif sort == "title":
        results.sort(key=lambda c: c.get("title", ""))
    else:
        # relevance (default): score desc, then newer
        results.sort(
            key=lambda c: (-c.get("_score", 0), c.get("updated_at", ""), c.get("id", "")),
            reverse=False,
        )
        results.sort(key=lambda c: -c.get("_score", 0))

    return results


def stats() -> dict[str, Any]:
    cases = all_cases()
    by_cat: dict[str, int] = {}
    for c in cases:
        by_cat[c["category"]] = by_cat.get(c["category"], 0) + 1
    return {
        "total": len(cases),
        "high": sum(1 for c in cases if c.get("priority") == "high"),
        "by_category": by_cat,
    }


def save_inquiry(payload: dict[str, Any]) -> dict[str, Any]:
    """Append a structured inquiry (local JSON only — PoC)."""
    INQUIRIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    if INQUIRIES_PATH.is_file():
        with INQUIRIES_PATH.open(encoding="utf-8") as f:
            rows = json.load(f)
    else:
        rows = []
    if not isinstance(rows, list):
        rows = []
    rows.append(payload)
    with INQUIRIES_PATH.open("w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    return payload


def list_inquiries() -> list[dict[str, Any]]:
    if not INQUIRIES_PATH.is_file():
        return []
    with INQUIRIES_PATH.open(encoding="utf-8") as f:
        rows = json.load(f)
    return rows if isinstance(rows, list) else []
