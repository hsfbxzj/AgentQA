"""LangChain tools that expose AgentQA core capabilities to DeerFlow."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated

import httpx
from langchain.tools import InjectedToolCallId, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from agentqa.case_generator import create_test_plan
from agentqa.executor import execute_test_plan
from agentqa.models import TestPlan
from agentqa.openapi_parser import parse_openapi_document
from agentqa.reporter import report_as_json, report_as_markdown
from agentqa.security import validate_target_url
from deerflow.tools.types import Runtime

DEFAULT_SPEC_URL = "http://agentqa-demo-api:8000/openapi.json"
DEFAULT_BASE_URL = "http://agentqa-demo-api:8000"
MAX_SPEC_BYTES = 2 * 1024 * 1024
REPORT_MARKDOWN_FILENAME = "agentqa-report.md"
REPORT_JSON_FILENAME = "agentqa-report.json"
REPORT_ARTIFACT_PATHS = [
    f"/mnt/user-data/outputs/{REPORT_MARKDOWN_FILENAME}",
    f"/mnt/user-data/outputs/{REPORT_JSON_FILENAME}",
]


async def _read_openapi_source(source: str) -> str:
    if not source.startswith(("http://", "https://")):
        return source
    validate_target_url(source)
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=False, trust_env=False) as client:
        response = await client.get(source)
        response.raise_for_status()
    if len(response.content) > MAX_SPEC_BYTES:
        raise ValueError("OpenAPI document exceeds the 2 MiB AgentQA MVP limit")
    return response.text


def _get_outputs_dir(runtime: Runtime) -> Path:
    if runtime.state is None:
        raise ValueError("Thread runtime state is not available")
    thread_data = runtime.state.get("thread_data") or {}
    outputs_path = thread_data.get("outputs_path")
    if not outputs_path:
        raise ValueError("Thread outputs path is not available in runtime state")
    return Path(outputs_path).expanduser().resolve()


def _write_report_files(outputs_dir: Path, markdown_report: str, json_report: str) -> None:
    outputs_dir.mkdir(parents=True, exist_ok=True)
    (outputs_dir / REPORT_MARKDOWN_FILENAME).write_text(markdown_report, encoding="utf-8")
    (outputs_dir / REPORT_JSON_FILENAME).write_text(json_report, encoding="utf-8")


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
    report = await execute_test_plan(plan, approved=approved)
    json_report = report_as_json(report)
    markdown_report = report_as_markdown(report)
    outputs_dir = _get_outputs_dir(runtime)
    await asyncio.to_thread(_write_report_files, outputs_dir, markdown_report, json_report)

    payload = json.dumps(
        {
            "status": "completed",
            "report": json.loads(json_report),
            "markdown_report": markdown_report,
            "artifacts": REPORT_ARTIFACT_PATHS,
        },
        ensure_ascii=False,
        indent=2,
    )
    return Command(
        update={
            "artifacts": REPORT_ARTIFACT_PATHS,
            "messages": [ToolMessage(content=payload, tool_call_id=tool_call_id)],
        }
    )
