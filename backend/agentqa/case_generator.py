"""Deterministic rule engine that turns normalized operations into test cases."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from agentqa.models import ApiOperation, ApiParameter, ApiResponse, ParsedOpenAPI, TestCase, TestPlan

AUTH_WORDS = ("login", "signin", "sign-in", "auth", "token")


def case_fingerprint(case: TestCase) -> str:
    """Identify request and assertion conditions independently of display IDs/order."""

    conditions = case.model_dump(mode="json", exclude={"id", "name"})
    conditions["method"] = case.method.upper()
    conditions["expected_status_codes"] = sorted(set(case.expected_status_codes))
    encoded = json.dumps(conditions, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _sample_value(schema: dict[str, Any], name: str = "value") -> Any:
    if "example" in schema:
        return schema["example"]
    if "default" in schema:
        return schema["default"]
    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and enum_values:
        return enum_values[0]
    schema_type = schema.get("type")
    if schema_type == "object" or isinstance(schema.get("properties"), dict):
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        selected = required or set(properties)
        return {key: _sample_value(properties[key], key) for key in properties if key in selected}
    if schema_type == "array":
        return [_sample_value(schema.get("items", {}), name)]
    if schema_type == "integer":
        return int(schema.get("minimum", 1))
    if schema_type == "number":
        return float(schema.get("minimum", 1.0))
    if schema_type == "boolean":
        return True
    if schema_type == "string":
        if schema.get("format") == "email":
            return "agentqa@example.com"
        if schema.get("format") == "date":
            return "2026-01-01"
        lowered = name.lower()
        if lowered in {"username", "user_name"}:
            return "demo"
        if "password" in lowered:
            return "agentqa"
        min_length = int(schema.get("minLength", 1))
        return ("test-" + name)[: max(min_length, len("test-" + name))]
    return "test-value"


def _parameter_value(parameter: ApiParameter) -> Any:
    if parameter.name.lower() in {"id", "user_id", "userid", "limit", "page", "size"}:
        return int(parameter.schema_data.get("minimum", 1))
    return _sample_value(parameter.schema_data, parameter.name)


def _is_auth_operation(operation: ApiOperation) -> bool:
    haystack = " ".join((operation.path, operation.operation_id, operation.summary)).lower()
    return any(word in haystack for word in AUTH_WORDS)


def _select_response(operation: ApiOperation) -> tuple[ApiResponse, str]:
    numeric = {int(response.status_code): response for response in operation.responses if response.status_code.isdigit()}
    if _is_auth_operation(operation) and 401 in numeric:
        return numeric[401], "documented-auth-rejection"
    successes = [status for status in numeric if 200 <= status < 400]
    if successes:
        selected = min(successes)
        return numeric[selected], "documented-success"
    if numeric:
        selected = min(numeric)
        return numeric[selected], "documented-response"
    return operation.responses[0], "documented-default-response"


def _create_case(operation: ApiOperation, index: int) -> TestCase:
    selected_response, rule = _select_response(operation)
    path_params: dict[str, Any] = {}
    query_params: dict[str, Any] = {}
    headers: dict[str, str] = {}
    for parameter in operation.parameters:
        if not parameter.required and parameter.location not in {"query"}:
            continue
        value = _parameter_value(parameter)
        if parameter.location == "path":
            path_params[parameter.name] = value
        elif parameter.location == "query":
            query_params[parameter.name] = value
        elif parameter.location == "header":
            headers[parameter.name] = str(value)

    json_body = _sample_value(operation.request_schema) if operation.request_schema else None
    if rule == "documented-auth-rejection" and isinstance(json_body, dict):
        if "username" in json_body:
            json_body["username"] = "invalid-user"
        if "password" in json_body:
            json_body["password"] = "invalid-password"

    try:
        expected_status = int(selected_response.status_code)
    except ValueError:
        expected_status = 200
    return TestCase(
        id=f"case-{index:03d}-{operation.method.lower()}",
        name=f"{operation.summary or operation.operation_id} [{rule}]",
        method=operation.method,
        path_template=operation.path,
        path_params=path_params,
        query_params=query_params,
        headers=headers,
        json_body=json_body,
        expected_status_codes=[expected_status],
        expected_schema=selected_response.schema_data,
        expect_empty_body=expected_status in {204, 304},
        rule=rule,
    )


def create_test_plan(specification: ParsedOpenAPI, base_url: str) -> TestPlan:
    """Generate one deterministic, reviewable contract case per operation."""

    cases = [_create_case(operation, index) for index, operation in enumerate(specification.operations, start=1)]
    fingerprint_source = {
        "api_title": specification.title,
        "base_url": base_url.rstrip("/"),
        "cases": [case.model_dump(mode="json") for case in cases],
    }
    digest = hashlib.sha256(json.dumps(fingerprint_source, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()[:12]
    return TestPlan(
        id=f"plan-{digest}",
        api_title=specification.title,
        base_url=base_url.rstrip("/"),
        cases=cases,
    )
