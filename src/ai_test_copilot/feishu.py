"""飞书（Lark）文档读取。

用企业自建应用的 App ID / App Secret 换 tenant_access_token，再读文档正文。
支持新版文档(/docx/)与知识库(/wiki/)链接。凭据从环境变量读取，不落代码。
"""

from __future__ import annotations

import os
import re
import time

import httpx

FEISHU_BASE = os.environ.get("FEISHU_BASE", "https://open.feishu.cn")
_TIMEOUT = 20.0

# 简单的进程内 token 缓存（tenant_access_token 默认有效约 2 小时）。
_token_cache: dict = {"token": None, "exp": 0.0}


class FeishuError(RuntimeError):
    """对外暴露的飞书相关错误。"""


def _app_creds() -> tuple[str, str]:
    aid = os.environ.get("FEISHU_APP_ID")
    sec = os.environ.get("FEISHU_APP_SECRET")
    if not aid or not sec:
        raise FeishuError("未配置飞书应用凭据（FEISHU_APP_ID / FEISHU_APP_SECRET）")
    return aid, sec


def _tenant_token() -> str:
    now = time.time()
    if _token_cache["token"] and _token_cache["exp"] > now + 60:
        return _token_cache["token"]
    aid, sec = _app_creds()
    try:
        r = httpx.post(
            f"{FEISHU_BASE}/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": aid, "app_secret": sec},
            timeout=_TIMEOUT,
        )
        data = r.json()
    except httpx.HTTPError as exc:
        raise FeishuError(f"连接飞书失败：{exc}") from exc
    if data.get("code") != 0:
        raise FeishuError(f"获取飞书 token 失败：{data.get('msg')}（code {data.get('code')}）")
    _token_cache["token"] = data["tenant_access_token"]
    _token_cache["exp"] = now + data.get("expire", 7200)
    return _token_cache["token"]


def parse_url(url: str) -> tuple[str, str]:
    """从飞书链接解析出 (类型, token)，类型 ∈ {docx, wiki, docs}。"""
    m = re.search(r"/(docx|wiki|docs)/([A-Za-z0-9]+)", url)
    if not m:
        raise FeishuError("无法识别的飞书文档链接（需含 /docx/ 或 /wiki/）")
    return m.group(1), m.group(2)


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
        code = data.get("code")
        if code in (1254005, 1254404, 99991672, 91402):  # 常见的无权限/找不到
            msg += "（请确认应用已开通文档读取权限，且该文档已分享给此应用）"
        raise FeishuError(f"飞书 API 错误：{msg}（code {code}）")
    return data["data"]


def _resolve_wiki(node_token: str, token: str) -> str:
    """知识库节点 → 实际文档 obj_token。"""
    data = _api_get("/open-apis/wiki/v2/spaces/get_node", token, {"token": node_token})
    node = data["node"]
    if node.get("obj_type") != "docx":
        raise FeishuError(f"暂不支持的知识库节点类型：{node.get('obj_type')}")
    return node["obj_token"]


def fetch_doc_text(url: str) -> str:
    """给定飞书文档链接，返回其纯文本正文。"""
    token = _tenant_token()
    doc_type, tok = parse_url(url)
    if doc_type == "wiki":
        document_id = _resolve_wiki(tok, token)
    elif doc_type == "docx":
        document_id = tok
    else:  # 旧版 /docs/
        raise FeishuError("暂不支持旧版文档(/docs/)，请使用新版文档(/docx/)或知识库链接")

    data = _api_get(
        f"/open-apis/docx/v1/documents/{document_id}/raw_content", token, {"lang": 0}
    )
    content = (data.get("content") or "").strip()
    if not content:
        raise FeishuError("文档内容为空，或应用无该文档读取权限")
    return content
