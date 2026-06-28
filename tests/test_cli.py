"""CLI 单测——用打桩替换 Copilot，不触网。"""

import json

from typer.testing import CliRunner

from ai_test_copilot import cli
from ai_test_copilot.models import (
    CaseType,
    FailureAnalysis,
    FailureCategory,
    Priority,
    TestCase,
    TestPlan,
)

runner = CliRunner()


class _FakeCopilot:
    """替身：不调用 Claude，直接返回固定结果。"""

    def __init__(self, *args, **kwargs):
        pass

    def generate_tests(self, spec: str) -> TestPlan:
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

    def analyze_failure(self, log: str) -> FailureAnalysis:
        return FailureAnalysis(
            summary="空指针",
            category=FailureCategory.product_bug,
            root_cause="rc",
            evidence=["NullPointerException at line 42"],
            suggested_fixes=["加空值校验"],
            confidence=0.8,
        )


def test_generate_json(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "Copilot", _FakeCopilot)
    spec = tmp_path / "spec.md"
    spec.write_text("登录功能", encoding="utf-8")

    result = runner.invoke(cli.app, ["generate", str(spec), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["test_cases"][0]["id"] == "TC-001"


def test_analyze_json(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "Copilot", _FakeCopilot)
    log = tmp_path / "f.log"
    log.write_text("NullPointerException", encoding="utf-8")

    result = runner.invoke(cli.app, ["analyze", str(log), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["category"] == "product_bug"


def test_missing_file_exits_2():
    result = runner.invoke(cli.app, ["generate", "/no/such/file.md"])
    assert result.exit_code == 2
