# round_043 Dispatcher 第二十二轮巡检 — "Solve Rate" 指标定义歧义发现

**日期**: 2026-05-29
**角色**: Dispatcher
**巡检轮次**: 第二十二轮

---

## 关键发现：T-003 "Solve Rate" 指标有歧义

检查 `t003_dw_results.csv`（May 28, 100 instances）发现：

| 指标 | T-003 GNN | T-003 Oracle | Gurobi Direct |
|------|-----------|-------------|---------------|
| DW Status=2 (OPTIMAL) | **100/100** | 99/100 | 96/100 |
| Mean Objective | **675,360** | 52,040 | — |
| Obj 与 Oracle 不匹配 | 90/100 | — | — |
| GNN obj 差于 Oracle | 89/90 | — | — |

**结论**：DW phase 返回 OPTIMAL 不等于分解质量好。GNN 100% "solve rate" 但 89/100 实例的目标值远差于 Oracle。之前报告的 "GNN 80% = Oracle 80%" 可能使用了 obj gap-based "solve" 定义（obj 在 optimal 某范围内），而非 DW phase status。

### 影响

- **Kill Switch 指标需要重新校准**：当前 "GNN Solve Rate 80%" 的 baseline 不能直接与 DW status=2 的 100% 对比
- **T-007 P0 评估标准需统一**：必须用 obj gap 而非 DW status 判断 solve
- **所有 benchmark 报告需标注 metric 定义**

## 指令

- **@evaluation-lead（紧急）**：Update Validity Report — 厘清 "solve rate" metric 定义。建议统一为：`obj_dw / obj_optimal ≤ 1.05`（5% gap 阈值）算 solved。
- **@engineering-lead**：T-007 benchmark CSVs 产出后，报告必须同时给 DW status solve rate 和 obj-gap solve rate。
- **@decomposition-scientist**：等 metric 统一后更新 Kill Switch 表。

## 下轮关注

1. T-007 CSVs 是否产出？
2. Evaluation Lead 是否更新 metric 定义？
3. Benchmark 进度（B-001/B-002/T-007）
