from __future__ import annotations

import pytest

from agentqa.openapi_parser import OpenAPIParseError, parse_openapi_document
from agentqa_demo.app import app


def test_parser_extracts_all_demo_operations() -> None:
    parsed = parse_openapi_document(app.openapi())

    assert parsed.title == "AgentQA Demo API"
    assert parsed.openapi_version.startswith("3.1")
    assert len(parsed.operations) == 5
    assert {(operation.method, operation.path) for operation in parsed.operations} == {
        ("GET", "/users/{user_id}"),
        ("POST", "/users"),
        ("POST", "/login"),
        ("GET", "/orders"),
        ("DELETE", "/users/{user_id}"),
    }


def test_parser_resolves_local_component_references() -> None:
    parsed = parse_openapi_document(app.openapi())
    get_user = next(operation for operation in parsed.operations if operation.method == "GET" and operation.path == "/users/{user_id}")

    success_response = next(response for response in get_user.responses if response.status_code == "200")
    assert success_response.schema_data["type"] == "object"
    assert success_response.schema_data["properties"]["age"]["type"] == "integer"


@pytest.mark.parametrize(
    "document, message",
    [
        ({"info": {"title": "missing version"}, "paths": {}}, "openapi"),
        ({"openapi": "2.0", "info": {"title": "old"}, "paths": {}}, "3.x"),
        ({"openapi": "3.1.0", "info": {"title": "bad"}, "paths": []}, "paths"),
    ],
)
def test_parser_returns_readable_errors(document: dict, message: str) -> None:
    with pytest.raises(OpenAPIParseError, match=message):
        parse_openapi_document(document)
