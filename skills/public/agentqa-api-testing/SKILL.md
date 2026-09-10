---
name: agentqa-api-testing
description: >-
  Test a local REST API from an OpenAPI 3.x JSON/YAML document. Use when the
  user asks to create API test cases, review an API test plan, run contract
  tests, discover response-schema or status-code defects, or generate an
  AgentQA report, compare before/after reports, or identify fixed, newly failing,
  and unresolved cases in a regression run. Network access is restricted to
  allowlisted local targets.
allowed-tools:
  - agentqa_create_test_plan
  - agentqa_execute_test_plan
  - agentqa_compare_test_reports
  - ask_clarification
  - read_file
---

# AgentQA API Testing

You are operating AgentQA, an OpenAPI-driven API contract testing workflow.
Follow the phases in order. Never skip the approval gate.

## Phase 1: Obtain the OpenAPI document

- For the built-in validation target, use these defaults:
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

`agentqa_execute_test_plan` deterministically saves and presents these outputs
in the same tool call:

- `agentqa/runs/<run_id>/agentqa-report.md` from `markdown_report`;
- `agentqa/runs/<run_id>/agentqa-report.json` from `report`;
- `agentqa/runs/<run_id>/agentqa-plan.json` containing the exact reviewed plan.

All paths are relative to `/mnt/user-data/outputs/`. Each run has immutable
archive paths. The root `agentqa-report.md` and `agentqa-report.json` are latest
aliases only; do not use these aliases to identify an earlier baseline.

The tool returns the actual virtual paths in `artifacts`; do not call `write_file` or
`present_files`, and do not ask the user to request downloads in another turn.
Verify that the artifact paths are present in the tool result before claiming
that the reports are downloadable.

## Regression comparison

1. Identify the baseline by its run ID and archived JSON report. Read uploaded
   or archived reports using `read_file`; retain complete JSON without rewriting
   counts, fingerprints, snapshots, or failure evidence.
2. For a new post-fix run, reuse the archived `agentqa-plan.json` (also available
   as `report.plan`). Show the exact plan and target and obtain explicit execution
   approval if the user has not already approved that exact rerun. Then use
   `agentqa_execute_test_plan`. Avoid regenerating expectations from a changed
   specification when the intent is to verify the original contract.
3. Call `agentqa_compare_test_reports` with `baseline_report_json` and
   `current_report_json`. Each input accepts a report object serialized as JSON
   or the full execution tool JSON containing `report`. This step only compares
   recorded results and needs no HTTP execution approval.
4. Explain the deterministic categories: failure → pass is fixed; pass → failure
   is a new defect; failure → failure is unresolved; pass → pass is persistent pass.
   These are case counts, not inferred independent root causes. Show evidence
   changes within unresolved cases without asserting that the root cause is the same.
5. Separately disclose added/missing cases, changed test conditions, network
   execution errors, and any returned warnings. Never call an untested case fixed.
   New-version reports match request/assertion fingerprints independent of case
   numbering. Legacy reports require identical plan IDs and unambiguous case IDs;
   different APIs/targets are rejected. Do not bypass validation by editing JSON.
6. Present the returned `agentqa/comparisons/<comparison_id>/agentqa-regression.md`
   and `.json` artifacts immediately. If both reports already exist, go directly
   to comparison without rerunning tests or asking for execution approval.

## Built-in validation target

The validation API has five operations and three intentional defects. A
correct run should produce five results: two passed and three failed. The
failures should expose a response type mismatch, an invalid-login status-code
mismatch, and a delete status/body mismatch.
