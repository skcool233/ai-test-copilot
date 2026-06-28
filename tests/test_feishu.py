"""飞书模块单测——离线逻辑（URL 解析、授权 URL、token 存取、未授权报错）。"""

import time

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


def test_parse_base_url():
    assert parse_url("https://x.feishu.cn/base/Bs1appToken?table=tbl9") == (
        "base",
        "Bs1appToken",
    )


def test_parse_invalid_url():
    with pytest.raises(FeishuError):
        parse_url("https://example.com/not-a-feishu-doc")


@pytest.fixture
def cfg(monkeypatch, tmp_path):
    monkeypatch.setenv("FEISHU_APP_ID", "cli_test")
    monkeypatch.setenv("FEISHU_APP_SECRET", "secret_test")
    monkeypatch.setenv("FEISHU_REDIRECT_URI", "http://h/feishu/callback")
    monkeypatch.setenv("FEISHU_TOKEN_FILE", str(tmp_path / "tok.json"))


def test_authorize_url(cfg):
    url = feishu.authorize_url("st8")
    assert url.startswith("https://accounts.feishu.cn/open-apis/authen/v1/authorize")
    assert "client_id=cli_test" in url
    assert "response_type=code" in url
    assert "state=st8" in url
    assert "offline_access" in url  # 需要它才能拿 refresh_token


def test_not_authorized_then_token_roundtrip(cfg):
    assert feishu.is_authorized() is False
    with pytest.raises(FeishuError, match="尚未授权"):
        feishu.fetch_doc_text("https://x.feishu.cn/docx/Abc123")

    # 模拟存入有效令牌
    feishu._save(
        {
            "access_token": "a",
            "access_expires": time.time() + 3600,
            "refresh_token": "r",
            "refresh_expires": time.time() + 86400,
        }
    )
    assert feishu.is_authorized() is True
    assert feishu._user_token() == "a"


def test_expired_refresh_token_reports(cfg):
    feishu._save({"refresh_token": "r", "refresh_expires": time.time() - 1})
    assert feishu.is_authorized() is False
    with pytest.raises(FeishuError):
        feishu._user_token()


def test_plan_blocks_structure():
    from ai_test_copilot.models import CaseType, Priority, TestCase, TestPlan

    plan = TestPlan(
        feature="登录",
        summary="s",
        test_cases=[
            TestCase(
                id="TC-001",
                title="成功",
                type=CaseType.functional,
                priority=Priority.P0,
                preconditions=["已注册"],
                steps=["输入", "提交"],
                expected_result="跳首页",
            )
        ],
    )
    blocks = feishu._plan_blocks(plan)
    assert blocks[0]["block_type"] == 3  # heading1 = feature
    assert "heading1" in blocks[0]
    # 含步骤/预期文本块
    flat = str(blocks)
    assert "步骤：输入 → 提交" in flat
    assert "预期：跳首页" in flat
