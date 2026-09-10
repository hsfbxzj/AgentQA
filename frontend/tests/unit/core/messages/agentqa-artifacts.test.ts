import type { Message } from "@langchain/langgraph-sdk";
import { describe, expect, test } from "@rstest/core";

import {
  extractPresentFilesFromMessage,
  getMessageGroups,
} from "@/core/messages/utils";

function call(id: string, name = "agentqa_execute_test_plan"): Message {
  return {
    id: `ai-${id}`,
    type: "ai",
    content: "",
    tool_calls: [{ id, name, args: {} }],
  } as Message;
}

function result(id: string, payload: unknown): Message {
  return {
    id: `result-${id}`,
    type: "tool",
    tool_call_id: id,
    content: JSON.stringify(payload),
  } as Message;
}

describe("AgentQA report artifacts", () => {
  test("preserves each run's files and comparison files in separate message groups", () => {
    const paths = [
      "runs/first/agentqa-report.md",
      "runs/second/agentqa-report.md",
      "comparisons/diff/agentqa-regression.md",
    ].map((path) => `/mnt/user-data/outputs/agentqa/${path}`);
    const messages = paths.flatMap((path, index) => [
      call(
        String(index),
        index === 2 ? "agentqa_compare_test_reports" : undefined,
      ),
      result(String(index), { status: "completed", artifacts: [path] }),
    ]);
    const groups = getMessageGroups(messages);
    expect(groups.map((group) => group.type)).toEqual(
      Array(3).fill("assistant:present-files"),
    );
    expect(
      groups.map((group) =>
        extractPresentFilesFromMessage(group.messages[0]!, group.messages),
      ),
    ).toEqual(paths.map((path) => [path]));
  });

  test("only uses a completed result with the matching tool call ID", () => {
    const message = call("first");
    const path = "/mnt/user-data/outputs/agentqa-report.md";
    expect(extractPresentFilesFromMessage(message)).toEqual([]);
    expect(
      extractPresentFilesFromMessage(message, [
        result("other", { status: "completed", artifacts: [path] }),
      ]),
    ).toEqual([]);
    expect(
      extractPresentFilesFromMessage(message, [
        result("first", { status: "error", artifacts: [path] }),
      ]),
    ).toEqual([]);
    const broken = {
      ...result("first", {}),
      content: "invalid JSON",
    } as Message;
    expect(extractPresentFilesFromMessage(message, [broken])).toEqual([]);
    expect(
      extractPresentFilesFromMessage(message, [result("first", null)]),
    ).toEqual([]);
  });

  test("accepts legacy explicit artifact paths and filters invalid paths", () => {
    const path = "/mnt/user-data/outputs/agentqa-report.json";
    const response = result("old", {
      status: "completed",
      artifacts: [
        path,
        path,
        42,
        "/outside.json",
        "/mnt/user-data/outputs/../private.json",
      ],
    });
    expect(extractPresentFilesFromMessage(call("old"), [response])).toEqual([
      path,
    ]);
  });

  test("keeps present_files behavior", () => {
    const message = {
      type: "ai",
      content: "",
      tool_calls: [
        {
          name: "present_files",
          args: { filepaths: ["/mnt/user-data/outputs/file.txt"] },
        },
      ],
    } as Message;
    expect(extractPresentFilesFromMessage(message)).toEqual([
      "/mnt/user-data/outputs/file.txt",
    ]);
  });
});
