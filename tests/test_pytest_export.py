"""pytest 骨架导出单测：产物须是合法 Python。"""

from ai_test_copilot.models import CaseType, Priority, TestCase, TestPlan
from ai_test_copilot.pytest_export import plan_to_pytest, slug_filename


def _plan():
    return TestPlan(
        feature="登录",
        summary="覆盖登录",
        test_cases=[
            TestCase(
                id="TC-001",
                title='正确账号密码登录成功（含 """ 边界）',
                type=CaseType.functional,
                priority=Priority.P0,
                preconditions=["用户已注册"],
                steps=["输入账号", "输入密码", "点击登录"],
                expected_result="跳转首页",
            ),
            TestCase(
                id="TC-001",  # 故意重名，验证函数名去重
                title="重复编号用例",
                type=CaseType.negative,
                priority=Priority.P1,
                steps=["x"],
                expected_result="y",
            ),
        ],
    )


def test_output_is_valid_python():
    code = plan_to_pytest(_plan())
    compile(code, "test_generated.py", "exec")  # 不能有语法错误
    assert "import pytest" in code
    assert "def test_tc_001(" in code
    assert "def test_tc_001_1(" in code  # 去重
    assert code.count("@pytest.mark.skip(reason=") == 2  # 每条用例一个装饰器


def test_slug_filename():
    assert slug_filename("登录 接口 v2").endswith(".py")
    assert slug_filename("").startswith("test_")
