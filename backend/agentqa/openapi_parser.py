"""Read OpenAPI 3.x JSON/YAML and normalize the parts AgentQA needs."""

from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

from agentqa.models import ApiOperation, ApiParameter, ApiResponse, ParsedOpenAPI

HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options", "trace")


class OpenAPIParseError(ValueError):
    """Raised when an input cannot be interpreted as supported OpenAPI 3.x."""


def _load_document(source: Mapping[str, Any] | str | bytes | Path) -> dict[str, Any]:
    if isinstance(source, Mapping):
        return deepcopy(dict(source))
    if isinstance(source, bytes):
        source = source.decode("utf-8")
    if isinstance(source, Path):
        try:
            text = source.read_text(encoding="utf-8")
        except OSError as exc:
            raise OpenAPIParseError(f"Unable to read OpenAPI file: {exc}") from exc
    elif isinstance(source, str):
        possible_path = Path(source)
        try:
            is_file = "\n" not in source and possible_path.is_file()
        except OSError:
            is_file = False
        if is_file:
            try:
                text = possible_path.read_text(encoding="utf-8")
            except OSError as exc:
                raise OpenAPIParseError(f"Unable to read OpenAPI file: {exc}") from exc
        else:
            text = source
    else:
        raise OpenAPIParseError("OpenAPI source must be a mapping, JSON/YAML text, bytes, or a local path")

    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        try:
            loaded = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise OpenAPIParseError(f"Invalid OpenAPI JSON/YAML: {exc}") from exc
    if not isinstance(loaded, dict):
        raise OpenAPIParseError("OpenAPI document root must be an object")
    return loaded


