"""Optional AI semantic search (xAI / offline keyword fallback)."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from dotenv import load_dotenv

from app.services import cases as case_service

load_dotenv()

MODEL = os.getenv("XAI_MODEL", "grok-4.5")


def ai_available() -> bool:
    return bool(os.getenv("XAI_API_KEY", "").strip())


def semantic_search(query: str, limit: int = 5) -> dict[str, Any]:
    """
    Rank past cases for a natural-language query.
    Uses xAI when XAI_API_KEY is set; otherwise offline keyword ranking.
    Dummy case text only is sent — no real personal data in this PoC.
    """
    q = (query or "").strip()
    if not q:
        return {
            "source": "none",
            "query": q,
            "matches": [],
            "note": "検索語を入力してください。",
        }

    catalog = case_service.all_cases()
    if ai_available():
        try:
            return _semantic_with_xai(q, catalog, limit)
        except Exception as exc:  # noqa: BLE001 — PoC fallback
            offline = _semantic_offline(q, limit)
            offline["source"] = "offline_fallback"
            offline["error"] = f"AI API error: {exc}"
            return offline
    return _semantic_offline(q, limit)


def _client():
    from openai import OpenAI

    return OpenAI(
        api_key=os.environ["XAI_API_KEY"],
        base_url="https://api.x.ai/v1",
    )


def _semantic_with_xai(query: str, catalog: list[dict[str, Any]], limit: int) -> dict[str, Any]:
    slim = [
        {
            "id": c["id"],
            "title": c["title"],
            "category": c["category"],
            "symptom": c["symptom"],
            "keywords": c.get("keywords", []),
        }
        for c in catalog
    ]
    system = (
        "あなたは社内ITヘルプデスク向けの事例検索アシスタントです。"
        "ユーザの自然文の困りごとに対し、与えられた過去事例一覧から"
        "類似度の高いものを最大"
        f"{limit}件、JSONのみで返してください。"
        "事例にない内容を捏造しないでください。"
        "社外秘の実データは含まれておらず、すべて架空のダミーです。"
    )
    user = f"""問い合わせ（自然文）:
{query}

過去事例一覧:
{json.dumps(slim, ensure_ascii=False, indent=2)}

次のJSONスキーマで返してください:
{{
  "matches": [
    {{"id": "HD-...", "reason": "類似する理由を1文（日本語）", "confidence": 0.0}}
  ],
  "hint": "オペレータ向けの短いヒント（日本語・任意）"
}}
confidence は 0〜1。
"""
    client = _client()
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=0.2,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    text = (resp.choices[0].message.content or "").strip()
    parsed = _parse_json(text)
    matches = _hydrate_matches(parsed.get("matches") or [], limit)
    return {
        "source": "xai",
        "query": query,
        "matches": matches,
        "hint": parsed.get("hint") or "",
        "note": "AI意味検索（ダミー事例のみ送信）",
    }


def _semantic_offline(query: str, limit: int) -> dict[str, Any]:
    ranked = case_service.search_cases(q=query, category="all", sort="relevance")
    matches = []
    for c in ranked[:limit]:
        matches.append(
            {
                "id": c["id"],
                "title": c["title"],
                "category": c["category"],
                "category_label": c.get("category_label"),
                "priority": c.get("priority"),
                "priority_label": c.get("priority_label"),
                "symptom": c.get("symptom"),
                "reason": "キーワード・表記ゆれを含むあいまい一致",
                "confidence": min(0.95, 0.35 + float(c.get("_score", 0)) / 20.0),
                "case": c,
            }
        )
    return {
        "source": "offline",
        "query": query,
        "matches": matches,
        "hint": "APIキー未設定のため、ローカルのあいまい検索で類似事例を並べています。",
        "note": "オフラインあいまい検索",
    }


def _hydrate_matches(raw_matches: list[Any], limit: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in raw_matches[:limit]:
        if not isinstance(m, dict):
            continue
        cid = str(m.get("id", ""))
        case = case_service.get_case(cid)
        if not case:
            continue
        out.append(
            {
                "id": cid,
                "title": case["title"],
                "category": case["category"],
                "category_label": case_service.category_label(case["category"]),
                "priority": case.get("priority"),
                "priority_label": case_service.PRIORITY_LABEL.get(case.get("priority", ""), ""),
                "symptom": case.get("symptom"),
                "reason": m.get("reason") or "",
                "confidence": float(m.get("confidence") or 0),
                "case": {
                    **case,
                    "category_label": case_service.category_label(case["category"]),
                    "priority_label": case_service.PRIORITY_LABEL.get(case.get("priority", ""), ""),
                },
            }
        )
    return out


def _parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            return json.loads(m.group(0))
        raise
