"""Contract tests documenting the demo target's three intentional defects.

These tests are strict xfails: the suite stays green while each known defect
is still detectable, but an unexpected fix becomes an XPASS and forces us to
update the teaching fixture deliberately.
"""

import pytest
from fastapi.testclient import TestClient

from agentqa_demo.app import app

client = TestClient(app)


@pytest.mark.xfail(strict=True, reason="DEMO-BUG-001: age violates the documented integer response schema")
def test_get_user_returns_integer_age() -> None:
    response = client.get("/users/1")

    assert response.status_code == 200
    assert isinstance(response.json()["age"], int)


@pytest.mark.xfail(strict=True, reason="DEMO-BUG-002: invalid credentials incorrectly return HTTP 200")
def test_invalid_login_returns_401() -> None:
    response = client.post(
        "/login",
        json={"username": "wrong-user", "password": "wrong-password"},
    )

    assert response.status_code == 401


@pytest.mark.xfail(strict=True, reason="DEMO-BUG-003: delete incorrectly returns HTTP 200 instead of 204")
def test_delete_user_returns_204() -> None:
    response = client.delete("/users/1")

    assert response.status_code == 204
