from __future__ import annotations

import httpx
import pytest

from agentqa.case_generator import create_test_plan
from agentqa.executor import execute_test_plan
from agentqa.openapi_parser import parse_openapi_document
from agentqa.reporter import report_as_json, report_as_markdown
from agentqa_demo.app import app


@pytest.mark.asyncio
async def test_report_can_be_rendered_as_json_and_markdown() -> None:
    plan = create_test_plan(parse_openapi_document(app.openapi()), "http://agentqa-demo-api:8000")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=plan.base_url) as client:
        report = await execute_test_plan(plan, approved=True, client=client)

    json_report = report_as_json(report)
    markdown_report = report_as_markdown(report)

    assert '"failed": 3' in json_report
    assert "# AgentQA API 测试报告" in markdown_report
    assert "3 个失败" in markdown_report
    assert "GET /users/{user_id}" in markdown_report
