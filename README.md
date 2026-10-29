# 基本面 Agent 演示

这是金融多 Agent 计划的一个本地 MVP，默认使用 LangGraph 状态图：

```text
本地缓存
  -> 缓存校验
  -> 确定性 Supervisor 检查清单
  -> 指标计算
  -> 验证器
  -> LLM 摘要与解释
  -> Markdown 报告
  -> 人工审批 interrupt
  -> checkpoint 恢复
  -> 无建议安全校验
```

默认缓存来自 SEC EDGAR `companyfacts`，覆盖三只美股。仓库中仍保留一份
illustrative fixture，用于离线 UI 和流水线测试。

## 范围

- 固定三只美股。
- 每只股票四个缓存季度。
- 营收及营收增长。
- 净利润及净利润增长。
- 毛利率。
- 自由现金流。
- 资产负债率。
- 每个计算指标都带有来源、期间和数据日期。
- 不包含买入、卖出或持有建议。
- 不接入券商或交易系统。

## 运行

项目依赖已经安装在本地 `.venv` 中。下面的命令直接使用虚拟环境 Python：

```powershell
.\.venv\Scripts\python.exe -m fundamental_agent.cli --thread-id demo-001 --md-output sample_report.md --json-output sample_report.json
```

第一次运行会在人工审批节点暂停，并输出 `thread_id` 和恢复命令。批准：

```powershell
.\.venv\Scripts\python.exe -m fundamental_agent.cli --thread-id demo-001 --approve --md-output sample_report.md --json-output sample_report.json
```

拒绝：

```powershell
.\.venv\Scripts\python.exe -m fundamental_agent.cli --thread-id demo-001 --reject
```

运行时会在终端输出节点进度，例如：

```text
正在加载 SEC 缓存...
正在计算指标...
正在验证指标...
llm_summary 开始
llm_summary 完成，来源：openai-compatible
render_report 开始
render_report 完成
human_approval 等待中
```

checkpoint 默认写入：

```text
data/checkpoints.sqlite
```

如果需要回到旧的 DAG-lite 引擎：

```powershell
.\.venv\Scripts\python.exe -m fundamental_agent.cli --engine daglite
```

## 环境配置

项目根目录已经提供 `.env` 和 `.env.example`。使用前编辑 `.env`：

```dotenv
LLM_MODE=auto
LLM_API_KEY=
LLM_MODEL=
LLM_BASE_URL=https://api.openai.com/v1
LLM_MAX_TOKENS=4000
LLM_TIMEOUT_SECONDS=180

SEC_USER_AGENT=fundamental-agent-demo/0.1 research contact@example.com
```

- `LLM_MODE=auto`：有 Key 和模型名时调用 API，否则使用模板。
- `LLM_MODE=api`：强制调用 API。
- `LLM_MODE=template`：强制使用模板。
- `LLM_MAX_TOKENS`：单次摘要最大输出 token，默认 4000。
- `LLM_TIMEOUT_SECONDS`：模型请求超时时间，默认 180 秒。
- `SEC_USER_AGENT`：SEC 要求的可识别 User-Agent。

程序启动时会通过 `python-dotenv` 自动加载项目根目录 `.env`。
系统环境变量优先级高于 `.env`，适合部署时覆盖本地配置。

.env 已加入 `.gitignore`，不要把真实 API Key 提交到仓库。

## 内部 API

本地启动：

```powershell
.\.venv\Scripts\python.exe -m uvicorn fundamental_agent.api:app --host 127.0.0.1 --port 8000
```

接口文档：

```text
http://127.0.0.1:8000/docs
```

