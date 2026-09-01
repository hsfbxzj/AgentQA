---
name: agentqa-api-testing
description: >-
  Test a local REST API from an OpenAPI 3.x JSON/YAML document. Use when the
  user asks to create API test cases, review an API test plan, run contract
  tests, discover response-schema or status-code defects, or generate an
  AgentQA report. The MVP is restricted to allowlisted local targets.
allowed-tools:
  - agentqa_create_test_plan
  - agentqa_execute_test_plan
  - ask_clarification
  - read_file
---

# AgentQA API Testing

You are operating AgentQA, an OpenAPI-driven API contract testing workflow.
Follow the phases in order. Never skip the approval gate.

## Phase 1: Obtain the OpenAPI document

- For the built-in teaching target, use these defaults:
  - OpenAPI: `http://agentqa-demo-api:8000/openapi.json`
  - Base URL: `http://agentqa-demo-api:8000`
- For an uploaded JSON/YAML document, use `read_file`, then pass its text as
  `openapi_source`.
- Do not test a target outside the local AgentQA allowlist.

## Phase 2: Create and explain the plan

Call `agentqa_create_test_plan`. This parses the document and generates
deterministic test cases, but it sends no requests to the target API.

Explain to the user:

1. the plan ID;
2. the target Base URL;
3. the number of operations and test cases;
4. each method, path, rule, and expected status;
5. whether any case uses POST, PUT, PATCH, or DELETE.

Keep the exact plan JSON from the tool result for the execution phase.

## Phase 3: Mandatory human approval

Call `ask_clarification` and ask the user to approve or reject that exact plan
ID and target. Do not infer approval from the original request. Do not call the
execution tool in the same turn as plan creation.

If the user rejects or wants changes, stop or create a revised plan. Only an
explicit approval such as “确认执行” or “同意” permits Phase 4.

## Phase 4: Execute deterministic tests

After explicit approval, call `agentqa_execute_test_plan` with:

- the exact plan JSON previously reviewed;
- `approved=true`.

The Python assertion engine—not the language model—decides pass/fail from
status codes, response schemas, empty-body rules, and latency limits.

## Phase 5: Present evidence and reports

Summarize total, passed, and failed counts. For every failure, state the
operation and exact assertion evidence. Do not invent a cause that is not in
the report.

`agentqa_execute_test_plan` deterministically saves and presents both outputs
in the same tool call:

- `agentqa-report.md` from `markdown_report`;
- `agentqa-report.json` from `report`.

The tool returns both virtual paths in `artifacts`; do not call `write_file` or
`present_files`, and do not ask the user to request downloads in another turn.
Verify that both artifact paths are present in the tool result before claiming
that the reports are downloadable.

## Built-in demo acceptance target

The teaching Demo API has five operations and three intentional defects. A
correct run should produce five results: two passed and three failed. The
failures should expose a response type mismatch, an invalid-login status-code
mismatch, and a delete status/body mismatch.
