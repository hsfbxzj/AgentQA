"""Deterministic assertions used to judge HTTP responses without an LLM."""

from __future__ import annotations

from typing import Any

import httpx

from agentqa.models import AssertionFailure, TestCase


def _type_matches(value: Any, expected: str) -> bool:
    checks = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "null": lambda item: item is None,
    }
    return expected not in checks or checks[expected](value)


def _schema_failures(value: Any, schema: dict[str, Any], location: str = "$") -> list[AssertionFailure]:
    failures: list[AssertionFailure] = []
    if value is None and schema.get("nullable"):
        return failures
    expected_type = schema.get("type")
    if isinstance(expected_type, list):
        if not any(_type_matches(value, item) for item in expected_type):
            return [AssertionFailure(kind="schema", message=f"{location}: expected one of {expected_type}, got {type(value).__name__}")]
    elif isinstance(expected_type, str) and not _type_matches(value, expected_type):
        return [AssertionFailure(kind="schema", message=f"{location}: expected {expected_type}, got {type(value).__name__}")]

    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and value not in enum_values:
        failures.append(AssertionFailure(kind="schema", message=f"{location}: value is not in enum {enum_values}"))
    if isinstance(value, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                failures.append(AssertionFailure(kind="schema", message=f"{location}.{key}: required property is missing"))
        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            for key, child_schema in properties.items():
                if key in value and isinstance(child_schema, dict):
                    failures.extend(_schema_failures(value[key], child_schema, f"{location}.{key}"))
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            failures.extend(_schema_failures(item, schema["items"], f"{location}[{index}]"))
    if isinstance(value, str):
        if "minLength" in schema and len(value) < int(schema["minLength"]):
            failures.append(AssertionFailure(kind="schema", message=f"{location}: shorter than minLength"))
        if "maxLength" in schema and len(value) > int(schema["maxLength"]):
            failures.append(AssertionFailure(kind="schema", message=f"{location}: longer than maxLength"))
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            failures.append(AssertionFailure(kind="schema", message=f"{location}: below minimum {schema['minimum']}"))
        if "maximum" in schema and value > schema["maximum"]:
            failures.append(AssertionFailure(kind="schema", message=f"{location}: above maximum {schema['maximum']}"))
    for child_schema in schema.get("allOf", []):
        if isinstance(child_schema, dict):
            failures.extend(_schema_failures(value, child_schema, location))
    return failures


def evaluate_response(case: TestCase, response: httpx.Response, elapsed_ms: float) -> tuple[list[AssertionFailure], Any]:
    """Compare one observed response with a reviewed test case."""

    failures: list[AssertionFailure] = []
    if response.status_code not in case.expected_status_codes:
        expected = "/".join(str(code) for code in case.expected_status_codes)
        failures.append(
            AssertionFailure(kind="status", message=f"expected status {expected}, got {response.status_code}")
        )
    if elapsed_ms > case.max_response_time_ms:
        failures.append(
            AssertionFailure(
                kind="latency",
                message=f"response took {elapsed_ms:.1f} ms, limit is {case.max_response_time_ms:.1f} ms",
            )
        )

    response_body: Any = None
    if response.content:
        try:
            response_body = response.json()
        except ValueError:
            response_body = response.text[:4000]
    if case.expect_empty_body and response.content:
        failures.append(AssertionFailure(kind="body", message="expected an empty response body"))
    if case.expected_schema is not None:
        if response_body is None:
            failures.append(AssertionFailure(kind="schema", message="$: expected JSON body, got empty body"))
        elif isinstance(response_body, (dict, list, str, int, float, bool)):
            failures.extend(_schema_failures(response_body, case.expected_schema))
    return failures, response_body