主要接口：

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/health` | 健康检查 |
| POST | `/runs` | 创建运行并生成草稿 |
| GET | `/runs/{thread_id}` | 查询运行状态 |
| POST | `/runs/{thread_id}/approve` | 批准报告 |
| POST | `/runs/{thread_id}/reject` | 拒绝报告 |
| GET | `/runs/{thread_id}/report` | 获取 Markdown 和结构化 JSON |
| GET | `/runs/{thread_id}/trace` | 获取 Trace 事件 |

除 `/health` 外，所有接口默认要求鉴权。`.env` 中配置：

```dotenv
API_REQUIRE_AUTH=true
API_AUTH_TOKEN=replace-with-a-long-random-token
```

请求时使用 Bearer Token：

```powershell
$headers = @{
  Authorization = "Bearer 你的 API_AUTH_TOKEN"
  "Content-Type" = "application/json"
}

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/runs" `
  -Headers $headers `
  -Body '{"tickers":["AAPL","MSFT","NVDA"],"llm_mode":"template"}'
```

也支持：

```text
X-API-Key: 你的 API_AUTH_TOKEN
```

Swagger 页面右上角的 Authorize 按钮可以填入 Bearer Token。

API 默认使用独立的 SQLite checkpoint：

```text
data/checkpoints.api.sqlite
```

## Docker Compose

```powershell
docker compose up --build
```

服务地址：

```text
http://127.0.0.1:8000
```

`data/` 会挂载到容器内，checkpoint、Trace 和报告会持久化到本地。

## LLM 摘要

`llm_summary` 节点只读取已经验证的结构化指标，输出带 evidence 的摘要。

三种模式：

- `auto`：有 API Key 和模型名时调用模型，否则使用模板。
- `api`：强制调用模型，缺少配置时直接报错。
- `template`：强制使用确定性模板。

无 Key 时可以直接运行：

```powershell
.\.venv\Scripts\python.exe -m fundamental_agent.cli --thread-id demo-template --llm-mode template
```

调用 OpenAI-compatible Chat Completions 接口：

```powershell
.\.venv\Scripts\python.exe -m fundamental_agent.cli --thread-id demo-api --llm-mode api
```

也支持：

```text
LLM_API_KEY
LLM_MODEL
LLM_BASE_URL
OPENAI_API_KEY
OPENAI_MODEL
```

API 失败、超时或返回格式不合法时，会自动回退到模板摘要，并在报告中标记 `summary_source`。

## Compliance Agent

合规检查位于 `llm_summary` 之后、人工审批之前：

```text
llm_summary -> compliance -> render_report -> human_approval
```

当前规则检查：

- 投资建议免责声明
- 买入、卖出、持有和目标价类表述
- 收益保证、稳赚、无风险收益类表述
- 摘要 evidence 是否存在于结构化指标
- SEC source、source_url、accession_number、filed_date
- filed_date 是否早于 period_end_date
- 摘要来源是否已知

合规不通过时，LangGraph 直接结束，不进入人工审批，也不会写最终报告。
API 返回状态为 `compliance_failed`。

## Trace、预算与评测

每次 LangGraph 运行会写入本地 Trace：

```text
data/traces/<thread-id>.jsonl
```

Trace 包含节点耗时、状态、LLM 调用、token 用量、预算快照、错误和模板回退。
API Key 和 `sk-...` 字符串会自动脱敏。

预算配置：

```dotenv
LLM_RUN_TOKEN_BUDGET=12000
LLM_COST_BUDGET_USD=0
LLM_INPUT_PRICE_PER_MILLION=0
LLM_OUTPUT_PRICE_PER_MILLION=0
```

金额预算需要通过价格变量配置；价格未知时保持 `0`，先使用 token 预算。

运行 Golden Eval：

```powershell
.\.venv\Scripts\python.exe -m fundamental_agent.eval_runner
```

评测基准：

```text
evals/golden/fundamental_metrics.json
```

评测报告：

```text
evals/reports/latest.json
```

评测覆盖 SEC 指标、季度连续性、filing 追溯、摘要 evidence、无建议和预算快照。

## 回归闸门

统一检查命令：

```powershell
.\.venv\Scripts\python.exe -m fundamental_agent.check
```

或者：

```powershell
.\scripts\check.ps1
```

它会依次执行全部单元测试和 Golden Eval，全部通过才返回成功。

