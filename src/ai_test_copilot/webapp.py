"""FastAPI Web 服务层。

在 CLI 的业务封装(Copilot)之上暴露 HTTP 接口和一个简单网页，
让浏览器可以直接调用。可选的访问密码用于保护后面的 API key 不被滥用。
"""

from __future__ import annotations

import os
from importlib.resources import files

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from . import __version__
from .client import Copilot, CopilotError
from .feishu import FeishuError, fetch_doc_text

# 若设置了 APP_PASSWORD，则所有 /api 调用都需带上正确密码（保护按量计费的 API key）。
APP_PASSWORD = os.environ.get("APP_PASSWORD") or None

app = FastAPI(title="ai-test-copilot", version=__version__)


class TextIn(BaseModel):
    text: str


class UrlIn(BaseModel):
    url: str


def _check_password(provided: str | None) -> None:
    if APP_PASSWORD and provided != APP_PASSWORD:
        raise HTTPException(status_code=401, detail="访问密码错误")


def _require_text(text: str) -> str:
    if not text or not text.strip():
        raise HTTPException(status_code=400, detail="输入为空")
    return text


@app.get("/healthz")
def healthz() -> dict:
    return {
        "ok": True,
        "version": __version__,
        "auth_required": bool(APP_PASSWORD),
        "feishu_configured": bool(os.environ.get("FEISHU_APP_ID") and os.environ.get("FEISHU_APP_SECRET")),
    }


@app.post("/api/feishu/fetch")
def api_feishu_fetch(body: UrlIn, x_app_password: str | None = Header(default=None)) -> dict:
    """拉取飞书文档正文，返回纯文本（前端再填入输入框走生成/分析）。"""
    _check_password(x_app_password)
    if not body.url.strip():
        raise HTTPException(status_code=400, detail="链接为空")
    try:
        text = fetch_doc_text(body.url.strip())
    except FeishuError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"text": text, "chars": len(text)}


@app.post("/api/generate")
def api_generate(body: TextIn, x_app_password: str | None = Header(default=None)) -> dict:
    _check_password(x_app_password)
    text = _require_text(body.text)
    try:
        return Copilot().generate_tests(text).model_dump()
    except CopilotError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/analyze")
def api_analyze(body: TextIn, x_app_password: str | None = Header(default=None)) -> dict:
    _check_password(x_app_password)
    text = _require_text(body.text)
    try:
        return Copilot().analyze_failure(text).model_dump()
    except CopilotError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return files("ai_test_copilot").joinpath("static/index.html").read_text(encoding="utf-8")
