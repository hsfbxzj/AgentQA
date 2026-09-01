"""Smoke tests proving that the AgentQA demo target is usable."""

from fastapi.testclient import TestClient

from agentqa_demo.app import INTENTIONAL_DEFECTS, app

client = TestClient(app)


def test_health_endpoint_is_available_but_hidden_from_openapi() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "agentqa-demo-api",
        "seeded_defects": 3,
    }
    assert "/health" not in client.get("/openapi.json").json()["paths"]


def test_openapi_exposes_five_business_operations() -> None:
    document = client.get("/openapi.json").json()
    methods = {"get", "post", "put", "patch", "delete", "options", "head", "trace"}
    operation_count = sum(
        1
        for path_item in document["paths"].values()
        for method in path_item
        if method in methods
    )

    assert document["openapi"].startswith("3.")
    assert document["info"]["title"] == "AgentQA Demo API"
    assert operation_count == 5


def test_create_user_happy_path() -> None:
    response = client.post("/users", json={"name": "小明", "age": 24})

    assert response.status_code == 201
    assert response.json() == {"id": 3, "name": "小明", "age": 24}


def test_create_user_rejects_out_of_range_age() -> None:
    response = client.post("/users", json={"name": "小明", "age": 121})

    assert response.status_code == 422


def test_orders_rejects_limit_below_boundary() -> None:
    response = client.get("/orders", params={"limit": 0})

    assert response.status_code == 422


def test_demo_target_declares_exactly_three_seeded_defects() -> None:
    assert set(INTENTIONAL_DEFECTS) == {
        "DEMO-BUG-001",
        "DEMO-BUG-002",
        "DEMO-BUG-003",
    }
