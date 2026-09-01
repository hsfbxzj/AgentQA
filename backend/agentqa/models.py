"""Pydantic data contracts shared by every AgentQA module."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    """Reject unexpected fields so malformed LLM/tool data fails early."""

    model_config = ConfigDict(extra="forbid")


class ApiParameter(StrictModel):
    """Normalized OpenAPI parameter."""

    name: str
    location: Literal["path", "query", "header", "cookie"]
    required: bool = False
    schema_data: dict[str, Any] = Field(default_factory=dict)
    description: str | None = None


class ApiResponse(StrictModel):
    """One documented HTTP response for an API operation."""

    status_code: str
    description: str = ""
    schema_data: dict[str, Any] | None = None


class ApiOperation(StrictModel):
    """Framework-independent representation of one HTTP operation."""

    method: str
    path: str
    operation_id: str
    summary: str = ""
    tags: list[str] = Field(default_factory=list)
    parameters: list[ApiParameter] = Field(default_factory=list)
    request_schema: dict[str, Any] | None = None
    request_required: bool = False
    responses: list[ApiResponse] = Field(default_factory=list)
    security_schemes: list[str] = Field(default_factory=list)


class ParsedOpenAPI(StrictModel):
    """Normalized subset of an OpenAPI 3.x document used by AgentQA."""

    title: str
    api_version: str = ""
    openapi_version: str
    servers: list[str] = Field(default_factory=list)
    operations: list[ApiOperation]


class TestCase(StrictModel):
    """A deterministic HTTP test case that can be reviewed before execution."""

    id: str
    name: str
    method: str
    path_template: str
    path_params: dict[str, Any] = Field(default_factory=dict)
    query_params: dict[str, Any] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    json_body: Any | None = None
    expected_status_codes: list[int]
    expected_schema: dict[str, Any] | None = None
    expect_empty_body: bool = False
    max_response_time_ms: float = Field(default=5000.0, gt=0)
    rule: str


class TestPlan(StrictModel):
    """Reviewable and hash-addressed collection of test cases."""

    id: str
    api_title: str
    base_url: str
    cases: list[TestCase]


class AssertionFailure(StrictModel):
    """Evidence explaining why one programmatic assertion failed."""

    kind: Literal["status", "schema", "body", "latency", "network"]
    message: str


class TestResult(StrictModel):
    """Observed result for one executed test case."""

    case_id: str
    name: str
    method: str
    path_template: str
    request_url: str
    status_code: int | None
    elapsed_ms: float
    passed: bool
    failures: list[AssertionFailure] = Field(default_factory=list)
    response_body: Any | None = None


class TestReport(StrictModel):
    """Machine-readable result of an approved AgentQA run."""

    plan_id: str
    api_title: str
    base_url: str
    generated_at: datetime
    total: int
    passed: int
    failed: int
    results: list[TestResult]
