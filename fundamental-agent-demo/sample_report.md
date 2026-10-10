# 美股基本面简报

- 生成时间：2026-10-10T12:53:38+08:00
- 数据截止：2026-10-10
- 缓存来源：local demo fixture (illustrative, not audited)
- 数据范围：每只股票最近 4 个季度
- 增速口径：环比 QoQ，因为本地缓存只有 4 个季度

> 本 Demo 使用本地 illustrative fixture，仅用于验证系统结构和计算口径。
> 这些数字不是实时行情，也不是经审计的正式财报数据。
> 报告仅做基本面信息整理，不构成投资建议，不包含买卖建议，不连接交易系统。

## AAPL - Apple Inc. (demo fixture)

| 财报期间 | 数据日期 | 营收 (USD bn) | 营收环比 | 净利润 (USD bn) | 净利润环比 | 毛利率 | 自由现金流 (USD bn) | 资产负债率 | 数据来源 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| 2025-Q4 | 2026-01-30 | 124.30 | N/A | 36.30 | N/A | 46.74% | 37.00 | 78.08% | demo_fixture_v1: illustrative quarterly data |
| 2026-Q1 | 2026-04-30 | 128.50 | 3.38% | 37.00 | 1.93% | 46.69% | 37.80 | 77.42% | demo_fixture_v1: illustrative quarterly data |
| 2026-Q2 | 2026-07-30 | 132.00 | 2.72% | 38.20 | 3.24% | 46.82% | 39.40 | 76.72% | demo_fixture_v1: illustrative quarterly data |
| 2026-Q3 | 2026-10-05 | 136.40 | 3.33% | 39.50 | 3.40% | 46.55% | 40.70 | 75.84% | demo_fixture_v1: illustrative quarterly data |

说明：同一行的全部指标均来自该行标注的财报期间、数据日期和数据来源；指标由确定性公式计算得到。

## MSFT - Microsoft Corporation (demo fixture)

| 财报期间 | 数据日期 | 营收 (USD bn) | 营收环比 | 净利润 (USD bn) | 净利润环比 | 毛利率 | 自由现金流 (USD bn) | 资产负债率 | 数据来源 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| 2025-Q4 | 2026-01-29 | 65.60 | N/A | 24.70 | N/A | 68.60% | 20.00 | 46.88% | demo_fixture_v1: illustrative quarterly data |
| 2026-Q1 | 2026-04-29 | 68.00 | 3.66% | 25.50 | 3.24% | 68.38% | 20.70 | 46.73% | demo_fixture_v1: illustrative quarterly data |
| 2026-Q2 | 2026-07-29 | 70.20 | 3.24% | 26.40 | 3.53% | 68.38% | 21.50 | 46.59% | demo_fixture_v1: illustrative quarterly data |
| 2026-Q3 | 2026-10-06 | 72.50 | 3.28% | 27.30 | 3.41% | 68.28% | 22.30 | 46.46% | demo_fixture_v1: illustrative quarterly data |

说明：同一行的全部指标均来自该行标注的财报期间、数据日期和数据来源；指标由确定性公式计算得到。

## NVDA - NVIDIA Corporation (demo fixture)

| 财报期间 | 数据日期 | 营收 (USD bn) | 营收环比 | 净利润 (USD bn) | 净利润环比 | 毛利率 | 自由现金流 (USD bn) | 资产负债率 | 数据来源 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| 2025-Q4 | 2026-02-25 | 44.00 | N/A | 22.00 | N/A | 75.00% | 23.80 | 31.67% | demo_fixture_v1: illustrative quarterly data |
| 2026-Q1 | 2026-05-27 | 46.50 | 5.68% | 23.40 | 6.36% | 74.84% | 25.20 | 31.25% | demo_fixture_v1: illustrative quarterly data |
| 2026-Q2 | 2026-08-26 | 49.00 | 5.38% | 24.80 | 5.98% | 74.90% | 26.60 | 30.88% | demo_fixture_v1: illustrative quarterly data |
| 2026-Q3 | 2026-10-07 | 52.00 | 6.12% | 26.50 | 6.85% | 75.00% | 28.00 | 30.34% | demo_fixture_v1: illustrative quarterly data |

说明：同一行的全部指标均来自该行标注的财报期间、数据日期和数据来源；指标由确定性公式计算得到。

## 校验记录

- Supervisor locked the MVP metric checklist.
- AAPL 2025-Q4: record and source validated
- AAPL 2026-Q1: record and source validated
- AAPL 2026-Q2: record and source validated
- AAPL 2026-Q3: record and source validated
- AAPL: 4 periods, 28 metric points verified
- MSFT 2025-Q4: record and source validated
- MSFT 2026-Q1: record and source validated
- MSFT 2026-Q2: record and source validated
- MSFT 2026-Q3: record and source validated
- MSFT: 4 periods, 28 metric points verified
- NVDA 2025-Q4: record and source validated
- NVDA 2026-Q1: record and source validated
- NVDA 2026-Q2: record and source validated
- NVDA 2026-Q3: record and source validated
- NVDA: 4 periods, 28 metric points verified
- All required metrics passed deterministic recomputation checks.
- No trading-advice phrases detected in the report body.

## 免责声明

本报告仅用于基本面信息整理和系统演示，不构成任何投资建议。报告不包含买入、卖出或持有建议，不连接交易系统，也不执行任何交易。

本报告不包含买入、卖出或持有建议，也没有任何交易执行接口。
