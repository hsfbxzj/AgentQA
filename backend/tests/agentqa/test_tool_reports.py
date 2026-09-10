from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest

import agentqa.tools as tools_module
from agentqa.case_generator import create_test_plan
from agentqa.executor import ApprovalRequiredError, execute_test_plan
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
        run_id="run-" + "0" * 32,
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

    archive = f"agentqa/runs/{report.run_id}"
    assert result.update["artifacts"] == [f"/mnt/user-data/outputs/{archive}/{name}" for name in ("agentqa-report.md", "agentqa-report.json", "agentqa-plan.json")]
    assert (outputs_dir / "agentqa-report.md").read_text(encoding="utf-8") == report_as_markdown(report)
    assert (outputs_dir / "agentqa-report.json").read_text(encoding="utf-8") == report_as_json(report)
    assert (outputs_dir / archive / "agentqa-report.json").read_text(encoding="utf-8") == report_as_json(report)
    assert json.loads((outputs_dir / archive / "agentqa-plan.json").read_text(encoding="utf-8")) == json.loads(_plan_json())

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


@pytest.mark.asyncio
async def test_two_executions_keep_history_and_comparison_delivers_real_files(tmp_path, monkeypatch):
    outputs_dir = tmp_path / "outputs"
    runtime = _runtime(str(outputs_dir))

    async def local_execute(plan, *, approved):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=plan.base_url) as client:
            return await execute_test_plan(plan, approved=approved, client=client)

    monkeypatch.setattr(tools_module, "execute_test_plan", local_execute)
    first = await tools_module.agentqa_execute_test_plan_tool.coroutine(plan_json=_plan_json(), runtime=runtime, tool_call_id="first", approved=True)
    first_payload = json.loads(first.update["messages"][0].content)
    first_file = outputs_dir / f"agentqa/runs/{first_payload['report']['run_id']}/agentqa-report.json"
    original_bytes = first_file.read_bytes()
    second = await tools_module.agentqa_execute_test_plan_tool.coroutine(plan_json=_plan_json(), runtime=runtime, tool_call_id="second", approved=True)
    second_payload = json.loads(second.update["messages"][0].content)
    assert first_payload["report"]["run_id"] != second_payload["report"]["run_id"]
    assert first_file.read_bytes() == original_bytes
    assert json.loads((outputs_dir / "agentqa-report.json").read_text(encoding="utf-8")) == second_payload["report"]

    def unexpected_request(*args, **kwargs):
        pytest.fail("Comparing recorded reports must not send HTTP requests")

    monkeypatch.setattr(httpx.AsyncClient, "request", unexpected_request)
    comparison = await tools_module.agentqa_compare_test_reports_tool.coroutine(
        baseline_report_json=first.update["messages"][0].content,
        current_report_json=json.dumps(second_payload["report"]),
        runtime=runtime,
        tool_call_id="compare",
    )
    payload = json.loads(comparison.update["messages"][0].content)
    assert payload["report"]["summary"]["unresolved"] == 3
    assert payload["report"]["baseline"]["run_id"] == first_payload["report"]["run_id"]
    assert payload["report"]["current"]["run_id"] == second_payload["report"]["run_id"]
    assert payload["artifacts"] == comparison.update["artifacts"]
    assert len(payload["artifacts"]) == 2
    for path in payload["artifacts"]:
        content = (outputs_dir / path.removeprefix("/mnt/user-data/outputs/")).read_text(encoding="utf-8")
        if path.endswith(".json"):
            assert json.loads(content) == payload["report"]
        else:
            assert content == payload["markdown_report"]
    assert first_file.read_bytes() == original_bytes


@pytest.mark.asyncio
async def test_compare_rejects_invalid_input_without_artifacts(tmp_path):
    outputs_dir = tmp_path / "outputs"
    with pytest.raises(ValueError):
        await tools_module.agentqa_compare_test_reports_tool.coroutine(
            baseline_report_json="{}",
            current_report_json="not-json",
            runtime=_runtime(str(outputs_dir)),
            tool_call_id="invalid",
        )
    assert not outputs_dir.exists()


def test_archive_collision_cannot_overwrite_existing_report(tmp_path):
    tools_module._write_artifacts(tmp_path, "agentqa/runs/test", {"report.json": "first"})
    with pytest.raises(FileExistsError):
        tools_module._write_artifacts(tmp_path, "agentqa/runs/test", {"report.json": "second"})
    assert (tmp_path / "agentqa/runs/test/report.json").read_text() == "first"


@pytest.mark.asyncio
async def test_missing_runtime_fails_before_http_execution(monkeypatch):
    async def unexpected_execute(*args, **kwargs):
        pytest.fail("Missing output context must fail before execution")

    monkeypatch.setattr(tools_module, "execute_test_plan", unexpected_execute)
    with pytest.raises(ValueError, match="outputs path"):
        await tools_module.agentqa_execute_test_plan_tool.coroutine(
            plan_json=_plan_json(),
            runtime=SimpleNamespace(state={}),
            tool_call_id="missing-runtime",
            approved=True,
        )
