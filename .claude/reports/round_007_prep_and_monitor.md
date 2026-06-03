# Round 007 — T-007 前置准备与 DW 基准测试监控

**日期**: 2026-05-27
**工人**: worker-beta (作为 worker-alpha 替身，准备 T-007)
**状态**: 主动准备中，等待 T-002 完成

---

## 本轮已完成的工作

### 1. 主板维护
- 修正 worker-alpha 状态不一致（训练在 tmux 运行但状态表显示空闲）
- 更新调度日志

### 2. 新模型评估 (04_test.py)
- 在 tmux 中用新模型 (`models/best_model_gap.pth`) 跑了 04_test.py
- **结果非常好**：
  - Average True Clusters: 14.58
  - **PCR (Perfect Cluster Recovery): 0.9831**
  - **V-Measure: 0.9978**
  - **ARI: 0.9914**
  - **NMI: 0.9978**
- 200 个 cluster JSON 输出到 `models/cluster_outputs/test/`
- 多个实例 PCR=1.0（完美恢复）

### 3. DW 基准测试监控 (T-002)
- DW benchmark 在 tmux `dw_full` 中运行，18/100 实例完成
- **0 INFEASIBLE** — artificial_cost=1e5 工作正常
- 最新实例 GNN 完全匹配 Oracle：`a13_t88_typeE_10` (Obj=729, CG iters=92)
- 但早期实例有显著 GNN 误差：
  - `a13_t42_typeB_57`: GNN=432 vs Oracle=334 (+29%)
  - `a13_t41_typeB_37`: GNN=375 vs Oracle=299 (+25%)
  - `a13_t40_typeB_62`: GNN=419 vs Oracle=390 (+7.4%)
- 注意：当前 benchmark 使用旧模型的分解 JSON（`results/decomposition_output/`）

### 4. 持久化自调度
- 用 CronCreate 设置了每 2 分钟自动唤醒（durable, 7 天过期）
- 确保工人不会停止

---

## 当前 pipeline 理解

```
训练模型 (03) → 04_test.py (聚类指标) → 06_eval_instances.py (分解 JSON)
                                              ↓
                                    07_solve_decomposition.py (DW 求解)
```

- `04_test.py` → `models/cluster_outputs/test/*.json`（聚类评估用）
- `06_eval_instances.py` → `results/decomposition_output/*_decomposition.json`（DW 用）
- `07_solve_decomposition.py` 读 `_decomposition.json` 做 DW GNN 求解

---

## T-007 阻塞分析

T-007 唯一未满足的依赖：T-002（DW 基准测试，进行中）

T-007 执行计划：
1. 等 T-002 完成 → 运行 `06_eval_instances.py` 用新模型生成分解 JSON
2. 运行 `07_solve_decomposition.py` 做全流程评估
3. 对比 Gurobi/Metis/GCG baseline

---

## 给下一轮的经验教训

1. **不能用 06 覆盖正在被 benchmark 读取的分解 JSON**：会导致结果不一致
2. **artificial_cost=1e5 可行**（0 INFEASIBLE），config 中已确认
3. **新模型聚类质量很高** (PCR 0.98)，但需等 06 生成分解后才能知道 DW 优化效果
4. **GNN vs Oracle 误差可能是旧分解的问题**：当前 benchmark 用旧模型分解，
   需等新模型分解生成后重新评估
5. **CronCreate 工作正常**：可持续调度，不需要用户干预
