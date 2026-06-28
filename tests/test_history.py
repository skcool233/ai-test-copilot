"""历史记录单测——写本地临时文件，不触网。"""

import pytest

from ai_test_copilot import history


@pytest.fixture
def hist_file(monkeypatch, tmp_path):
    monkeypatch.setenv("HISTORY_FILE", str(tmp_path / "h.jsonl"))


def test_add_list_get(hist_file):
    assert history.list_meta() == []
    i1 = history.add("generate", "登录", "需求...", {"feature": "登录", "test_cases": []})
    i2 = history.add("analyze", "空指针", "日志...", {"summary": "空指针"})

    metas = history.list_meta()
    assert [m["id"] for m in metas] == [i2, i1]  # 最新在前
    assert metas[0]["mode"] == "analyze"
    assert "input" not in metas[0]  # 列表只给元信息

    full = history.get(i1)
    assert full["input"] == "需求..."
    assert full["result"]["feature"] == "登录"
    assert history.get("nope") is None


def test_cap_to_max(hist_file, monkeypatch):
    monkeypatch.setattr(history, "MAX_ITEMS", 3)
    for n in range(5):
        history.add("generate", f"t{n}", "x", {})
    metas = history.list_meta()
    assert len(metas) == 3
    assert [m["title"] for m in metas] == ["t4", "t3", "t2"]  # 只留最近 3 条
