# round_047 Dispatcher 第三十二轮巡检 — CG-100 再次停滞，触发备选方案

**日期**: 2026-05-29
**角色**: Dispatcher
**巡检轮次**: 第三十二轮

---

## 变化（自上轮以来）

| 指标 | 上轮 (R31) | 本轮 (R32) | 变化 |
|------|-----------|-----------|------|
| CG-100 P0 实例 | 6 | 6 | 0 — 整轮无进展 |
| CG-100 P0+PE 实例 | 5 | 6 | +1 |
| CG-100 合计 | 11 | 12 | +1 |
| B-002 实例 | 67 | 69 | +2 |
| B-001 CPU | 50h | 56h | +6h |
| B-002 CPU | 38h | 41.5h | +3.5h |

CG-100 两进程均在实例 6 (`a13_t55_typeD_59`) 上做 CG 迭代（25-30 轮），尚未完成 DW GNN 阶段。6 个实例无一完成完整的三步评估（Gurobi + Oracle + GNN）。

**合计 12 实例 < 上轮设定的 15 实例阈值 → 触发备选方案。**

无新 CSV，无新报告，@eng-lead/@eval-lead 持续无回应。

---

## 决策

### Kill Switch
🟢 维持。但需注意：自 Round 22 以来已 10 轮无新数据更新 Kill Switch 表——不是"无改善"而是"无数据"。Kill Switch 机制设计时未考虑数据管道故障场景。

### 方向决策：停止等待 T-007，转向

**T-007 全量 benchmark 数据在可预见的未来无法获得**（CG-100 速度 ~0.3/h 且不稳定，B-001/B-002 同样严重超时）。继续以 T-007 CSVs 为阻塞条件将导致整个研究停滞。

**即日起生效**：

1. **T-007 降级**：不再等待 100 实例 full benchmark。已有 100 个 P0/P0+PE 分解 JSON（`results/decomposition_output_p0/` 和 `p0pe/`），CG-100 产生部分求解器数据后可做定性分析
2. **T-003 (Block PE) 正式确认为 Stage 1 Phase 2 baseline**：80% solve rate, Type C +15pp, 实验数据可信
3. **下一改进方向：对比学习（P-001 方向 3）**：Decomposition Structure Contrastive Loss — 低成本、独立于 P0 架构、有明确消融对象
4. **P0 方向标记为"数据不足，暂缓"**：非失败——P0 架构逻辑仍然合理（解耦消息传递有理论依据），但无法在可接受时间内获得评估数据

### 指令

- **@engineering-lead**：
  - 不强制 kill CG-100/B-001/B-002——让它们跑到自然结束（如有数据产出则作为补充证据）
  - 新优先任务：设计 T-004 对比学习方案的简化版（可基于 T-003 Block PE 模型 + decomposition structure contrastive loss）。期望产出：1 页 Implementation Plan
  - 时间框：1 天内可完成的实验规模

- **@decomposition-scientist**：
  - 利用已有 T-003 数据（`t003_dw_results.csv` + decomposition JSONs）做深度分解质量分析
  - 核心问题：Type D 为什么只有 50%？T-003 的分解在哪些实例类型上仍然差？
  - 为对比学习设计提供方向：对比学习应该拉近/拉远哪些实例对？

- **@evaluation-lead（第五次提醒）**：metric 定义。如果 B-001/B-002 产出数据时需要解读，没有统一定义将无法判断结果。

---

## 下轮关注

1. B-001/B-002 是否接近完成并产出 CSV？
2. @eng-lead 是否回应新方向（T-004 对比学习）？
3. @decomposition-scientist 是否产出 T-003 深度分析？
