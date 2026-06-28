"""命令行入口。

用法：
  ai-test-copilot generate spec.md
  ai-test-copilot generate spec.md --json > plan.json
  cat failure.log | ai-test-copilot analyze -
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .client import Copilot, CopilotError
from .models import FailureAnalysis, TestPlan

app = typer.Typer(
    add_completion=False,
    help="AI 测试助手：生成测试用例 / 分析失败日志。",
)
console = Console()
err_console = Console(stderr=True)


def _read_input(source: str) -> str:
    """从文件路径或 '-'(stdin) 读取文本。"""
    if source == "-":
        data = sys.stdin.read()
    else:
        path = Path(source)
        if not path.is_file():
            err_console.print(f"[red]找不到文件：{source}[/red]")
            raise typer.Exit(code=2)
        data = path.read_text(encoding="utf-8")
    if not data.strip():
        err_console.print("[red]输入为空[/red]")
        raise typer.Exit(code=2)
    return data


def _render_plan(plan: TestPlan) -> None:
    console.print(Panel(f"[bold]{plan.feature}[/bold]\n{plan.summary}", title="测试计划"))
    table = Table(show_lines=True)
    table.add_column("编号", style="cyan", no_wrap=True)
    table.add_column("类型")
    table.add_column("优先级", justify="center")
    table.add_column("标题")
    table.add_column("预期结果")
    for tc in plan.test_cases:
        table.add_row(tc.id, tc.type.value, tc.priority.value, tc.title, tc.expected_result)
    console.print(table)
    console.print(f"[dim]共 {len(plan.test_cases)} 条用例[/dim]")


def _render_analysis(a: FailureAnalysis) -> None:
    color = {"product_bug": "red", "test_bug": "yellow", "flaky": "magenta"}.get(
        a.category.value, "blue"
    )
    console.print(
        Panel(
            f"[bold]{a.summary}[/bold]\n\n"
            f"归类：[{color}]{a.category.value}[/{color}]   置信度：{a.confidence:.0%}",
            title="失败分析",
        )
    )
    console.print("[bold]根因：[/bold]")
    console.print(a.root_cause)
    if a.evidence:
        console.print("\n[bold]关键证据：[/bold]")
        for e in a.evidence:
            console.print(f"  • {e}")
    console.print("\n[bold]修复建议：[/bold]")
    for f in a.suggested_fixes:
        console.print(f"  • {f}")


@app.command()
def generate(
    spec: str = typer.Argument(..., help="需求/接口描述文件路径，'-' 表示从 stdin 读取"),
    json_out: bool = typer.Option(False, "--json", help="输出 JSON（便于落库/转 pytest 骨架）"),
    model: Optional[str] = typer.Option(None, "--model", help="覆盖默认模型"),
) -> None:
    """从需求/接口描述生成测试用例。"""
    text = _read_input(spec)
    try:
        plan = Copilot(model=model).generate_tests(text)
    except CopilotError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    if json_out:
        console.print_json(plan.model_dump_json())
    else:
        _render_plan(plan)


@app.command()
def analyze(
    log: str = typer.Argument(..., help="失败日志文件路径，'-' 表示从 stdin 读取"),
    json_out: bool = typer.Option(False, "--json", help="输出 JSON"),
    model: Optional[str] = typer.Option(None, "--model", help="覆盖默认模型"),
) -> None:
    """分析测试失败日志，定位根因并给出修复建议。"""
    text = _read_input(log)
    try:
        result = Copilot(model=model).analyze_failure(text)
    except CopilotError as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    if json_out:
        console.print_json(result.model_dump_json())
    else:
        _render_analysis(result)


if __name__ == "__main__":
    app()
