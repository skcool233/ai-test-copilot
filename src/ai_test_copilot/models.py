"""结构化输出的数据模型（Pydantic）。

这些模型既用于 Claude 的 structured outputs（保证返回合法 JSON），
也用于本地校验和渲染。
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class CaseType(str, Enum):
    """测试用例分类——高级测试工程师关注的覆盖维度。"""

    functional = "functional"  # 正常功能路径
    boundary = "boundary"  # 边界值
    negative = "negative"  # 异常/非法输入
    security = "security"  # 安全相关
    performance = "performance"  # 性能相关


class Priority(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


class TestCase(BaseModel):
    id: str = Field(description="用例编号，如 TC-001")
    title: str = Field(description="一句话描述用例意图")
    type: CaseType
    priority: Priority
    preconditions: list[str] = Field(default_factory=list, description="前置条件")
    steps: list[str] = Field(description="可执行的操作步骤，逐条")
    expected_result: str = Field(description="预期结果，可断言")


class TestPlan(BaseModel):
    feature: str = Field(description="被测功能/需求名称")
    summary: str = Field(description="对测试范围的简短说明")
    test_cases: list[TestCase]


class FailureCategory(str, Enum):
    product_bug = "product_bug"  # 产品代码缺陷
    test_bug = "test_bug"  # 用例/脚本自身问题
    flaky = "flaky"  # 不稳定（时序、并发、依赖外部）
    environment = "environment"  # 环境/配置/依赖
    unknown = "unknown"


class FailureAnalysis(BaseModel):
    summary: str = Field(description="一句话概括失败原因")
    category: FailureCategory
    root_cause: str = Field(description="对根因的详细分析")
    evidence: list[str] = Field(
        default_factory=list, description="日志中支撑该判断的关键行/线索"
    )
    suggested_fixes: list[str] = Field(description="具体可执行的修复建议")
    confidence: float = Field(ge=0.0, le=1.0, description="判断置信度 0~1")
