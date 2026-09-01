from __future__ import annotations

from agentqa.case_generator import create_test_plan
from agentqa.openapi_parser import parse_openapi_document
from agentqa_demo.app import app


def test_rule_generator_covers_every_demo_operation() -> None:
    specification = parse_openapi_document(app.openapi())
    plan = create_test_plan(specification, "http://agentqa-demo-api:8000")

    assert len(plan.cases) == 5
    assert {(case.method, case.path_template) for case in plan.cases} == {
        ("GET", "/users/{user_id}"),
        ("POST", "/users"),
        ("POST", "/login"),
        ("GET", "/orders"),
        ("DELETE", "/users/{user_id}"),
    }


def test_rule_generator_builds_cases_that_expose_seeded_contract_defects() -> None:
    specification = parse_openapi_document(app.openapi())
    plan = create_test_plan(specification, "http://agentqa-demo-api:8000")

    get_user = next(case for case in plan.cases if case.method == "GET" and case.path_template == "/users/{user_id}")
    invalid_login = next(case for case in plan.cases if case.path_template == "/login")
    delete_user = next(case for case in plan.cases if case.method == "DELETE")

    assert get_user.expected_status_codes == [200]
    assert get_user.expected_schema["properties"]["age"]["type"] == "integer"
    assert invalid_login.expected_status_codes == [401]
    assert invalid_login.json_body == {"username": "invalid-user", "password": "invalid-password"}
    assert delete_user.expected_status_codes == [204]
    assert delete_user.expect_empty_body is True


def test_plan_identifier_is_deterministic() -> None:
    specification = parse_openapi_document(app.openapi())

    first = create_test_plan(specification, "http://agentqa-demo-api:8000")
    second = create_test_plan(specification, "http://agentqa-demo-api:8000")

    assert first.id == second.id
