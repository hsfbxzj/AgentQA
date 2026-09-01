from __future__ import annotations

import httpx
import pytest

from agentqa.case_generator import create_test_plan
from agentqa.executor import ApprovalRequiredError, execute_test_plan
from agentqa.openapi_parser import parse_openapi_document
from agentqa_demo.app import app


@pytest.mark.asyncio
async def test_executor_refuses_to_send_requests_without_approval() -> None:
    plan = create_test_plan(parse_openapi_document(app.openapi()), "http://agentqa-demo-api:8000")

    with pytest.raises(ApprovalRequiredError, match="approval"):
        await execute_test_plan(plan, approved=False)


@pytest.mark.asyncio
async def test_executor_finds_all_three_seeded_defects() -> None:
    plan = create_test_plan(parse_openapi_document(app.openapi()), "http://agentqa-demo-api:8000")
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url=plan.base_url) as client:
        report = await execute_test_plan(plan, approved=True, client=client)

    assert report.total == 5
    assert report.passed == 2
    assert report.failed == 3

    failures_by_case = {result.case_id: result for result in report.results if not result.passed}
    assert any("$.age" in failure.message for result in failures_by_case.values() for failure in result.failures)
    assert any("expected status 401" in failure.message for result in failures_by_case.values() for failure in result.failures)
    assert any("expected status 204" in failure.message for result in failures_by_case.values() for failure in result.failures)
