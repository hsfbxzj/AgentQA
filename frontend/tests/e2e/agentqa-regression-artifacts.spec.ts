import { expect, test } from "@playwright/test";

import { mockLangGraphAPI } from "./utils/mock-api";

test("AgentQA history keeps baseline, rerun, and regression download paths distinct", async ({
  page,
}) => {
  const threadId = "00000000-0000-0000-0000-000000009901";
  const paths = [
    "/mnt/user-data/outputs/agentqa/runs/run-before/agentqa-report.md",
    "/mnt/user-data/outputs/agentqa/runs/run-after/agentqa-report.md",
    "/mnt/user-data/outputs/agentqa/comparisons/comparison-demo/agentqa-regression.md",
  ];
  const messages = [
    {
      type: "human",
      id: "human",
      content: "Compare the before and after runs",
    },
    ...paths.flatMap((path, index) => {
      const name =
        index === 2
          ? "agentqa_compare_test_reports"
          : "agentqa_execute_test_plan";
      return [
        {
          type: "ai",
          id: `ai-${index}`,
          content: "",
          tool_calls: [{ id: `call-${index}`, name, args: {} }],
        },
        {
          type: "tool",
          id: `tool-${index}`,
          name,
          tool_call_id: `call-${index}`,
          content: JSON.stringify({ status: "completed", artifacts: [path] }),
        },
      ];
    }),
    {
      type: "ai",
      id: "complete",
      content: "已修复 1，新增缺陷 1，仍未解决 2，持续通过 1。",
    },
  ];
  mockLangGraphAPI(page, {
    threads: [
      {
        thread_id: threadId,
        title: "AgentQA regression",
        messages,
        artifacts: paths,
      },
    ],
  });
  await page.goto(`/workspace/chats/${threadId}`);
  for (const path of paths) {
    const link = page
      .locator("a[href]")
      .filter({ has: page.locator("svg.lucide-download") });
    await expect
      .poll(async () =>
        (
          await link.evaluateAll((links) =>
            links.map((element) => element.getAttribute("href")),
          )
        ).some((href) => decodeURIComponent(href ?? "").includes(path)),
      )
      .toBe(true);
  }
  await expect(
    page.getByText("已修复 1，新增缺陷 1，仍未解决 2，持续通过 1。", {
      exact: true,
    }),
  ).toBeVisible();
});
