# 基本面 Agent 演示

这是金融多 Agent 计划的一个零服务 MVP：

```text
本地缓存
  -> 缓存校验
  -> 确定性 Supervisor 检查清单
  -> 指标计算
  -> 验证器
  -> Markdown 报告
  -> 无建议安全校验
```

该演示使用本地示例 fixture。数字有意标记为演示数据，任何真实使用前都必须替换为已授权、point-in-time 的金融数据。

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

在项目目录下执行：

```powershell
python -m fundamental_agent.cli
```

或指定三只股票：

```powershell
python -m fundamental_agent.cli --tickers AAPL MSFT NVDA --md-output sample_report.md --json-output sample_report.json
```

只生成 Markdown 报告：

```powershell
python -m fundamental_agent.cli --tickers AAPL MSFT NVDA --md-output sample_report.md
```

## 测试

```powershell
python -m unittest discover -s tests -v
```

## 架构

节点刻意保持显式：

1. `load_cache`
2. `validate_cache`
3. `supervisor`
4. `compute_metrics`
5. `verify_metrics`
6. `render_report`
7. `safety_check`

`fundamental_agent/graph.py` 是一个小型、按依赖顺序执行的 DAG 运行器。它让第一个里程碑无需安装工作流引擎即可运行。节点边界可以直接对应未来的 LangGraph `StateGraph`：

```text
load_cache -> validate_cache -> supervisor -> compute_metrics
  -> verify_metrics -> render_report -> safety_check
```

## 迁移路径

1. 用真实的本地缓存写入器替换 fixture JSON。
2. 用 LangGraph `StateGraph` 替换 `graph.py`。
3. 加入 LangGraph checkpointer 和用于人工审批的 interrupt 节点。
4. 只有在确定性基线通过评测后，才加入 LLM Supervisor。
5. 当权限和数据源扩展后，加入数据质量 Agent 和合规 Agent。
6. 将风险、合规和订单执行保持在 LLM 运行时之外。

## 输出

CLI 会写入：

- `sample_report.md`：人类可读简报。
- `sample_report.json`：结构化输出，每个指标点都附带来源、期间和数据日期。
