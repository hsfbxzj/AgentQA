"""Render AgentQA reports for machines and people."""

from __future__ import annotations

from html import escape

from agentqa.models import RegressionReport, TestReport, TestResult


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
        f"- 运行 ID：`{report.run_id or '旧版报告（无运行 ID）'}`",
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
        lines.append(f"| {icon} | `{result.method} {result.path_template}` | {status} | {result.elapsed_ms:.2f} ms |")
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


def regression_as_json(report: RegressionReport) -> str:
    return report.model_dump_json(indent=2)


def _cell(value: str) -> str:
    return escape(value).replace("|", "&#124;").replace("`", "&#96;").replace("\r", " ").replace("\n", " ")


def _outcome(result: TestResult | None) -> str:
    if result is None:
        return "未执行"
    status = str(result.status_code) if result.status_code is not None else "无 HTTP 响应"
    return f"{'PASS' if result.passed else 'FAIL'} / {status} / {result.elapsed_ms:.2f} ms"


def regression_as_markdown(report: RegressionReport) -> str:
    """Render transitions with both sides' evidence, including coverage gaps."""

    summary = report.summary
    labels = {
        "fixed": "已修复",
        "new_defect": "新增缺陷",
        "unresolved": "仍未解决",
        "persistent_pass": "持续通过",
        "added_case": "新增用例",
        "missing_case": "缺失用例",
        "changed_case": "测试条件变化",
        "execution_error": "网络执行异常",
    }
    lines = [
        "# AgentQA 回归测试报告",
        "",
        f"- 被测 API：{_cell(report.api_title)}",
        f"- Base URL：{_cell(report.base_url)}",
        f"- 对比 ID：{report.comparison_id}",
        f"- 基线：{report.baseline.run_id or '旧版报告'} / {_cell(report.baseline.plan_id)} / {report.baseline.generated_at.isoformat()}",
        f"- 当前：{report.current.run_id or '旧版报告'} / {_cell(report.current.plan_id)} / {report.current.generated_at.isoformat()}",
        f"- 可比较用例：{summary.comparable}；已修复 {summary.fixed}，新增缺陷 {summary.new_defects}，仍未解决 {summary.unresolved}，持续通过 {summary.persistent_passes}",
        f"- 覆盖变化：新增用例 {summary.added_cases}，缺失用例 {summary.missing_cases}，测试条件变化 {summary.changed_cases}；网络执行异常 {summary.execution_errors}",
        "",
        "统计单位是测试用例，不代表独立根因数量。未复测、条件变化和网络执行异常不计入已修复或新增缺陷。",
        "",
    ]
    if report.warnings:
        lines.extend(["## 比较限制", "", *[f"- {_cell(warning)}" for warning in report.warnings], ""])
    lines.extend(["## 用例对比", "", "| 分类 | 接口 | 修复前 | 修复后 |", "|---|---|---|---|"])
    for item in report.items:
        result = item.after or item.before
        lines.append(f"| {labels[item.category]} | {_cell(result.method + ' ' + result.path_template)} | {_outcome(item.before)} | {_outcome(item.after)} |")
    lines.extend(["", "## 前后证据", ""])
    for item in report.items:
        if item.category == "persistent_pass":
            continue
        result = item.after or item.before
        lines.extend([f"### {labels[item.category]}：{_cell(result.method + ' ' + result.path_template)}", ""])
        if item.evidence_changed:
            lines.append("失败证据变化：两次均未通过，但不能据此认定是同一个根因。")
        for label, side in (("修复前", item.before), ("修复后", item.after)):
            lines.append(f"- **{label}**：{_outcome(side)}")
            if side is not None:
                lines.append(f"  - 用例：{_cell(side.case_id)}；请求：{_cell(side.request_url)}")
                if item.category == "changed_case":
                    lines.append(f"  - 测试条件指纹：{side.case_fingerprint}")
                lines.extend(f"  - **{failure.kind}**：{_cell(failure.message)}" for failure in side.failures)
        lines.append("")
    return "\n".join(lines)
