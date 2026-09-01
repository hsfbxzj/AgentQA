"""Request and response contracts exposed by the AgentQA demo API."""

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    """Payload accepted when creating a user."""

    name: str = Field(min_length=1, max_length=50, description="Display name")
    age: int = Field(ge=1, le=120, description="Age in completed years")


class UserResponse(BaseModel):
    """Documented user response."""

    id: int = Field(ge=1)
    name: str
    age: int = Field(ge=1, le=120)


class LoginRequest(BaseModel):
    """Credentials accepted by the demo login endpoint."""

    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    """Successful login response."""

    access_token: str
    token_type: str = "bearer"


class ErrorResponse(BaseModel):
    """Standard error response documented by the demo service."""

    detail: str


class OrderResponse(BaseModel):
    """Order returned by the list endpoint."""

    id: int = Field(ge=1)
    user_id: int = Field(ge=1)
    amount: float = Field(ge=0)
    status: str
