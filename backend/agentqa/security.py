"""Network safety boundary for AgentQA's HTTP-capable tools."""

from __future__ import annotations

from urllib.parse import urlsplit

DEFAULT_ALLOWED_HOSTS = frozenset({"localhost", "127.0.0.1", "agentqa-demo-api"})


class UnsafeTargetError(ValueError):
    """Raised when a target falls outside the local MVP allowlist."""


def validate_target_url(url: str, allowed_hosts: frozenset[str] = DEFAULT_ALLOWED_HOSTS) -> str:
    """Allow only explicit HTTP(S) targets from the AgentQA local allowlist."""

    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeTargetError("AgentQA only permits http:// or https:// targets")
    if not parsed.hostname or parsed.hostname.lower() not in allowed_hosts:
        raise UnsafeTargetError(f"Target host is not in the AgentQA allowlist: {parsed.hostname or '<missing>'}")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeTargetError("Credentials must not be embedded in a target URL")
    if parsed.fragment:
        raise UnsafeTargetError("Target URLs must not contain fragments")
    return url


def validate_request_path(path: str) -> str:
    """Prevent an OpenAPI path from overriding the approved host."""

    if not path.startswith("/") or path.startswith("//") or "://" in path or "\\" in path:
        raise UnsafeTargetError(f"Unsafe OpenAPI request path: {path}")
    return path
