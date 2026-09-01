import { AlertTriangleIcon, ClipboardCheckIcon } from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { AgentQATestPlan } from "@/core/messages/utils";

const MUTATING_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

const RULE_LABELS: Record<string, string> = {
  "documented-success": "验证文档声明的成功响应",
  "documented-auth-rejection": "验证文档声明的认证失败响应",
  "documented-response": "验证文档声明的响应",
  "documented-default-response": "验证文档默认响应",
};

export function AgentQAPlanCard({ plan }: { plan: AgentQATestPlan }) {
  const mutatingCases = plan.cases.filter((testCase) =>
    MUTATING_METHODS.has(testCase.method.toUpperCase()),
  );

  return (
    <Card className="gap-4 py-5">
      <CardHeader className="gap-2 px-5">
        <CardTitle className="flex items-center gap-2">
          <ClipboardCheckIcon className="size-5" />
          AgentQA 测试计划
        </CardTitle>
        <CardDescription className="space-y-1">
          <div>
            计划 ID：<code>{plan.id}</code>
          </div>
          <div>
            测试目标：<code>{plan.base_url}</code>
          </div>
          <div>
            API：{plan.api_title} · 共 {plan.cases.length} 个测试用例
          </div>
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4 px-5">
        <div className="overflow-x-auto rounded-lg border">
          <table className="w-full min-w-3xl text-left text-sm">
            <thead className="bg-muted/60 text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">#</th>
                <th className="px-3 py-2 font-medium">方法</th>
                <th className="px-3 py-2 font-medium">路径</th>
                <th className="px-3 py-2 font-medium">测试规则</th>
                <th className="px-3 py-2 font-medium">预期状态码</th>
              </tr>
            </thead>
            <tbody>
              {plan.cases.map((testCase, index) => (
                <tr key={testCase.id} className="border-t">
                  <td className="px-3 py-2">{index + 1}</td>
                  <td className="px-3 py-2 font-mono font-medium">
                    {testCase.method}
                  </td>
                  <td className="px-3 py-2 font-mono">
                    {testCase.path_template}
                  </td>
                  <td className="px-3 py-2">
                    {RULE_LABELS[testCase.rule] ?? testCase.rule}
                  </td>
                  <td className="px-3 py-2 font-mono">
                    {testCase.expected_status_codes.join(", ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {mutatingCases.length > 0 && (
          <div className="flex gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm">
            <AlertTriangleIcon className="mt-0.5 size-4 shrink-0 text-amber-600" />
            <span>
              计划包含 {mutatingCases.length} 个可能修改数据的请求（
              {mutatingCases.map((testCase) => testCase.method).join("、")}）。
              确认后才会执行。
            </span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
