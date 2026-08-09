"""Internal IT Help Desk — past case search portal (PoC)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.services import ai as ai_service
from app.services import cases as case_service

load_dotenv()

APP_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))
templates.env.filters["urlencode"] = lambda v: quote(str(v), safe="")

app = FastAPI(
    title="IT Help Desk Case Search (Internal PoC)",
    description="社内ポータル向け: 過去問い合わせ事例のあいまい/意味検索 + 起票フォーム",
    docs_url=None,
    redoc_url=None,
)
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")


def _base_ctx(request: Request) -> dict:
    return {
        "request": request,
        "ai_ready": ai_service.ai_available(),
        "contact": case_service.get_contact(),
        "categories": case_service.get_categories(),
        "meta": case_service.get_meta(),
        "access_mode": "internal_only",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    q: str = Query(""),
    category: str = Query("all"),
    sort: str = Query("relevance"),
    semantic: int = Query(0),
):
    cases = case_service.search_cases(q=q, category=category, sort=sort)
    semantic_result = None
    if semantic and q.strip():
        semantic_result = ai_service.semantic_search(q, limit=5)
    # counts per category for tabs
    all_for_counts = case_service.search_cases(q=q, category="all", sort=sort)
    counts = {"all": len(all_for_counts)}
    for c in case_service.get_categories():
        if c["id"] == "all":
            continue
        counts[c["id"]] = sum(1 for x in all_for_counts if x.get("category") == c["id"])

    return templates.TemplateResponse(
        request,
        "home.html",
        {
            **_base_ctx(request),
            "cases": cases,
            "q": q,
            "category": category or "all",
            "sort": sort or "relevance",
            "counts": counts,
            "semantic_result": semantic_result,
            "stats": {
                "total": case_service.stats()["total"],
                "shown": len(cases),
            },
        },
    )


@app.get("/cases/{case_id}", response_class=HTMLResponse)
async def case_detail(request: Request, case_id: str):
    case = case_service.get_case(case_id)
    if not case:
        return templates.TemplateResponse(
            request,
            "not_found.html",
            {**_base_ctx(request), "case_id": case_id},
            status_code=404,
        )
    case = dict(case)
    case["category_label"] = case_service.category_label(case.get("category", ""))
    case["priority_label"] = case_service.PRIORITY_LABEL.get(case.get("priority", ""), "")
    related = [
        c
        for c in case_service.search_cases(q="", category=case["category"], sort="updated")
        if c["id"] != case_id
    ][:3]
    return templates.TemplateResponse(
        request,
        "detail.html",
        {
            **_base_ctx(request),
            "case": case,
            "related": related,
        },
    )


@app.get("/inquiry", response_class=HTMLResponse)
async def inquiry_form(request: Request, ref: str = Query("")):
    return templates.TemplateResponse(
        request,
        "inquiry.html",
        {
            **_base_ctx(request),
            "ref": ref,
            "priorities": [
                ("high", "高（業務停止・多数影響）"),
                ("medium", "中（回避策あり・期限あり）"),
                ("low", "低（質問・改善要望）"),
            ],
            "devices": [
                ("pc", "社給PC"),
                ("mac", "Mac"),
                ("mobile", "スマホ/タブレット"),
                ("printer", "プリンタ/複合機"),
                ("other", "その他・不明"),
            ],
            "submitted": False,
        },
    )


@app.post("/inquiry", response_class=HTMLResponse)
async def inquiry_submit(
    request: Request,
    name: str = Form(""),
    dept: str = Form(""),
    email: str = Form(""),
    category: str = Form("other"),
    priority: str = Form("medium"),
    device: str = Form("pc"),
    device_detail: str = Form(""),
    subject: str = Form(""),
    body: str = Form(""),
    ref_case: str = Form(""),
):
    ticket_id = f"INQ-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    payload = {
        "ticket_id": ticket_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "name": name.strip(),
        "dept": dept.strip(),
        "email": email.strip(),
        "category": category,
        "priority": priority,
        "device": device,
        "device_detail": device_detail.strip(),
        "subject": subject.strip(),
        "body": body.strip(),
        "ref_case": ref_case.strip(),
        "note": "PoC: ローカル JSON に保存のみ。外部チケットへは連携しません。",
    }
    case_service.save_inquiry(payload)
    return templates.TemplateResponse(
        request,
        "inquiry.html",
        {
            **_base_ctx(request),
            "ref": ref_case,
            "priorities": [
                ("high", "高（業務停止・多数影響）"),
                ("medium", "中（回避策あり・期限あり）"),
                ("low", "低（質問・改善要望）"),
            ],
            "devices": [
                ("pc", "社給PC"),
                ("mac", "Mac"),
                ("mobile", "スマホ/タブレット"),
                ("printer", "プリンタ/複合機"),
                ("other", "その他・不明"),
            ],
            "submitted": True,
            "ticket": payload,
        },
    )


@app.post("/search/semantic")
async def search_semantic_redirect(q: str = Form("")):
    return RedirectResponse(
        url=f"/?q={quote(q)}&semantic=1",
        status_code=303,
    )
