"""Compare recorded AgentQA runs without issuing requests or inferring root causes."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from uuid import uuid4

from agentqa.case_generator import case_fingerprint
from agentqa.models import RegressionItem, RegressionReport, RegressionSummary, RunReference, TestReport, TestResult


def _validate_report(report: TestReport) -> None:
    ids = [result.case_id for result in report.results]
    if len(set(ids)) != len(ids):
        raise ValueError("Report contains duplicate case IDs")
    passed = sum(result.passed for result in report.results)
    if (report.total, report.passed, report.failed) != (len(ids), passed, len(ids) - passed):
        raise ValueError("Report counts do not match its results")
    for result in report.results:
        if result.passed != (not result.failures):
            raise ValueError(f"Inconsistent passed flag and failure evidence: {result.case_id}")
        if result.status_code is None and not any(failure.kind == "network" for failure in result.failures):
            raise ValueError(f"Missing HTTP status without network evidence: {result.case_id}")
    if report.schema_version == 1:
        return
    plan = report.plan
    if plan is None or report.run_id is None:
        raise ValueError("Version 2 reports require a plan snapshot and run ID")
    if (plan.id, plan.api_title, plan.base_url.rstrip("/")) != (report.plan_id, report.api_title, report.base_url.rstrip("/")):
        raise ValueError("Report metadata does not match the plan snapshot")
    cases = {case.id: case for case in plan.cases}
    if len(cases) != len(plan.cases) or set(cases) != set(ids):
        raise ValueError("Report results do not match the plan snapshot case IDs")
    fingerprints: set[str] = set()
    for result in report.results:
        case = cases[result.case_id]
        fingerprint = case_fingerprint(case)
        if result.case_fingerprint != fingerprint or (result.method, result.path_template) != (case.method, case.path_template):
            raise ValueError(f"Case fingerprint or operation does not match the plan snapshot: {result.case_id}")
        if fingerprint in fingerprints:
            raise ValueError("Report contains duplicate case fingerprints; matching would be ambiguous")
        fingerprints.add(fingerprint)


def _pair(before: TestResult, after: TestResult) -> RegressionItem:
    if any(failure.kind == "network" for result in (before, after) for failure in result.failures):
        category = "execution_error"
    elif before.passed:
        category = "persistent_pass" if after.passed else "new_defect"
    else:
        category = "fixed" if after.passed else "unresolved"
    evidence_before = {(failure.kind, failure.message) for failure in before.failures}
    evidence_after = {(failure.kind, failure.message) for failure in after.failures}
    return RegressionItem(category=category, before=before, after=after, evidence_changed=category == "unresolved" and evidence_before != evidence_after)


def _reference(report: TestReport) -> RunReference:
    return RunReference(**{field: getattr(report, field) for field in RunReference.model_fields})


def compare_test_reports(baseline: TestReport, current: TestReport) -> RegressionReport:
    """Classify comparable cases; keep coverage changes and execution errors separate."""

    _validate_report(baseline)
    _validate_report(current)
    if baseline.base_url.rstrip("/") != current.base_url.rstrip("/") or baseline.api_title != current.api_title:
        raise ValueError("Reports must describe the same API and target base URL")
    warnings: list[str] = []
    if baseline.run_id is not None and baseline.run_id == current.run_id:
        warnings.append("基线与当前报告使用相同运行 ID；这不是两次独立执行。")
    legacy = baseline.schema_version == 1 or current.schema_version == 1
    if legacy:
        if baseline.plan_id != current.plan_id:
            raise ValueError("Legacy reports can only be compared with the same plan ID")
        warnings.append("包含旧版报告：仅根据相同计划 ID 和用例 ID 匹配，无法独立验证原始测试条件。")
    before_by_key = {(result.case_id if legacy else result.case_fingerprint): result for result in baseline.results}
    after_by_key = {(result.case_id if legacy else result.case_fingerprint): result for result in current.results}
    items: list[RegressionItem] = []
    for key, before in before_by_key.items():
        after = after_by_key.get(key)
        if after is not None:
            if (before.method, before.path_template, before.name) != (after.method, after.path_template, after.name) and legacy:
                raise ValueError("Legacy case ID identifies different cases in the same plan")
            items.append(_pair(before, after))

    missing = [result for key, result in before_by_key.items() if key not in after_by_key]
    added = [result for key, result in after_by_key.items() if key not in before_by_key]
    # Only pair changed conditions if one old and one new scenario remain for an
    # operation/rule. Multiple candidates stay as coverage changes, never guesses.
    if not legacy:
        before_rules = {case.id: case.rule for case in baseline.plan.cases}
        after_rules = {case.id: case.rule for case in current.plan.cases}
        old_groups = defaultdict(list)
        new_groups = defaultdict(list)
        for result in missing:
            old_groups[(result.method, result.path_template, before_rules[result.case_id])].append(result)
        for result in added:
            new_groups[(result.method, result.path_template, after_rules[result.case_id])].append(result)
        changed_before: set[str] = set()
        changed_after: set[str] = set()
        for key, old in old_groups.items():
            new = new_groups.get(key, [])
            if len(old) == len(new) == 1:
                items.append(RegressionItem(category="changed_case", before=old[0], after=new[0]))
                changed_before.add(old[0].case_id)
                changed_after.add(new[0].case_id)
            elif new:
                warnings.append(f"{key[0]} {key[1]} 的剩余用例匹配存在歧义，已分别列为缺失和新增用例。")
        missing = [result for result in missing if result.case_id not in changed_before]
        added = [result for result in added if result.case_id not in changed_after]
    items.extend(RegressionItem(category="missing_case", before=result) for result in missing)
    items.extend(RegressionItem(category="added_case", after=result) for result in added)
    counts = Counter(item.category for item in items)
    summary = RegressionSummary(
        comparable=sum(counts[key] for key in ("fixed", "new_defect", "unresolved", "persistent_pass")),
        fixed=counts["fixed"],
        new_defects=counts["new_defect"],
        unresolved=counts["unresolved"],
        persistent_passes=counts["persistent_pass"],
        added_cases=counts["added_case"],
        missing_cases=counts["missing_case"],
        changed_cases=counts["changed_case"],
        execution_errors=counts["execution_error"],
    )
    return RegressionReport(
        comparison_id=f"comparison-{uuid4().hex}",
        generated_at=datetime.now(UTC),
        api_title=current.api_title,
        base_url=current.base_url,
        baseline=_reference(baseline),
        current=_reference(current),
        summary=summary,
        items=items,
        warnings=warnings,
    )
