from __future__ import annotations

import pytest

from agentqa.security import UnsafeTargetError, validate_target_url


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8003",
        "http://127.0.0.1:8003/openapi.json",
        "http://agentqa-demo-api:8000",
    ],
)
def test_local_demo_targets_are_allowed(url: str) -> None:
    assert validate_target_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://169.254.169.254/latest/meta-data",
        "http://example.com",
        "http://user:password@localhost:8003",
    ],
)
def test_untrusted_targets_are_rejected(url: str) -> None:
    with pytest.raises(UnsafeTargetError):
        validate_target_url(url)
