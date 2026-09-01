from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

import agentqa.tools as tools_module
from agentqa.case_generator import create_test_plan
from agentqa.executor import ApprovalRequiredError
from agentqa.models import TestReport as AgentQATestReport
from agentqa.openapi_parser import parse_openapi_document
from agentqa.reporter import report_as_json, report_as_markdown
from agentqa_demo.app import app


def _runtime(outputs_path: str) -> SimpleNamespace:
    return SimpleNamespace(
        state={"thread_data": {"outputs_path": outputs_path}},
        context={"thread_id": "thread-agentqa"},
        config={},
    )


def _plan_json() -> str:
    plan = create_test_plan(parse_openapi_document(app.openapi()), "http://agentqa-demo-api:8000")
    return plan.model_dump_json()


@pytest.mark.asyncio
async def test_execute_tool_writes_and_presents_both_reports(tmp_path, monkeypatch) -> None:
    outputs_dir = tmp_path / "outputs"
    report = AgentQATestReport(
        plan_id="plan-test",
        api_title="AgentQA Demo API",
        base_url="http://agentqa-demo-api:8000",
        generated_at=datetime(2026, 8, 29, tzinfo=UTC),
        total=0,
        passed=0,
        failed=0,
        results=[],
    )

    async def fake_execute_test_plan(plan, *, approved):
        assert approved is True
        return report

    monkeypatch.setattr(tools_module, "execute_test_plan", fake_execute_test_plan)

    result = await tools_module.agentqa_execute_test_plan_tool.coroutine(
        plan_json=_plan_json(),
        approved=True,
        runtime=_runtime(str(outputs_dir)),
        tool_call_id="call-agentqa",
    )

    assert result.update["artifacts"] == [
        "/mnt/user-data/outputs/agentqa-report.md",
        "/mnt/user-data/outputs/agentqa-report.json",
    ]
    assert (outputs_dir / "agentqa-report.md").read_text(encoding="utf-8") == report_as_markdown(report)
    assert (outputs_dir / "agentqa-report.json").read_text(encoding="utf-8") == report_as_json(report)

    tool_message = result.update["messages"][0]
    assert tool_message.tool_call_id == "call-agentqa"
    payload = json.loads(tool_message.content)
    assert payload["status"] == "completed"
    assert payload["artifacts"] == result.update["artifacts"]


@pytest.mark.asyncio
async def test_execute_tool_does_not_write_reports_before_approval(tmp_path) -> None:
    outputs_dir = tmp_path / "outputs"

    with pytest.raises(ApprovalRequiredError, match="approval"):
        await tools_module.agentqa_execute_test_plan_tool.coroutine(
            plan_json=_plan_json(),
            approved=False,
            runtime=_runtime(str(outputs_dir)),
            tool_call_id="call-agentqa-denied",
        )

    assert not outputs_dir.exists()
