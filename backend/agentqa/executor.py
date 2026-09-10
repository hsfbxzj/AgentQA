"""Approved HTTP execution for AgentQA test plans."""

from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import httpx

from agentqa.assertions import evaluate_response
from agentqa.case_generator import case_fingerprint
from agentqa.models import AssertionFailure, TestPlan, TestReport, TestResult
from agentqa.security import validate_request_path, validate_target_url


class ApprovalRequiredError(PermissionError):
    """Raised when execution is attempted before explicit approval."""


def _render_path(template: str, values: dict[str, Any]) -> str:
    path = template
    for name, value in values.items():
        path = path.replace("{" + name + "}", quote(str(value), safe=""))
    if "{" in path or "}" in path:
        raise ValueError(f"Missing required path parameter for {template}")
    return validate_request_path(path)


async def execute_test_plan(
    plan: TestPlan,
    *,
    approved: bool,
    client: httpx.AsyncClient | None = None,
) -> TestReport:
    """Execute a reviewed plan; no network request is sent unless approved is true."""

    if not approved:
        raise ApprovalRequiredError("Explicit user approval is required before AgentQA sends HTTP requests")
    validate_target_url(plan.base_url)

    owns_client = client is None
    active_client = client or httpx.AsyncClient(
        base_url=plan.base_url,
        timeout=httpx.Timeout(10.0),
        follow_redirects=False,
        trust_env=False,
    )
    results: list[TestResult] = []
    try:
        for case in plan.cases:
            path = _render_path(case.path_template, case.path_params)
            started = perf_counter()
            try:
                response = await active_client.request(
                    case.method,
                    path,
                    params=case.query_params,
                    headers=case.headers,
                    json=case.json_body,
                )
                elapsed_ms = (perf_counter() - started) * 1000
                failures, response_body = evaluate_response(case, response, elapsed_ms)
                status_code = response.status_code
            except httpx.HTTPError as exc:
                elapsed_ms = (perf_counter() - started) * 1000
                failures = [AssertionFailure(kind="network", message=f"request failed: {exc}")]
                response_body = None
                status_code = None
            results.append(
                TestResult(
                    case_id=case.id,
                    case_fingerprint=case_fingerprint(case),
                    name=case.name,
                    method=case.method,
                    path_template=case.path_template,
                    request_url=f"{plan.base_url}{path}",
                    status_code=status_code,
                    elapsed_ms=round(elapsed_ms, 2),
                    passed=not failures,
                    failures=failures,
                    response_body=response_body,
                )
            )
    finally:
        if owns_client:
            await active_client.aclose()

    passed = sum(result.passed for result in results)
    return TestReport(
        schema_version=2,
        run_id=f"run-{uuid4().hex}",
        plan=plan.model_copy(deep=True),
        plan_id=plan.id,
        api_title=plan.api_title,
        base_url=plan.base_url,
        generated_at=datetime.now(UTC),
        total=len(results),
        passed=passed,
        failed=len(results) - passed,
        results=results,
    )
