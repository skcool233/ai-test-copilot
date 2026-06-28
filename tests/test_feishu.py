"""飞书模块单测——只测离线逻辑（URL 解析、缺凭据报错），不触网。"""

import pytest

from ai_test_copilot import feishu
from ai_test_copilot.feishu import FeishuError, parse_url


def test_parse_docx_url():
    assert parse_url("https://x.feishu.cn/docx/AbcD1234efGh") == ("docx", "AbcD1234efGh")


def test_parse_wiki_url():
    assert parse_url("https://x.feishu.cn/wiki/Wk99TokenXyz?from=share") == (
        "wiki",
        "Wk99TokenXyz",
    )


def test_parse_invalid_url():
    with pytest.raises(FeishuError):
        parse_url("https://example.com/not-a-feishu-doc")


def test_missing_credentials(monkeypatch):
    monkeypatch.delenv("FEISHU_APP_ID", raising=False)
    monkeypatch.delenv("FEISHU_APP_SECRET", raising=False)
    feishu._token_cache["token"] = None  # 清缓存
    with pytest.raises(FeishuError, match="凭据"):
        feishu.fetch_doc_text("https://x.feishu.cn/docx/Abc123")
