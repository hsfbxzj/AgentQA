# AgentQA

AgentQA 是一个由大模型驱动的 API 自动化测试与质量分析 Agent。用户可以通过自然语言提出测试需求，系统会解析 OpenAPI 文档、生成测试计划、等待人工审批、执行确定性契约测试，并交付 Markdown 与 JSON 报告。

本仓库只发布 AgentQA 自身的实现代码和接入补丁，不重复提交完整的上游 Agent Runtime，方便直接查看本项目新增的核心能力。

## 已实现能力

- OpenAPI 3.x JSON/YAML 解析与本地 `$ref` 解析
- 基于 Pydantic 的结构化 TestPlan、TestCase 和 TestReport
- 稳定 Plan ID，保证审批计划与实际执行内容一致
- Human-in-the-loop 人工审批与执行器二次校验
- 基于 HTTPX 的异步请求执行
- 状态码、响应 Schema、空 Body 和响应时延断言
- 本地目标白名单、路径校验和 SSRF 防护
- Markdown、JSON 报告生成与 Artifact 下载
- React/TypeScript 结构化测试计划卡片
- FastAPI Demo API 与 3 个预埋契约缺陷
- Docker Compose 集成及聚焦自动化测试

## 设计思路

AgentQA 采用“LLM 决策与解释 + Python 确定性执行”的分层架构：

```text
自然语言测试需求
        ↓
LLM 选择 AgentQA Skill 与 Tool
        ↓
解析 OpenAPI，生成结构化测试计划
        ↓
前端展示完整计划
        ↓
用户审批（HITL）
        ↓
HTTPX 执行请求，Python 断言计算 Pass/Fail
        ↓
LLM 根据断言证据总结缺陷
        ↓
交付 Markdown / JSON 报告
```

大模型负责理解用户意图、选择工具和整理结果；测试是否通过由确定性程序计算，避免大模型主观判断造成的不稳定和不可复现问题。

## 目录结构

```text
backend/agentqa/                         核心测试引擎
├── openapi_parser.py                    OpenAPI 解析
├── case_generator.py                    测试用例生成
├── executor.py                          HTTP 请求执行
├── assertions.py                        确定性断言
├── security.py                          白名单与 SSRF 防护
├── reporter.py                          Markdown/JSON 报告
├── models.py                            Pydantic 数据模型
└── tools.py                             LangGraph Tool 接入

backend/agentqa_demo/                    FastAPI 测试靶场
backend/tests/agentqa/                   核心模块与 Tool 测试
backend/tests/agentqa_demo/              Demo API 契约测试
skills/public/agentqa-api-testing/       Agent 测试工作流规范
frontend/.../agentqa-plan-card.tsx       结构化计划审批组件
integration/deerflow-v2.0.0.patch        运行框架接入补丁
```

## 本地运行核心测试

建议使用 Python 3.12：

```bash
python -m venv .venv
source .venv/Scripts/activate
python -m pip install -e ".[test]"
```

运行不依赖 Agent Runtime 的核心测试：

```bash
pytest \
  backend/tests/agentqa/test_case_generator.py \
  backend/tests/agentqa/test_executor.py \
  backend/tests/agentqa/test_openapi_parser.py \
  backend/tests/agentqa/test_reporter.py \
  backend/tests/agentqa/test_security.py \
  backend/tests/agentqa_demo -q
```

## 接入完整 Agent 平台

当前集成以 DeerFlow `v2.0.0` 为基线。完整运行时保留在上游仓库，本仓库通过源码目录与补丁记录 AgentQA 的新增内容。

### 1. 获取固定版本的运行框架

```bash
git clone --branch v2.0.0 --depth 1 https://github.com/bytedance/deer-flow.git deer-flow-agentqa
```

### 2. 复制 AgentQA 模块

将本仓库中的以下目录复制到 DeerFlow 根目录的相同路径：

```text
backend/agentqa/
backend/agentqa_demo/
backend/tests/agentqa/
backend/tests/agentqa_demo/
skills/public/agentqa-api-testing/
frontend/src/components/workspace/messages/agentqa-plan-card.tsx
```

### 3. 应用集成补丁

在 DeerFlow 项目根目录执行：

```bash
git apply /path/to/AgentQA/integration/deerflow-v2.0.0.patch
```

补丁负责完成 Tool 配置、前端消息识别、计划卡片渲染、Demo API 服务和 Docker 启停脚本接入。

### 4. 配置模型

根据上游配置示例创建本地 `.env` 和 `config.yaml`，并通过环境变量引用模型 Key。真实配置文件已加入忽略规则，不应提交到 Git。

OpenAI 兼容模型配置示例：

```yaml
models:
  - name: your-model
    display_name: Your Model
    use: langchain_openai:ChatOpenAI
    model: your-model
    api_key: $YOUR_MODEL_API_KEY
    base_url: https://your-openai-compatible-endpoint/v1
```

### 5. Docker 启动

在 Git Bash 中执行：

```bash
./scripts/docker.sh start
```

服务地址：

- AgentQA：<http://localhost:2026>
- Demo API Swagger：<http://localhost:8003/docs>
- Demo OpenAPI：<http://localhost:8003/openapi.json>

停止服务：

```bash
./scripts/docker.sh stop
```

## 演示方式

进入 Agent 工作区，新建对话并输入：

```text
/agentqa-api-testing 测试内置 Demo API。先展示测试计划，必须等我确认后再执行。
```

Agent 会先展示请求方法、路径、测试规则和预期状态码。只有用户明确批准后，执行工具才会发送实际请求。

内置 Demo API 提供 5 个接口并故意保留 3 个契约缺陷，正确验收结果为：

```text
5 cases / 2 passed / 3 failed
```

缺陷分别覆盖：

1. 响应字段类型与 OpenAPI Schema 不一致；
2. DELETE 状态码和空 Body 规则不一致；
3. 登录失败状态码与接口契约不一致。

完整集成环境的聚焦测试基线为：

```text
28 passed, 3 xfailed
```

其中 3 个 `xfail` 用于稳定记录 Demo API 中故意保留的缺陷。

## Roadmap

- [x] OpenAPI 解析与结构化测试计划
- [x] 人工审批与安全边界
- [x] 确定性契约测试执行器
- [x] Markdown/JSON 报告及前端下载
- [x] Docker Compose 集成
- [ ] 正常、异常、边界和认证场景扩展
- [ ] 测试任务与执行结果持久化
- [ ] 失败用例重跑与回归结果对比
- [ ] HTML 可视化测试报告
- [ ] 工具调用、Token、时延与异常监控

## 安全说明

- `.env`、`config.yaml`、运行日志和测试报告不会提交到仓库。
- 不要在源码、前端代码或文档中写入真实 API Key。
- 当前执行器仅允许访问安全白名单中的本地测试目标。
- 执行 POST、PUT、PATCH、DELETE 前必须审核测试计划。

## 开源说明

AgentQA 与 MIT License 开源的 DeerFlow 2.0 Agent Runtime 集成。上游来源与版权信息见 [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md)，原 MIT 许可证文本保留在 [LICENSE](./LICENSE)。

## License

[MIT License](./LICENSE)
