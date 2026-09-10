from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest

from agentqa.case_generator import case_fingerprint, create_test_plan
from agentqa.executor import execute_test_plan
from agentqa.models import AssertionFailure
from agentqa.models import TestReport as Report
from agentqa.openapi_parser import parse_openapi_document
from agentqa.regression import compare_test_reports
from agentqa.reporter import regression_as_markdown
from agentqa_demo.app import app


@pytest.fixture
def plan():
    return create_test_plan(parse_openapi_document(app.openapi()), "http://agentqa-demo-api:8000")


async def run(plan, handler=None):
    transport = httpx.MockTransport(handler) if handler else httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=plan.base_url) as client:
        return await execute_test_plan(plan, approved=True, client=client)


def after_fix(request):
    if request.method == "GET" and request.url.path.startswith("/users/"):
        return httpx.Response(200, json={"id": 1, "name": "Alice", "age": 29})
    if request.method == "POST" and request.url.path == "/users":
        return httpx.Response(201, json={"id": 3, "name": "test-name", "age": 1})
    if request.url.path == "/login":
        return httpx.Response(200, json={"detail": "Invalid credentials"})
    if request.url.path == "/orders":
        return httpx.Response(500, json={"detail": "new failure"})
    return httpx.Response(200, json={"deleted": True, "id": 1})


@pytest.mark.asyncio
async def test_real_executor_before_and_after_detects_all_categories(plan):
    before = await run(plan)
    after = await run(plan, after_fix)
    comparison = compare_test_reports(before, after)
    assert (before.passed, before.failed) == (2, 3)
    assert (comparison.summary.fixed, comparison.summary.new_defects, comparison.summary.unresolved, comparison.summary.persistent_passes) == (1, 1, 2, 1)
    assert comparison.summary.comparable == 5
    assert before.run_id != after.run_id
    assert before.plan == plan
    fixed = next(item for item in comparison.items if item.category == "fixed")
    assert "$.age" in fixed.before.failures[0].message
    assert fixed.after.failures == []
    markdown = regression_as_markdown(comparison)
    assert "已修复" in markdown and "新增缺陷" in markdown and "仍未解决" in markdown
    assert "$.age" in markdown and "expected status 401" in markdown


@pytest.mark.asyncio
async def test_reordering_and_renaming_case_ids_does_not_change_matching(plan):
    before = await run(plan)
    reordered = plan.model_copy(deep=True)
    reordered.cases.reverse()
    for index, case in enumerate(reordered.cases):
        case.id = f"different-{index}"
        case.name = "renamed display title"
    reordered.id = "reordered-plan"
    after = await run(reordered)
    comparison = compare_test_reports(before, after)
    assert comparison.summary.unresolved == 3
    assert comparison.summary.persistent_passes == 2
    assert comparison.summary.added_cases == comparison.summary.missing_cases == 0


@pytest.mark.asyncio
async def test_missing_added_and_changed_tests_are_not_defect_transitions(plan):
    before = await run(plan)
    changed = plan.model_copy(deep=True)
    removed = changed.cases.pop(0)
    changed.cases[0].expected_status_codes = [418]
    added = removed.model_copy(update={"id": "added", "path_template": "/new-endpoint"})
    changed.cases.append(added)
    changed.id = "different-plan"
    comparison = compare_test_reports(before, await run(changed, after_fix))
    assert comparison.summary.added_cases == 1
    assert comparison.summary.missing_cases == 1
    assert comparison.summary.changed_cases == 1
    assert comparison.summary.fixed == 0


@pytest.mark.asyncio
async def test_network_errors_are_execution_errors_not_new_defects(plan):
    before = await run(plan)

    def offline(request):
        raise httpx.ConnectError("offline", request=request)

    after = await run(plan, offline)
    comparison = compare_test_reports(before, after)
    assert comparison.summary.execution_errors == 5
    assert comparison.summary.new_defects == comparison.summary.fixed == 0
    assert compare_test_reports(after, before).summary.execution_errors == 5


def legacy(report):
    data = report.model_dump(mode="json", exclude={"schema_version", "run_id", "plan"})
    for result in data["results"]:
        result.pop("case_fingerprint", None)
    return Report.model_validate(data)


