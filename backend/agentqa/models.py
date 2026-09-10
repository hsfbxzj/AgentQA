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
    case_fingerprint: str | None = None
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

    schema_version: Literal[1, 2] = 1
    run_id: str | None = Field(default=None, pattern=r"^run-[a-f0-9]{32}$")
    plan: TestPlan | None = None
    plan_id: str
    api_title: str
    base_url: str
    generated_at: datetime
    total: int
    passed: int
    failed: int
    results: list[TestResult]


RegressionCategory = Literal["fixed", "new_defect", "unresolved", "persistent_pass", "added_case", "missing_case", "changed_case", "execution_error"]


class RegressionItem(StrictModel):
    """One matched pair, changed test, or coverage difference with evidence."""

    category: RegressionCategory
    before: TestResult | None = None
    after: TestResult | None = None
    evidence_changed: bool = False


class RegressionSummary(StrictModel):
    """Counts refer to cases, never inferred root-cause defects."""

    comparable: int = 0
    fixed: int = 0
    new_defects: int = 0
    unresolved: int = 0
    persistent_passes: int = 0
    added_cases: int = 0
    missing_cases: int = 0
    changed_cases: int = 0
    execution_errors: int = 0


class RunReference(StrictModel):
    run_id: str | None
    plan_id: str
    generated_at: datetime
    total: int
    passed: int
    failed: int


class RegressionReport(StrictModel):
    schema_version: Literal[1] = 1
    comparison_id: str = Field(pattern=r"^comparison-[a-f0-9]{32}$")
    generated_at: datetime
    api_title: str
    base_url: str
    baseline: RunReference
    current: RunReference
    summary: RegressionSummary
    items: list[RegressionItem]
    warnings: list[str] = Field(default_factory=list)
