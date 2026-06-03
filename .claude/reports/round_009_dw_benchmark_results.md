# Round 009 — T-002 DW 基准测试结果分析

**日期**: 2026-05-27
**工人**: worker-assistant（接替卡住的 worker-delta 完成 T-002 分析）
**任务**: T-002 — DW 全量验证（100 实例）

---

## 执行情况

- worker-delta 在服务器启动 benchmark（tmux `dw_full`），12:20 重跑
- delta 最后心跳 12:45，之后离线，tmux 会话消失
- benchmark 实际完成了 100 实例并写入了 `results/gap_dw_results_new.csv`
- 本 worker 对结果进行了完整分析

---

## 结果概览

| 类别 | 数量 | 占比 |
|------|------|------|
| Exact match (Gurobi=DW) | 39 | 39.0% |
| Small gap (<5%) | 30 | 30.0% |
| Large gap (5-100%) | 3 | 3.0% |
| Catastrophic (>100%, artificial cost 主导) | 8 | 8.0% |
| TIME_LIMIT (120s) | 20 | 20.0% |

### 成功率

| 指标 | 结果 | 目标 | 判定 |
|------|------|------|------|
| DW Oracle 求解成功 (RMP OPTIMAL) | 80% | >80% | ⚠️ 恰好达标 |
| Oracle-Gurobi 精确一致 | 39% | >90% | ❌ 远未达标 |
| 可用结果 (exact + gap<5%) | 69% | — | — |

### 关键发现

1. **8 例灾难性失败全部是 Type C 实例**，obj 值高达 2e8-9e8（Gurobi 真值仅 3k-7k）
   - 这些实例的 NodeCount 全部 > 1（4727-20618）
   - 根因：DW 生成的列不能覆盖所有约束，RMP 强制使用 artificial variables
   - 这些实例的共同特征：agents 多 (14-16)、tasks 多 (63-89)、type C

2. **TIME_LIMIT 20 例**：120s 超时但 gap 信息不全，说明 CG 迭代在限时内未收敛

3. **NodeCount > 1 的实例有 47 个**，说明 tightness=0.50 的新实例确实更难

4. **可用率 69%**：在排除超时和灾难性失败后，DW 能找到接近最优的解（gap<5%）

---

## 结论

- **artificial_cost=1e3 对多数实例有效**，但 Type C 大实例仍需更高 artificial_cost 或更好的列生成策略
- **DW 不是精确算法**：在没有 branch-and-price 的情况下，DW+MIP RMP 是启发式，不可能 100% 匹配 Gurobi
- **T-002 执行完成**，结果已存档。是否满足验收标准由调度员判断

---

## 给 T-007 的建议

- 在最终评估中，DW 与 Gurobi 的对比应区分"可用结果"（gap<5%）和"失败结果"
- Type C 灾难性失败可能需要单独处理（提高 artificial_cost 或限制 CG 迭代）
- 考虑在 T-007 中加入按实例类型的细分分析