@pytest.mark.asyncio
async def test_legacy_and_mixed_reports_require_identical_plan(plan):
    report = await run(plan)
    for before, after in [(legacy(report), legacy(report)), (legacy(report), report)]:
        comparison = compare_test_reports(before, after)
        assert comparison.summary.unresolved == 3
        assert comparison.warnings
    changed = report.model_copy(deep=True)
    changed.plan_id = "other-plan"
    with pytest.raises(ValueError, match="plan"):
        compare_test_reports(legacy(report), legacy(changed))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation, message",
    [
        ("totals", "counts"),
        ("duplicate", "duplicate"),
        ("passed", "passed"),
        ("fingerprint", "fingerprint"),
        ("snapshot", "snapshot"),
        ("target", "target"),
    ],
)
async def test_invalid_reports_are_rejected(plan, mutation, message):
    before = await run(plan)
    after = before.model_copy(deep=True)
    if mutation == "totals":
        after.total += 1
    elif mutation == "duplicate":
        after.results[1].case_id = after.results[0].case_id
    elif mutation == "passed":
        result = next(item for item in after.results if item.passed)
        result.failures = [AssertionFailure(kind="status", message="bad")]
    elif mutation == "fingerprint":
        after.results[0].case_fingerprint = "incorrect"
    elif mutation == "snapshot":
        after.plan = None
    elif mutation == "target":
        after.base_url = "http://localhost:9999"
        after.plan.base_url = after.base_url
    with pytest.raises(ValueError, match=message):
        compare_test_reports(before, after)


@pytest.mark.asyncio
async def test_duplicate_fingerprints_are_ambiguous(plan):
    duplicate = plan.cases[0].model_copy(update={"id": "duplicate"})
    plan.cases.append(duplicate)
    report = await run(plan)
    with pytest.raises(ValueError, match="duplicate.*fingerprint"):
        compare_test_reports(report, report)


def test_empty_legacy_reports_are_valid():
    report = Report(plan_id="empty", api_title="API", base_url="http://localhost:8000", generated_at=datetime.now(UTC), total=0, passed=0, failed=0, results=[])
    comparison = compare_test_reports(report, report)
    assert comparison.items == []
    assert comparison.summary.comparable == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("query_params", {"limit": 2}),
        ("headers", {"X-Test": "new"}),
        ("json_body", {"changed": True}),
        ("expected_status_codes", [418]),
        ("max_response_time_ms", 9000),
        ("expected_schema", {"type": "string"}),
    ],
)
def test_fingerprint_includes_request_and_assertion_conditions(plan, field, value):
    original = plan.cases[0]
    assert case_fingerprint(original) != case_fingerprint(original.model_copy(update={field: value}))


@pytest.mark.asyncio
async def test_changed_failure_evidence_is_visible(plan):
    before = await run(plan)
    after = before.model_copy(deep=True)
    failed = next(result for result in after.results if not result.passed)
    failed.failures = [AssertionFailure(kind="status", message="different failure")]
    comparison = compare_test_reports(before, after)
    item = next(item for item in comparison.items if item.after.case_id == failed.case_id)
    assert item.category == "unresolved"
    assert item.evidence_changed is True
    assert "失败证据变化" in regression_as_markdown(comparison)


@pytest.mark.asyncio
async def test_ambiguous_changed_scenarios_are_not_paired(plan):
    original = plan.cases[0]
    plan.cases = [original.model_copy(update={"id": f"old-{i}", "query_params": {"variant": i}}) for i in range(2)]
    before = await run(plan)
    plan.cases = [original.model_copy(update={"id": f"new-{i}", "query_params": {"variant": i}}) for i in range(2, 4)]
    after = await run(plan)
    comparison = compare_test_reports(before, after)
    assert comparison.summary.added_cases == comparison.summary.missing_cases == 2
    assert comparison.summary.changed_cases == comparison.summary.fixed == 0
    assert any("歧义" in warning for warning in comparison.warnings)


@pytest.mark.asyncio
async def test_legacy_id_collision_is_rejected(plan):
    before = legacy(await run(plan))
    after = before.model_copy(deep=True)
    after.results[0].path_template = "/another-operation"
    with pytest.raises(ValueError, match="different cases"):
        compare_test_reports(before, after)


def test_fingerprint_normalizes_object_key_order_and_status_sets(plan):
    case = plan.cases[0].model_copy(update={"query_params": {"a": 1, "b": 2}, "expected_status_codes": [201, 200]})
    reordered = case.model_copy(update={"query_params": {"b": 2, "a": 1}, "expected_status_codes": [200, 201, 200]})
    assert case_fingerprint(case) == case_fingerprint(reordered)
