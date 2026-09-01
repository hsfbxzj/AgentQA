"""FastAPI application that acts as AgentQA's deterministic test target.

The service intentionally contains three contract defects. They are teaching
fixtures, not accidental production bugs: AgentQA must eventually discover all
three and include the evidence in its report.
"""

from typing import Annotated

from fastapi import FastAPI, Path, Query
from fastapi.responses import JSONResponse

from agentqa_demo.models import (
    ErrorResponse,
    LoginRequest,
    OrderResponse,
    TokenResponse,
    UserCreate,
    UserResponse,
)

INTENTIONAL_DEFECTS = {
    "DEMO-BUG-001": "GET /users/{user_id} returns age as a string instead of the documented integer",
    "DEMO-BUG-002": "POST /login returns HTTP 200 instead of 401 for invalid credentials",
    "DEMO-BUG-003": "DELETE /users/{user_id} returns HTTP 200 instead of the documented 204",
}

USERS = {
    1: {"id": 1, "name": "Alice", "age": 29},
    2: {"id": 2, "name": "Bob", "age": 35},
}

ORDERS = (
    {"id": 1, "user_id": 1, "amount": 99.0, "status": "paid"},
    {"id": 2, "user_id": 2, "amount": 25.5, "status": "pending"},
    {"id": 3, "user_id": 1, "amount": 12.0, "status": "cancelled"},
)


app = FastAPI(
    title="AgentQA Demo API",
    version="0.1.0",
    description=(
        "A deterministic local API used to teach and demonstrate AgentQA. "
        "It intentionally contains three known contract defects."
    ),
)


@app.get("/health", include_in_schema=False)
def health() -> dict[str, str | int]:
    """Return service health without adding an extra business operation."""
    return {
        "status": "ok",
        "service": "agentqa-demo-api",
        "seeded_defects": len(INTENTIONAL_DEFECTS),
    }


@app.get(
    "/users/{user_id}",
    response_model=UserResponse,
    responses={404: {"model": ErrorResponse, "description": "User not found"}},
    tags=["users"],
    summary="Get a user",
)
def get_user(user_id: Annotated[int, Path(ge=1)]) -> UserResponse | JSONResponse:
    """Return one user, with DEMO-BUG-001 deliberately preserved."""
    user = USERS.get(user_id)
    if user is None:
        return JSONResponse(status_code=404, content={"detail": "User not found"})

    # DEMO-BUG-001: returning a Response object bypasses FastAPI response-model
    # validation, allowing the documented integer field to become a string.
    defective_user = {**user, "age": str(user["age"])}
    return JSONResponse(status_code=200, content=defective_user)


@app.post(
    "/users",
    response_model=UserResponse,
    status_code=201,
    tags=["users"],
    summary="Create a user",
)
def create_user(payload: UserCreate) -> UserResponse:
    """Create a deterministic user response for positive and boundary tests."""
    return UserResponse(id=3, name=payload.name, age=payload.age)


@app.post(
    "/login",
    response_model=TokenResponse,
    responses={401: {"model": ErrorResponse, "description": "Invalid credentials"}},
    tags=["authentication"],
    summary="Log in",
)
def login(payload: LoginRequest) -> TokenResponse | JSONResponse:
    """Return a token or expose DEMO-BUG-002 for invalid credentials."""
    if payload.username == "demo" and payload.password == "agentqa":
        return TokenResponse(access_token="demo-token")

    # DEMO-BUG-002: the contract documents 401, but the implementation returns
    # a successful HTTP status with an error-shaped body.
    return JSONResponse(status_code=200, content={"detail": "Invalid credentials"})


@app.get(
    "/orders",
    response_model=list[OrderResponse],
    tags=["orders"],
    summary="List orders",
)
def list_orders(limit: Annotated[int, Query(ge=1, le=100)] = 20) -> list[OrderResponse]:
    """Return a bounded, deterministic order list."""
    return [OrderResponse(**order) for order in ORDERS[:limit]]


@app.delete(
    "/users/{user_id}",
    status_code=204,
    responses={404: {"model": ErrorResponse, "description": "User not found"}},
    tags=["users"],
    summary="Delete a user",
)
def delete_user(user_id: Annotated[int, Path(ge=1)]) -> JSONResponse:
    """Pretend to delete a user while exposing DEMO-BUG-003."""
    if user_id not in USERS:
        return JSONResponse(status_code=404, content={"detail": "User not found"})

    # DEMO-BUG-003: the OpenAPI contract says 204 No Content, but the service
    # returns 200 and an unnecessary response body.
    return JSONResponse(status_code=200, content={"deleted": True, "id": user_id})
