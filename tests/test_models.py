"""模型层单测——不调用任何外部 API，可在 CI 里离线跑。"""

import pytest
from pydantic import ValidationError

from ai_test_copilot.models import (
    CaseType,
    FailureAnalysis,
    FailureCategory,
    Priority,
    TestCase,
    TestPlan,
)


def test_test_plan_roundtrip():
    plan = TestPlan(
        feature="登录",
        summary="覆盖正常与异常登录",
        test_cases=[
            TestCase(
                id="TC-001",
                title="正确账号密码登录成功",
                type=CaseType.functional,
                priority=Priority.P0,
                steps=["输入正确账号", "输入正确密码", "点击登录"],
                expected_result="跳转到首页",
            )
        ],
    )
    # 序列化 -> 反序列化应保持一致（落库 / 转 pytest 骨架依赖这点）
    again = TestPlan.model_validate_json(plan.model_dump_json())
    assert again == plan
    assert again.test_cases[0].type is CaseType.functional


def test_confidence_must_be_within_range():
    with pytest.raises(ValidationError):
        FailureAnalysis(
            summary="x",
            category=FailureCategory.flaky,
            root_cause="x",
            suggested_fixes=["x"],
            confidence=1.5,  # 越界，应被拒绝
        )


def test_priority_enum_rejects_unknown():
    with pytest.raises(ValidationError):
        TestCase(
            id="TC-002",
            title="t",
            type=CaseType.boundary,
            priority="P9",  # 非法优先级
            steps=["s"],
            expected_result="r",
        )
