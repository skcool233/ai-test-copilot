"""Web 接口单测——打桩 Copilot，不触网。"""

import importlib

import pytest
from fastapi.testclient import TestClient

from ai_test_copilot import webapp
from ai_test_copilot.models import (
    CaseType,
    FailureAnalysis,
    FailureCategory,
    Priority,
    TestCase,
    TestPlan,
)


class _FakeCopilot:
    def __init__(self, *a, **k):
        pass

    def generate_tests(self, spec):
        return TestPlan(
            feature="demo",
            summary="s",
            test_cases=[
                TestCase(
                    id="TC-001",
                    title="t",
                    type=CaseType.functional,
                    priority=Priority.P0,
                    steps=["s"],
                    expected_result="r",
                )
            ],
        )

    def analyze_failure(self, log):
        return FailureAnalysis(
            summary="并发未加锁",
            category=FailureCategory.product_bug,
            root_cause="rc",
            suggested_fixes=["加行锁"],
            confidence=0.9,
        )


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(webapp, "Copilot", _FakeCopilot)
    monkeypatch.setenv("HISTORY_FILE", str(tmp_path / "h.jsonl"))  # 别污染真实 home
    return TestClient(webapp.app)


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "AI 测试助手" in r.text


def test_generate(client):
    r = client.post("/api/generate", json={"text": "登录功能"})
    assert r.status_code == 200
    assert r.json()["test_cases"][0]["id"] == "TC-001"


def test_analyze(client):
    r = client.post("/api/analyze", json={"text": "并发日志"})
    assert r.status_code == 200
    assert r.json()["category"] == "product_bug"


def test_empty_input_rejected(client):
    r = client.post("/api/generate", json={"text": "  "})
    assert r.status_code == 400


def test_password_gate(monkeypatch):
    # 设置了密码：缺密码 401，带对密码 200
    monkeypatch.setattr(webapp, "Copilot", _FakeCopilot)
    monkeypatch.setattr(webapp, "APP_PASSWORD", "secret")
    c = TestClient(webapp.app)

    assert c.post("/api/generate", json={"text": "x"}).status_code == 401
    ok = c.post(
        "/api/generate", json={"text": "x"}, headers={"X-App-Password": "secret"}
    )
    assert ok.status_code == 200


def test_feishu_fetch(client, monkeypatch):
    monkeypatch.setattr(webapp, "fetch_doc_text", lambda url: "需求正文 from " + url)
    r = client.post("/api/feishu/fetch", json={"url": "https://x.feishu.cn/docx/Abc123"})
    assert r.status_code == 200
    assert r.json()["text"].startswith("需求正文")
    assert r.json()["chars"] > 0


def test_feishu_fetch_error(client, monkeypatch):
    def boom(url):
        from ai_test_copilot.feishu import FeishuError

        raise FeishuError("无权限")

    monkeypatch.setattr(webapp, "fetch_doc_text", boom)
    r = client.post("/api/feishu/fetch", json={"url": "https://x.feishu.cn/docx/Abc123"})
    assert r.status_code == 400
    assert "无权限" in r.json()["detail"]


def test_feishu_batch_fetch(client, monkeypatch):
    monkeypatch.setattr(webapp, "fetch_doc_text", lambda url: "正文:" + url[-3:])
    r = client.post(
        "/api/feishu/fetch",
        json={"url": "https://x.feishu.cn/docx/aaa\nhttps://x.feishu.cn/wiki/bbb"},
    )
    assert r.status_code == 200
    assert r.json()["count"] == 2
    assert "=====" in r.json()["text"]  # 多链接会带分隔标题


def test_to_pytest_endpoint(client):
    plan = {
        "feature": "登录",
        "summary": "s",
        "test_cases": [
            {
                "id": "TC-001",
                "title": "t",
                "type": "functional",
                "priority": "P0",
                "preconditions": [],
                "steps": ["s"],
                "expected_result": "r",
            }
        ],
    }
    r = client.post("/api/to-pytest", json=plan)
    assert r.status_code == 200
    assert "import pytest" in r.json()["code"]
    assert r.json()["filename"].endswith(".py")


def test_to_pytest_bad_plan(client):
    r = client.post("/api/to-pytest", json={"feature": "x"})  # 缺 test_cases
    assert r.status_code == 400


def test_history_records_generate(client):
    # 生成后历史里应能查到，且能取回完整结果
    client.post("/api/generate", json={"text": "登录功能"})
    metas = client.get("/api/history").json()
    assert len(metas) == 1 and metas[0]["mode"] == "generate"
    full = client.get(f"/api/history/{metas[0]['id']}").json()
    assert full["result"]["test_cases"][0]["id"] == "TC-001"


def test_history_item_404(client):
    assert client.get("/api/history/nope").status_code == 404


def test_feishu_export(client, monkeypatch):
    monkeypatch.setattr(webapp, "create_doc_from_plan", lambda plan: "https://x.feishu.cn/docx/NEW")
    plan = {
        "feature": "登录",
        "summary": "s",
        "test_cases": [
            {
                "id": "TC-001",
                "title": "t",
                "type": "functional",
                "priority": "P0",
                "preconditions": [],
                "steps": ["s"],
                "expected_result": "r",
            }
        ],
    }
    r = client.post("/api/feishu/export", json=plan)
    assert r.status_code == 200
    assert r.json()["url"].endswith("/docx/NEW")


def test_module_reimport_smoke():
    # 确保模块可被重新导入（部署时 uvicorn --reload 不会崩）
    importlib.reload(webapp)