GitHub Actions 配置在：

```text
.github/workflows/ci.yml
```

负向测试覆盖缺少季度、缺少 provenance、未来日期、非法 JSON、预算超限、API 失败和审批拒绝。

## 刷新 SEC 缓存

SEC 请求需要提供描述性的 `User-Agent`，默认从 `.env` 的 `SEC_USER_AGENT` 读取。

然后刷新本地缓存：

```powershell
.\.venv\Scripts\python.exe -m fundamental_agent.sec_ingest --tickers AAPL MSFT NVDA --as-of 2026-10-12 --out data/cache/quarterly_fundamentals.sec.json
```

抓取流程：

1. 用 SEC `company_tickers.json` 把 ticker 映射到 CIK。
2. 拉取 `data.sec.gov` 的 `companyfacts`。
3. 只使用 `filed <= --as-of` 的事实。
4. 取最近四个已披露 fiscal quarter。
5. 缺失的单季值由累计值差分推导：
   - `Q2 = 6M YTD - Q1`
   - `Q3 = 9M YTD - 6M YTD`
   - `Q4 = FY - 9M YTD`
6. 每个季度都附带表单类型、accession number、申报日期和来源 URL。

## NewsEvent 数据层

当前已支持抓取 SEC 8-K/8-K/A 重大事件：

```powershell
.\.venv\Scripts\python.exe -m fundamental_agent.news_ingest --tickers AAPL MSFT NVDA --as-of 2026-10-28 --lookback-days 180 --out data/cache/news_events.sec.json
```

本地缓存：

```text
data/cache/news_events.sec.json
```

每条 `NewsEvent` 包含：

- ticker
- company_name
- event_type
- headline
- source
- source_url
- accession_number
- form_type
- published_at
- filed_date
- report_date
- items
- primary_document
- summary

抓取规则：

- 只保留 8-K 和 8-K/A
- 只保留 `filed_date <= --as-of`
- 按 `--lookback-days` 过滤历史事件
- 按 accession number 去重
- 校验 SEC URL、发布时间、filing 日期和 ticker

News Agent 已接入 LangGraph 和报告，当前使用确定性事件摘要。
新闻只作为独立事件信息展示，不会修改财务指标。LLM 新闻解释将在后续版本加入。

## 测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## 架构

LangGraph 节点：

1. `load_cache`
2. `validate_cache`
3. `supervisor`
4. `compute_metrics`
5. `verify_metrics`
6. `news`
7. `llm_summary`
8. `compliance`
9. `render_report`
10. `human_approval`
11. `safety_check`

默认执行引擎是 [langgraph_pipeline.py](fundamental_agent/langgraph_pipeline.py)。
它使用 SQLite checkpointer，支持暂停、恢复和审批拒绝。

`fundamental_agent/graph.py` 仍保留为 DAG-lite 备用引擎，用于对比和离线测试。

```text
load_cache -> validate_cache -> supervisor -> compute_metrics
  -> verify_metrics -> news -> llm_summary -> compliance -> render_report -> human_approval
  -> safety_check（批准）
  -> END（拒绝）
```

## 迁移路径

1. 已加入 SEC EDGAR `companyfacts` 本地缓存写入器；下一步加强数据质量规则和重述处理。
2. 已将默认流程迁移到 LangGraph `StateGraph`。
3. 已加入 SQLite checkpointer、人工审批 interrupt 和 resume。
4. 已加入受约束的 LLM 摘要与解释节点，支持 API 和模板降级。
5. 当权限和数据源扩展后，加入数据质量 Agent 和合规 Agent。
6. 将风险、合规和订单执行保持在 LLM 运行时之外。

## 输出

CLI 会写入：

- `sample_report.md`：人类可读简报。
- `sample_report.json`：结构化输出，每个指标点都附带来源、期间和数据日期。

默认 CLI 使用的缓存是：

```text
data/cache/quarterly_fundamentals.sec.json
```
