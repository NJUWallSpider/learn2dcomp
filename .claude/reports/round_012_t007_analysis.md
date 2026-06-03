# Round 012 — T-007 结果深度分析

**时间**: 2026-05-30 12:15 CST
**工人**: worker-gamma
**任务**: T-010 — 分析 T-007 100 实例 benchmark 结果

---

## 做了什么

1. 写 `analyze_t007.py` 解析 `results/gap_dw_results_new.csv`（100 实例）
2. 按 instance type 分维度统计 Oracle/GNN 求解率、gap 分布、CG 迭代数
3. 对比 T-002 结果 (round_011)，定位差异根因

## 关键发现

### artificial_cost 污染严重（8/100 实例，全部 Type C）

T-007 同样存在 artificial_cost 污染，且比 T-002 (5/65) 更严重：

| Instance | Gurobi Obj | Oracle Obj | 膨胀倍数 |
|----------|-----------|------------|----------|
| a15_t84_typeC_33 | 6,564 | 900,005,971 | ~137,000× |
| a14_t82_typeC_98 | 6,456 | 800,006,130 | ~124,000× |
| a15_t89_typeC_53 | 7,014 | 700,006,859 | ~100,000× |
| a16_t82_typeC_8 | 6,430 | 600,006,410 | ~93,000× |
| a15_t77_typeC_88 | 6,042 | 500,005,968 | ~83,000× |
| a15_t78_typeC_18 | 6,093 | 500,005,911 | ~82,000× |
| a15_t63_typeC_83 | 4,908 | 200,005,060 | ~41,000× |
| a15_t69_typeC_38 | 5,379 | 200,005,374 | ~37,000× |

Oracle obj ≈ Gurobi_obj + N × 1e8，意味着约 100 个人工变量进入了基（每个成本 1e6）。**config.py 设 artificial_cost=1e3 但 `GAPDWSolver.__init__()` 默认 1e6 未被覆盖。** 与 T-002 同一 bug，更严重——新实例更大，人工变量更多。

### 干净实例统计（排除 8 个污染 Type C + 20 个 TIME_LIMIT）

只统计 Oracle 返回 OPTIMAL (status=2) 的 80 实例（含 5 个干净的 Type C）：

| 指标 | 值 | T-002 对照 | 判定 |
|------|-----|-----------|------|
| DW Oracle OPTIMAL | 80/100 (80.0%) | 52/65 (80.0%) | 达标 |
| Oracle-Gurobi <1% | 57/80 (71.2%) | 38/48 (79.2%) | 略低 |
| Oracle-Gurobi <3% | 67/80 (83.8%) | — | 良好 |
| Oracle-Gurobi 中位 gap | 0.18% | — | 优秀 |
| GNN-Oracle 中位 gap | 0.00% | 0.00% | 优秀 |
| GNN-Oracle 平均 gap | 0.03% | 1.47% | 改善! |

### 按 Instance Type 分解

| Type | N | Oracle OPTIMAL | Oracle-Gurobi 中位 gap | 状态 |
|------|---|---------------|----------------------|------|
| A | 20 | 19 (95%) | 0.00% | 优秀 |
| B | 20 | 18 (90%) | 0.74% | 良好（1 个 outlier: a14_t79_typeB_42 at 31.2%）|
| C | 20 | 13 (65%) | — | 差（8 个污染 + 7 个 TIME_LIMIT）|
| D | 20 | 10 (50%) | 0.63% | 一般（10 TIME_LIMIT）|
| E | 20 | 20 (100%) | 0.00% | 完美 |

### CG 迭代数对比

- T-007 Oracle CG: mean=61.1, median=60
- T-007 GNN CG: mean=61.2, median=60
- T-002 Oracle CG: mean=63, GNN CG: mean=50 (GNN 少 20%)

T-007 中 GNN 和 Oracle CG 迭代数几乎相同（都是新模型分解），说明新模型学习到的分解结构与 GCG oracle 高度一致。

### TIME_LIMIT 分布

- T-007: 20/100 (20%) TIME_LIMIT — Type C (7), Type D (10), Type A (1), Type B (2)
- T-002: 12/65 (18.5%) TIME_LIMIT
- T-007 的 TIME_LIMIT 比例略高，因为新实例更大（更多 agents × tasks）

## 根因分析：为什么 T-007 报告 "19.36% gap"？

调度日志中 "DW Oracle 19.36%" 的计算包括了 8 个 artificial_cost 污染实例（gap 高达 10^7%），严重拉高了均值。**排除污染后，干净实例的 Oracle-Gurobi 中位 gap 仅 0.18%，结果良好。**

## 与 T-002 对比

| 维度 | T-002 (旧分解, 65 实例) | T-007 (新模型分解, 100 实例) |
|------|------------------------|---------------------------|
| Oracle OPTIMAL | 80.0% | 80.0% |
| Oracle-Gurobi <1% | 79.2% | 71.2% |
| artificial_cost 污染 | 5/65 (7.7%) | 8/100 (8.0%) |
| GNN-Oracle 中位 gap | 0.00% | 0.00% |
| GNN CG 节省 | 20% 更少 | 0%（几乎相同）|

**结论**：新模型分解达到与 GCG oracle 同等的质量（GNN-Oracle gap 0.00%）。主要问题仍是 artificial_cost 污染和 TIME_LIMIT。

## 未解决问题

1. **artificial_cost bug**: `GAPDWSolver.__init__()` 默认 1e6 未被 config 1e3 覆盖。需代码修复后重跑受影响的 Type C 实例
2. **T-002 剩余 35 实例**: 未跑完
3. **a14_t79_typeB_42 outlier**: Oracle-Gurobi gap 31.2% — 需单独调查
4. **Type D TIME_LIMIT 50%**: 120s 不够，可能需要增加 time_limit 或优化 DW
5. **report.html 需更新**: 合入 T-007 和 T-002 最终结果

## 经验教训

- **不要只看均值**: "19.36% gap" 掩盖了真实情况——干净实例中位 gap 仅 0.18%
- **artificial_cost 是 T-002/T-007 共同瓶颈**: 修复后预计 Oracle-Gurobi 一致率可达 85%+
- **GNN 分解质量已达标**: GNN-Oracle gap 0.00%，CG 迭代数一致。当前瓶颈不在 GNN，在 DW 求解器本身
