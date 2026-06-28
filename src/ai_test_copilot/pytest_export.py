"""把 TestPlan 导出成 pytest 用例骨架。

每条用例生成一个 test 函数：标题/优先级/类型/步骤/预期写进 docstring，
函数体 raise NotImplementedError，并打 @pytest.mark.skip，方便先跑通再逐条实现。
"""

from __future__ import annotations

import re

from .models import TestPlan


def _func_name(case_id: str, used: dict[str, int]) -> str:
    base = "test_" + (re.sub(r"[^a-zA-Z0-9]+", "_", case_id).strip("_").lower() or "case")
    if base in used:
        used[base] += 1
        return f"{base}_{used[base]}"
    used[base] = 0
    return base


def _safe(text: str) -> str:
    # 避免文本里的三引号破坏 docstring
    return text.replace('"""', "'''")


def plan_to_pytest(plan: TestPlan) -> str:
    out: list[str] = []
    out.append(f'"""{_safe(plan.feature)} — pytest 用例骨架（由 ai-test-copilot 生成）')
    out.append("")
    out.append(_safe(plan.summary))
    out.append("")
    out.append(f"共 {len(plan.test_cases)} 条用例；实现后移除对应的 @pytest.mark.skip。")
    out.append('"""')
    out.append("import pytest")
    out.append("")

    used: dict[str, int] = {}
    for tc in plan.test_cases:
        name = _func_name(tc.id, used)
        out.append("")
        out.append('@pytest.mark.skip(reason="TODO: 实现用例")')
        out.append(f"def {name}():")
        doc = [f"[{tc.priority.value}/{tc.type.value}] {_safe(tc.title)}"]
        if tc.preconditions:
            doc += ["", "前置条件:"] + [f"    - {_safe(p)}" for p in tc.preconditions]
        doc += ["", "步骤:"] + [f"    {i}. {_safe(s)}" for i, s in enumerate(tc.steps, 1)]
        doc += ["", "预期:", f"    {_safe(tc.expected_result)}"]
        out.append('    """' + doc[0])
        for line in doc[1:]:
            out.append(("    " + line) if line else "")
        out.append('    """')
        out.append("    raise NotImplementedError")
    return "\n".join(out) + "\n"


def slug_filename(feature: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", feature).strip("_").lower()
    return f"test_{s or 'cases'}.py"
