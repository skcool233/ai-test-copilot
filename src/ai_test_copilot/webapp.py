"""FastAPI Web 服务层。

在 CLI 的业务封装(Copilot)之上暴露 HTTP 接口和一个简单网页，
让浏览器可以直接调用。可选的访问密码用于保护后面的 API key 不被滥用。
"""

from __future__ import annotations

import os
import re
import secrets
from importlib.resources import files

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from . import __version__
from . import feishu, history
from .client import Copilot, CopilotError
from .feishu import FeishuError, create_doc_from_plan, fetch_doc_text
from .models import TestPlan
from .pytest_export import plan_to_pytest, slug_filename

# OAuth state 校验（防 CSRF）。单用户个人工具，进程内存即可。
_oauth_states: set[str] = set()

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
    configured = bool(os.environ.get("FEISHU_APP_ID") and os.environ.get("FEISHU_APP_SECRET"))
    return {
        "ok": True,
        "version": __version__,
        "auth_required": bool(APP_PASSWORD),
        "feishu_configured": configured,
        "feishu_authorized": configured and feishu.is_authorized(),
    }


@app.get("/feishu/login")
def feishu_login() -> RedirectResponse:
    """跳转到飞书授权页（用户授权一次，之后自动续期）。"""
    try:
        state = secrets.token_urlsafe(16)
        _oauth_states.add(state)
        return RedirectResponse(feishu.authorize_url(state))
    except FeishuError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/feishu/callback", response_class=HTMLResponse)
def feishu_callback(code: str | None = None, state: str | None = None) -> str:
    """飞书授权回调：用 code 换取并保存用户令牌。"""
    if not code:
        return _result_page("授权失败", "未拿到授权码（code）", ok=False)
    if not state or state not in _oauth_states:
        return _result_page("授权失败", "state 校验未通过，请重新发起登录", ok=False)
    _oauth_states.discard(state)
    try:
        feishu.exchange_code(code)
    except FeishuError as exc:
        return _result_page("授权失败", str(exc), ok=False)
    return _result_page("✅ 飞书授权成功", "现在可以关闭本页，回到工具粘贴文档链接拉取。", ok=True)


def _result_page(title: str, msg: str, *, ok: bool) -> str:
    color = "#3fb950" if ok else "#f85149"
    return (
        f"<!doctype html><meta charset=utf-8><title>{title}</title>"
        "<body style='background:#0e1016;color:#e8eaf0;font-family:-apple-system,sans-serif;"
        "display:grid;place-items:center;height:100vh;margin:0'>"
        f"<div style='text-align:center'><h2 style='color:{color}'>{title}</h2>"
        f"<p style='color:#9aa3b5'>{msg}</p></div></body>"
    )


@app.post("/api/feishu/fetch")
def api_feishu_fetch(body: UrlIn, x_app_password: str | None = Header(default=None)) -> dict:
    """拉取飞书文档/多维表格正文，返回纯文本。支持多链接（空白/换行分隔）批量。"""
    _check_password(x_app_password)
    links = [u for u in re.split(r"\s+", body.url.strip()) if u]
    if not links:
        raise HTTPException(status_code=400, detail="链接为空")
    parts, errors = [], []
    for u in links:
        try:
            t = fetch_doc_text(u)
            parts.append(t if len(links) == 1 else f"===== {u} =====\n\n{t}")
        except FeishuError as exc:
            errors.append(f"{u} → {exc}")
    if not parts:
        raise HTTPException(status_code=400, detail="；".join(errors) or "拉取失败")
    text = "\n\n".join(parts)
    return {"text": text, "chars": len(text), "count": len(parts), "errors": errors}


@app.post("/api/to-pytest")
def api_to_pytest(body: dict, x_app_password: str | None = Header(default=None)) -> dict:
    """把生成的测试计划 JSON 转成 pytest 骨架代码。"""
    _check_password(x_app_password)
    try:
        plan = TestPlan.model_validate(body)
    except Exception as exc:  # noqa: BLE001 - 统一回 400
        raise HTTPException(status_code=400, detail=f"测试计划格式不对：{exc}") from exc
    return {"code": plan_to_pytest(plan), "filename": slug_filename(plan.feature)}


@app.post("/api/feishu/export")
def api_feishu_export(body: dict, x_app_password: str | None = Header(default=None)) -> dict:
    """把测试计划新建成一篇飞书文档，返回文档链接。"""
    _check_password(x_app_password)
    try:
        plan = TestPlan.model_validate(body)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"测试计划格式不对：{exc}") from exc
    try:
        url = create_doc_from_plan(plan)
    except FeishuError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"url": url}


@app.post("/api/generate")
def api_generate(body: TextIn, x_app_password: str | None = Header(default=None)) -> dict:
    _check_password(x_app_password)
    text = _require_text(body.text)
    try:
        plan = Copilot().generate_tests(text)
    except CopilotError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    result = plan.model_dump()
    history.add("generate", plan.feature, text, result)
    return result


@app.post("/api/analyze")
def api_analyze(body: TextIn, x_app_password: str | None = Header(default=None)) -> dict:
    _check_password(x_app_password)
    text = _require_text(body.text)
    try:
        analysis = Copilot().analyze_failure(text)
    except CopilotError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    result = analysis.model_dump()
    history.add("analyze", analysis.summary, text, result)
    return result


@app.get("/api/history")
def api_history(x_app_password: str | None = Header(default=None)) -> list[dict]:
    _check_password(x_app_password)
    return history.list_meta()


@app.get("/api/history/{item_id}")
def api_history_item(item_id: str, x_app_password: str | None = Header(default=None)) -> dict:
    _check_password(x_app_password)
    item = history.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="记录不存在")
    return item


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return files("ai_test_copilot").joinpath("static/index.html").read_text(encoding="utf-8")
