"""LangChain tools that expose AgentQA core capabilities to DeerFlow."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import httpx
from langchain.tools import InjectedToolCallId, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from agentqa.case_generator import create_test_plan
from agentqa.executor import execute_test_plan
from agentqa.models import TestPlan, TestReport
from agentqa.openapi_parser import parse_openapi_document
from agentqa.regression import compare_test_reports
from agentqa.reporter import regression_as_json, regression_as_markdown, report_as_json, report_as_markdown
from agentqa.security import validate_target_url
from deerflow.tools.types import Runtime

DEFAULT_SPEC_URL = "http://agentqa-demo-api:8000/openapi.json"
DEFAULT_BASE_URL = "http://agentqa-demo-api:8000"
MAX_SPEC_BYTES = 2 * 1024 * 1024
REPORT_MARKDOWN_FILENAME = "agentqa-report.md"
REPORT_JSON_FILENAME = "agentqa-report.json"


async def _read_openapi_source(source: str) -> str:
    if not source.startswith(("http://", "https://")):
        return source
    validate_target_url(source)
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=False, trust_env=False) as client:
        response = await client.get(source)
        response.raise_for_status()
    if len(response.content) > MAX_SPEC_BYTES:
        raise ValueError("OpenAPI document exceeds the 2 MiB AgentQA limit")
    return response.text


def _get_outputs_dir(runtime: Runtime) -> Path:
    if runtime.state is None:
        raise ValueError("Thread runtime state is not available")
    thread_data = runtime.state.get("thread_data") or {}
    outputs_path = thread_data.get("outputs_path")
    if not outputs_path:
        raise ValueError("Thread outputs path is not available in runtime state")
    return Path(outputs_path).expanduser().resolve()


def _write_artifacts(outputs_dir: Path, relative_dir: str, files: dict[str, str], *, latest: bool = False) -> list[str]:
    # relative_dir and filenames are generated internally, never report/user paths.
    archive = outputs_dir / relative_dir
    archive.mkdir(parents=True, exist_ok=False)
    for filename, content in files.items():
        (archive / filename).write_text(content, encoding="utf-8")
    if latest:
        for filename in (REPORT_MARKDOWN_FILENAME, REPORT_JSON_FILENAME):
            temporary = outputs_dir / f".{filename}.{uuid4().hex}.tmp"
            temporary.write_text(files[filename], encoding="utf-8")
            temporary.replace(outputs_dir / filename)
    return [f"/mnt/user-data/outputs/{relative_dir}/{filename}" for filename in files]


def _report_command(tool_call_id: str, name: str, report: str, markdown: str, artifacts: list[str]) -> Command:
    payload = json.dumps({"status": "completed", "report": json.loads(report), "markdown_report": markdown, "artifacts": artifacts}, ensure_ascii=False, indent=2)
    return Command(update={"artifacts": artifacts, "messages": [ToolMessage(content=payload, tool_call_id=tool_call_id, name=name)]})


@tool("agentqa_create_test_plan", parse_docstring=True)
async def agentqa_create_test_plan_tool(
    openapi_source: str = DEFAULT_SPEC_URL,
    base_url: str = DEFAULT_BASE_URL,
) -> str:
    """Parse OpenAPI and create a reviewable API test plan without testing the target yet.

    Args:
        openapi_source: Local-allowlisted OpenAPI URL or inline JSON/YAML text.
        base_url: Local-allowlisted base URL that the approved tests will target.
    """

    validate_target_url(base_url)
    document_text = await _read_openapi_source(openapi_source)
    specification = parse_openapi_document(document_text)
    plan = create_test_plan(specification, base_url)
    return json.dumps(
        {
            "status": "awaiting_user_approval",
            "message": "No test requests have been sent. Show this plan to the user and ask for explicit approval.",
            "plan": plan.model_dump(mode="json"),
        },
        ensure_ascii=False,
        indent=2,
    )


@tool("agentqa_execute_test_plan", parse_docstring=True)
async def agentqa_execute_test_plan_tool(
    plan_json: str,
    runtime: Runtime,
    tool_call_id: Annotated[str, InjectedToolCallId],
    approved: bool = False,
) -> Command:
    """Execute an approved AgentQA plan and automatically deliver both report files.

    Args:
        plan_json: JSON returned by agentqa_create_test_plan; either the wrapper or its plan object.
        approved: Set true only after the user explicitly confirms execution in the conversation.
    """

    decoded = json.loads(plan_json)
    plan_data = decoded.get("plan", decoded) if isinstance(decoded, dict) else decoded
    plan = TestPlan.model_validate(plan_data)
    outputs_dir = _get_outputs_dir(runtime)
    report = await execute_test_plan(plan, approved=approved)
    json_report = report_as_json(report)
    markdown_report = report_as_markdown(report)
    if report.run_id is None:
        raise ValueError("Executed report is missing its run ID")
    artifacts = await asyncio.to_thread(
        _write_artifacts,
        outputs_dir,
        f"agentqa/runs/{report.run_id}",
        {REPORT_MARKDOWN_FILENAME: markdown_report, REPORT_JSON_FILENAME: json_report, "agentqa-plan.json": plan.model_dump_json(indent=2)},
        latest=True,
    )
    return _report_command(tool_call_id, "agentqa_execute_test_plan", json_report, markdown_report, artifacts)


@tool("agentqa_compare_test_reports", parse_docstring=True)
async def agentqa_compare_test_reports_tool(
    baseline_report_json: str,
    current_report_json: str,
    runtime: Runtime,
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    """Compare recorded AgentQA runs and deliver regression reports without HTTP requests.

    Args:
        baseline_report_json: Before-fix report JSON, or the complete execution tool result containing report.
        current_report_json: After-fix report JSON, or the complete execution tool result containing report.
    """

    def decode(source: str) -> TestReport:
        data = json.loads(source)
        return TestReport.model_validate(data.get("report", data) if isinstance(data, dict) else data)

    comparison = compare_test_reports(decode(baseline_report_json), decode(current_report_json))
    markdown = regression_as_markdown(comparison)
    json_report = regression_as_json(comparison)
    artifacts = await asyncio.to_thread(
        _write_artifacts,
        _get_outputs_dir(runtime),
        f"agentqa/comparisons/{comparison.comparison_id}",
        {"agentqa-regression.md": markdown, "agentqa-regression.json": json_report},
    )
    return _report_command(tool_call_id, "agentqa_compare_test_reports", json_report, markdown, artifacts)
