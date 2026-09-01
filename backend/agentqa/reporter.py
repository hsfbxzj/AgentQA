"""Render AgentQA reports for machines and people."""

from __future__ import annotations

from agentqa.models import TestReport


def report_as_json(report: TestReport) -> str:
    """Return a stable JSON representation suitable for CI or later comparison."""

    return report.model_dump_json(indent=2)


def report_as_markdown(report: TestReport) -> str:
    """Return a concise human-readable test report."""

    lines = [
        "# AgentQA API 测试报告",
        "",
        f"- 被测 API：{report.api_title}",
        f"- Base URL：`{report.base_url}`",
        f"- 测试计划：`{report.plan_id}`",
        f"- 结果：{report.total} 条用例，{report.passed} 个通过，{report.failed} 个失败",
        "",
        "## 用例结果",
        "",
        "| 结果 | 接口 | 状态码 | 耗时 |",
        "|---|---|---:|---:|",
    ]
    for result in report.results:
        icon = "PASS" if result.passed else "FAIL"
        status = result.status_code if result.status_code is not None else "N/A"
        lines.append(
            f"| {icon} | `{result.method} {result.path_template}` | {status} | {result.elapsed_ms:.2f} ms |"
        )
    failed_results = [result for result in report.results if not result.passed]
    if failed_results:
        lines.extend(["", "## 失败证据", ""])
        for result in failed_results:
            lines.append(f"### {result.method} {result.path_template}")
            lines.append("")
            for failure in result.failures:
                lines.append(f"- **{failure.kind}**：{failure.message}")
            lines.append("")
    lines.extend(
        [
            "## 结论",
            "",
            f"本次测试共发现 {report.failed} 个失败用例；结论由程序断言生成，不由大模型主观判断。",
            "",
        ]
    )
    return "\n".join(lines)