def _resolve_json_pointer(document: dict[str, Any], reference: str) -> Any:
    if not reference.startswith("#/"):
        raise OpenAPIParseError(f"Only local OpenAPI references are supported in the MVP: {reference}")
    current: Any = document
    for raw_part in reference[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or part not in current:
            raise OpenAPIParseError(f"OpenAPI reference does not exist: {reference}")
        current = current[part]
    return current


def _resolve_node(node: Any, document: dict[str, Any], seen: frozenset[str] = frozenset()) -> Any:
    if isinstance(node, list):
        return [_resolve_node(item, document, seen) for item in node]
    if not isinstance(node, dict):
        return deepcopy(node)
    if "$ref" in node:
        reference = node["$ref"]
        if not isinstance(reference, str):
            raise OpenAPIParseError("OpenAPI $ref must be a string")
        if reference in seen:
            return {"$ref": reference}
        resolved = _resolve_node(_resolve_json_pointer(document, reference), document, seen | {reference})
        if not isinstance(resolved, dict):
            return resolved
        siblings = {key: value for key, value in node.items() if key != "$ref"}
        return {**resolved, **_resolve_node(siblings, document, seen)}
    return {key: _resolve_node(value, document, seen) for key, value in node.items()}


def _json_schema_from_content(content: Any, document: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(content, dict) or not content:
        return None
    media = content.get("application/json") or next(iter(content.values()))
    if not isinstance(media, dict) or not isinstance(media.get("schema"), dict):
        return None
    return _resolve_node(media["schema"], document)


def _parse_parameter(raw: Any, document: dict[str, Any]) -> ApiParameter:
    parameter = _resolve_node(raw, document)
    if not isinstance(parameter, dict):
        raise OpenAPIParseError("Each OpenAPI parameter must be an object")
    location = parameter.get("in")
    if location not in {"path", "query", "header", "cookie"}:
        raise OpenAPIParseError(f"Unsupported or missing parameter location: {location}")
    name = parameter.get("name")
    if not isinstance(name, str) or not name:
        raise OpenAPIParseError("Each OpenAPI parameter must have a non-empty name")
    schema_data = parameter.get("schema") if isinstance(parameter.get("schema"), dict) else {}
    return ApiParameter(
        name=name,
        location=location,
        required=location == "path" or bool(parameter.get("required")),
        schema_data=_resolve_node(schema_data, document),
        description=parameter.get("description"),
    )


def _merge_parameters(path_parameters: Any, operation_parameters: Any, document: dict[str, Any]) -> list[ApiParameter]:
    merged: dict[tuple[str, str], ApiParameter] = {}
    for raw in list(path_parameters or []) + list(operation_parameters or []):
        parameter = _parse_parameter(raw, document)
        merged[(parameter.name, parameter.location)] = parameter
    return list(merged.values())


def _parse_responses(raw_responses: Any, document: dict[str, Any]) -> list[ApiResponse]:
    if not isinstance(raw_responses, dict) or not raw_responses:
        raise OpenAPIParseError("Each operation must document at least one response")
    responses: list[ApiResponse] = []
    for status_code, raw_response in raw_responses.items():
        response = _resolve_node(raw_response, document)
        if not isinstance(response, dict):
            raise OpenAPIParseError(f"Response {status_code} must be an object")
        responses.append(
            ApiResponse(
                status_code=str(status_code),
                description=str(response.get("description", "")),
                schema_data=_json_schema_from_content(response.get("content"), document),
            )
        )
    return responses


def _security_names(raw_security: Any) -> list[str]:
    if not isinstance(raw_security, list):
        return []
    return list(dict.fromkeys(name for requirement in raw_security if isinstance(requirement, dict) for name in requirement))


def parse_openapi_document(source: Mapping[str, Any] | str | bytes | Path) -> ParsedOpenAPI:
    """Parse OpenAPI 3.x into a small, stable structure used by AgentQA."""

    document = _load_document(source)
    openapi_version = document.get("openapi")
    if not isinstance(openapi_version, str):
        raise OpenAPIParseError("Missing required openapi version field")
    if not openapi_version.startswith("3."):
        raise OpenAPIParseError(f"Only OpenAPI 3.x is supported, got {openapi_version}")
    paths = document.get("paths")
    if not isinstance(paths, dict):
        raise OpenAPIParseError("OpenAPI paths must be an object")
    info = document.get("info") if isinstance(document.get("info"), dict) else {}

    operations: list[ApiOperation] = []
    for path, raw_path_item in paths.items():
        path_item = _resolve_node(raw_path_item, document)
        if not isinstance(path, str) or not path.startswith("/") or not isinstance(path_item, dict):
            raise OpenAPIParseError("Every OpenAPI path must start with '/' and map to an object")
        for method in HTTP_METHODS:
            raw_operation = path_item.get(method)
            if not isinstance(raw_operation, dict):
                continue
            request_body = _resolve_node(raw_operation.get("requestBody", {}), document)
            request_schema = None
            request_required = False
            if isinstance(request_body, dict) and request_body:
                request_schema = _json_schema_from_content(request_body.get("content"), document)
                request_required = bool(request_body.get("required"))
            operation_id = raw_operation.get("operationId") or f"{method}_{path.strip('/').replace('/', '_') or 'root'}"
            operations.append(
                ApiOperation(
                    method=method.upper(),
                    path=path,
                    operation_id=str(operation_id),
                    summary=str(raw_operation.get("summary", "")),
                    tags=[str(tag) for tag in raw_operation.get("tags", [])],
                    parameters=_merge_parameters(path_item.get("parameters"), raw_operation.get("parameters"), document),
                    request_schema=request_schema,
                    request_required=request_required,
                    responses=_parse_responses(raw_operation.get("responses"), document),
                    security_schemes=_security_names(raw_operation.get("security", document.get("security"))),
                )
            )

    servers = [server["url"] for server in document.get("servers", []) if isinstance(server, dict) and isinstance(server.get("url"), str)]
    return ParsedOpenAPI(
        title=str(info.get("title", "Untitled API")),
        api_version=str(info.get("version", "")),
        openapi_version=openapi_version,
        servers=servers,
        operations=operations,
    )
