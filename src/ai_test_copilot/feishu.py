"""飞书（Lark）文档读取 —— 基于「用户授权(OAuth)」。

用 user_access_token 代表登录用户读文档，因此能读「该用户有阅读权限」的任意文档
（包括别人知识库里、但分享给你的文档），无需把应用加进每个知识库。

流程：浏览器 /feishu/login → 飞书授权页 → /feishu/callback 拿 code → 换
access_token + refresh_token，存盘并自动续期。凭据/令牌均从环境变量与本地文件读，
不进代码与 git。
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

import httpx

FEISHU_BASE = os.environ.get("FEISHU_BASE", "https://open.feishu.cn")
FEISHU_ACCOUNTS_BASE = os.environ.get("FEISHU_ACCOUNTS_BASE", "https://accounts.feishu.cn")
# 需要 offline_access 才会下发 refresh_token（用于自动续期）。
SCOPE = os.environ.get(
    "FEISHU_SCOPE",
    "docx:document:readonly wiki:wiki:readonly bitable:app:readonly offline_access",
)
_BITABLE_MAX_RECORDS = 100
_TIMEOUT = 20.0


class FeishuError(RuntimeError):
    """对外暴露的飞书相关错误。"""


def _creds() -> tuple[str, str]:
    aid = os.environ.get("FEISHU_APP_ID")
    sec = os.environ.get("FEISHU_APP_SECRET")
    if not aid or not sec:
        raise FeishuError("未配置飞书应用凭据（FEISHU_APP_ID / FEISHU_APP_SECRET）")
    return aid, sec


def _redirect_uri() -> str:
    uri = os.environ.get("FEISHU_REDIRECT_URI")
    if not uri:
        raise FeishuError("未配置 FEISHU_REDIRECT_URI（须与飞书后台登记的重定向 URL 一致）")
    return uri


def _token_file() -> Path:
    p = os.environ.get("FEISHU_TOKEN_FILE") or str(
        Path.home() / ".ai-test-copilot" / "feishu_token.json"
    )
    return Path(p)


# ---------- token 存取 ----------

def _load() -> dict:
    f = _token_file()
    if not f.is_file():
        return {}
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(tok: dict) -> None:
    f = _token_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(tok), encoding="utf-8")
    try:
        os.chmod(f, 0o600)
    except OSError:
        pass


def is_authorized() -> bool:
    t = _load()
    # 有 refresh_token（未过期）或 access_token 即视为已授权。
    now = time.time()
    return bool(
        (t.get("refresh_token") and t.get("refresh_expires", 0) > now)
        or (t.get("access_token") and t.get("access_expires", 0) > now)
    )


# ---------- OAuth ----------

def authorize_url(state: str) -> str:
    aid, _ = _creds()
    return (
        f"{FEISHU_ACCOUNTS_BASE}/open-apis/authen/v1/authorize"
        f"?client_id={aid}&response_type=code"
        f"&redirect_uri={quote(_redirect_uri(), safe='')}"
        f"&scope={quote(SCOPE, safe='')}&state={quote(state)}"
    )


def _post_token(payload: dict) -> dict:
    try:
        r = httpx.post(
            f"{FEISHU_BASE}/open-apis/authen/v2/oauth/token",
            json=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=_TIMEOUT,
        )
        data = r.json()
    except httpx.HTTPError as exc:
        raise FeishuError(f"连接飞书失败：{exc}") from exc
    if data.get("code") not in (0, None) or "access_token" not in data:
        raise FeishuError(f"飞书授权失败：{data.get('error_description') or data.get('error') or data}")
    return data


def _store_token(data: dict) -> None:
    now = time.time()
    tok = _load()
    tok["access_token"] = data["access_token"]
    tok["access_expires"] = now + data.get("expires_in", 7200)
    if data.get("refresh_token"):
        tok["refresh_token"] = data["refresh_token"]
        tok["refresh_expires"] = now + data.get("refresh_token_expires_in", 30 * 86400)
    _save(tok)


def exchange_code(code: str) -> None:
    aid, sec = _creds()
    data = _post_token(
        {
            "grant_type": "authorization_code",
            "client_id": aid,
            "client_secret": sec,
            "code": code,
            "redirect_uri": _redirect_uri(),
        }
    )
    _store_token(data)


def _refresh() -> None:
    aid, sec = _creds()
    tok = _load()
    rt = tok.get("refresh_token")
    if not rt or tok.get("refresh_expires", 0) < time.time():
        raise FeishuError("飞书授权已过期，请重新点「登录飞书」")
    data = _post_token(
        {
            "grant_type": "refresh_token",
            "client_id": aid,
            "client_secret": sec,
            "refresh_token": rt,
        }
    )
    _store_token(data)


def _user_token() -> str:
    tok = _load()
    if not tok:
        raise FeishuError("尚未授权飞书，请先在页面点「登录飞书」")
    if tok.get("access_token") and tok.get("access_expires", 0) > time.time() + 60:
        return tok["access_token"]
    _refresh()
    return _load()["access_token"]


# ---------- 文档读取 ----------

def parse_url(url: str) -> tuple[str, str]:
    """从飞书链接解析出 (类型, token)，类型 ∈ {docx, wiki, docs, base}。"""
    m = re.search(r"/(docx|wiki|docs|base)/([A-Za-z0-9]+)", url)
    if not m:
        raise FeishuError("无法识别的飞书链接（需含 /docx/、/wiki/ 或 /base/）")
    return m.group(1), m.group(2)


def _flatten(value) -> str:
    """把多维表格的字段值压成可读字符串。"""
    if isinstance(value, list):
        return " ".join(_flatten(v) for v in value)
    if isinstance(value, dict):
        return str(value.get("text") or value.get("name") or json.dumps(value, ensure_ascii=False))
    return str(value)


def _fetch_bitable(url: str, app_token: str, token: str) -> str:
    """读取多维表格（Bitable）记录，转成文本。"""
    table_id = (parse_qs(urlparse(url).query).get("table") or [None])[0]
    if not table_id:
        tables = _api_get(f"/open-apis/bitable/v1/apps/{app_token}/tables", token, {"page_size": 1})
        items = tables.get("items") or []
        if not items:
            raise FeishuError("多维表格里没有数据表")
        table_id = items[0]["table_id"]

    recs = _api_get(
        f"/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records",
        token,
        {"page_size": _BITABLE_MAX_RECORDS},
    )
    items = recs.get("items") or []
    if not items:
        raise FeishuError("多维表格内容为空，或无读取权限")

    lines: list[str] = []
    field_lines = 0
    for i, rec in enumerate(items, 1):
        lines.append(f"# 记录 {i}")
        for key, val in (rec.get("fields") or {}).items():
            lines.append(f"{key}: {_flatten(val)}")
            field_lines += 1
        lines.append("")
    if field_lines == 0:
        raise FeishuError(
            f"读到 {len(items)} 条记录但字段值为空——可能是空表，"
            "或该多维表格开启了「高级权限」导致 API 读不到内容（需关闭高级权限或换一张表）"
        )
    return "\n".join(lines).strip()


def _api_get(path: str, token: str, params: dict | None = None) -> dict:
    try:
        r = httpx.get(
            f"{FEISHU_BASE}{path}",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=_TIMEOUT,
        )
        data = r.json()
    except httpx.HTTPError as exc:
        raise FeishuError(f"连接飞书失败：{exc}") from exc
    if data.get("code") != 0:
        msg = data.get("msg", "")
        if "permission" in str(msg).lower():
            msg += "（你的账号可能对该文档无阅读权限，或权限范围未开通）"
        raise FeishuError(f"飞书 API 错误：{msg}（code {data.get('code')}）")
    return data["data"]


def _resolve_wiki(node_token: str, token: str) -> str:
    data = _api_get("/open-apis/wiki/v2/spaces/get_node", token, {"token": node_token})
    node = data["node"]
    if node.get("obj_type") != "docx":
        raise FeishuError(f"暂不支持的知识库节点类型：{node.get('obj_type')}")
    return node["obj_token"]


def fetch_doc_text(url: str) -> str:
    """给定飞书文档链接，用当前登录用户的权限读取其纯文本正文。"""
    token = _user_token()
    doc_type, tok = parse_url(url)
    if doc_type == "base":
        return _fetch_bitable(url, tok, token)
    if doc_type == "wiki":
        document_id = _resolve_wiki(tok, token)
    elif doc_type == "docx":
        document_id = tok
    else:
        raise FeishuError("暂不支持旧版文档(/docs/)，请使用新版文档(/docx/)或知识库链接")

    data = _api_get(
        f"/open-apis/docx/v1/documents/{document_id}/raw_content", token, {"lang": 0}
    )
    content = (data.get("content") or "").strip()
    if not content:
        raise FeishuError("文档内容为空")
    return content
