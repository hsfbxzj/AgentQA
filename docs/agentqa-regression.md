# AgentQA 回归测试

AgentQA 可以比较修复前后的两份执行报告。分类由 Python 完成，LLM 负责解释和调度。统计单位是**测试用例**，不是推测的独立缺陷根因。

## 使用流程

1. 生成并确认测试计划，执行一次作为基线。保存工具返回的运行 ID 和报告路径。
2. 修复被测 API 后，读取基线的 `agentqa-plan.json`，确认相同计划和目标的复测，再执行。
3. 调用 `agentqa_compare_test_reports`，传入 `baseline_report_json` 和 `current_report_json`。可以传报告 JSON，也可以传包含 `report` 的完整执行工具结果。
4. 读取同次工具调用返回的 JSON/Markdown 对比报告。已有两份报告时可直接比较，不会重新发送 HTTP 请求。

对 Agent 的示例请求：

```text
/agentqa-api-testing 使用运行 <基线运行ID> 的原始计划复测修复后的 API，先展示计划供确认，然后对比两次结果。
```

```text
/agentqa-api-testing 对比这两份已上传的 AgentQA JSON 报告，第一份是修复前，第二份是修复后。
```

## 判定原理

新报告包含版本号、运行 ID、完整计划快照，以及每条结果的条件指纹。指纹使用 SHA-256，输入包括方法、路径、请求参数、请求体、规则、期望状态码、响应 Schema、空响应体要求和耗时阈值；排除展示名称与顺序编号。重排接口不会改变同一测试条件的匹配身份。

| 修复前 | 修复后 | 分类 |
|---|---|---|
| 失败 | 通过 | 已修复 |
| 通过 | 失败 | 新增缺陷 |
| 失败 | 失败 | 仍未解决，同时标记失败证据是否变化 |
| 通过 | 通过 | 持续通过 |

没有出现在本次计划中的旧用例标记为缺失；新增测试单列，不声称是新增缺陷。同一接口/规则剩余各一个用例且条件不同时，标记为测试条件变化；多个候选匹配有歧义时保留为新增/缺失并给出提示。任一侧发生网络失败的匹配用例单列为执行异常，不计入四类可比较结果。

比较前会校验统计总数、通过标记与失败证据的一致性、重复用例 ID、重复指纹、计划快照与实际结果的对应关系。必须是相同 API 标题和 Base URL（忽略末尾 `/`）；当前不支持自动推断不同地址属于同一环境。时间戳用于追溯，由调用者明确指定基线和当前报告。

未携带新版元数据的旧报告仍可读取；只允许计划 ID 一致并且用例 ID、方法、路径、名称无歧义时比较，报告会明确提示无法独立验证旧测试条件。指纹是匹配标识，不是防篡改签名，也无法证明外部测试数据和部署环境相同。

## 文件留存与界面

执行输出（相对于 `/mnt/user-data/outputs/`）：

```text
agentqa/runs/<run_id>/agentqa-report.md
agentqa/runs/<run_id>/agentqa-report.json
agentqa/runs/<run_id>/agentqa-plan.json
```

回归输出：

```text
agentqa/comparisons/<comparison_id>/agentqa-regression.md
agentqa/comparisons/<comparison_id>/agentqa-regression.json
```

每个目录唯一，重复目录不会覆盖已有报告。根目录的 `agentqa-report.md` 和 `.json` 保留为最近一次执行的兼容入口。前端从对应成功工具结果的 `artifacts` 读取真实路径，因此旧消息下载的是旧报告；尚未完成或失败的工具调用不展示虚构的报告下载。

独立归档从启用本功能后的运行开始。此前已经被固定文件名覆盖的报告无法恢复，需要使用之前下载的文件或会话中保留的完整报告 JSON。

## 验证

在 backend 目录、已安装项目依赖的环境中执行：

```bash
PYTHONPATH=. uv run pytest tests/agentqa tests/agentqa_demo -q
PYTHONPATH=. uv run ruff check agentqa tests/agentqa agentqa_demo tests/agentqa_demo
PYTHONPATH=. uv run ruff format --check agentqa tests/agentqa
make test
```

Windows PowerShell 若使用本地虚拟环境：

```powershell
$env:PYTHONPATH='.;packages/harness'
$env:PYTHONIOENCODING='utf-8'
.venv/Scripts/python.exe -m pytest tests/agentqa tests/agentqa_demo -q
```

在 frontend 目录执行：

```bash
pnpm exec rstest run tests/unit/core/messages/agentqa-artifacts.test.ts tests/unit/core/messages/utils.test.ts tests/unit/core/artifacts
pnpm typecheck
pnpm test:e2e tests/e2e/agentqa-regression-artifacts.spec.ts --project=chromium
```

核心集成场景使用真实执行器：基线通过 ASGITransport 执行内置验收 API（2 通过、3 失败），修复后通过 MockTransport 模拟修正用户年龄类型，同时让订单接口返回 500。登录与删除缺陷保持不变，预期对比结果是**已修复 1、新增缺陷 1、仍未解决 2、持续通过 1**。验收 API 及三个严格 xfail 缺陷测试保持原样。

其他覆盖包括接口重排、条件变化、新增/缺失测试、空报告、旧版兼容、非法报告、网络错误、历史文件留存、无网络比较、工具注册和浏览器下载路径。测试中的模拟修复不代表真实部署已修复。
