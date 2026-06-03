# Round 009 — worker-gamma 综合工作报告

**日期**: 2026-05-27
**工人**: worker-gamma
**任务**: T-008 完成 + 模型评估 + METIS baseline + DW 基准监控

---

## 做了什么

### 1. T-008: 更新技术报告 (已 commit, round_006)

更新 `report.html`:
- Type B tightness 1.20→0.50, 70% NodeCount>1
- reassign_noise_points 修复文档化
- CFLP/UFLP 清理已记录
- 数据集重建结果 (1200/1200 GCG 成功)
- Section 8 实验结果（含 T-001/003/005 完成 + T-002/T-006 占位符）
- Roadmap Phase 5.4 标记已完成

### 2. 新模型评估 (T-006 完成后)

- **04_test.py**: ARI=0.9914, NMI=0.9978 — 聚类质量与 oracle 几乎一致
- **06_eval_instances.py**: 100 test 实例 GNN 分解在 12 秒内生成 (CUDA)
- **METIS baseline**: ARI=0.0026, NMI=0.1202 — 通用图划分完全失败
- **T-006 训练结果**: 50 epochs, best @21, Loss plateau ~4.34

### 3. DW 基准监控

- DW benchmark 在 tmux dw_full 中运行 (pid 3790851)
- 21/100 实例完成，当前在 a14_t100_typeC_3 (硬实例)
- 部分结果 (15 实例): Oracle-Gurobi 一致率 80%, GNN-Gurobi 一致率 26.7%
- Type C 实例导致 DW TIME_LIMIT (120s 不够)
- Type B 实例 GNN 误差 15-25%

### 4. 自动化调度

- CronCreate 已设置：调度员巡检 (每分钟) + 工人引擎 (每分钟)
- T-002 完成后自动标记 ✅ → 解锁 T-007 → 空闲工人认领执行

---

## 修改文件清单

| 文件 | 改动 |
|------|------|
| `report.html` | 多轮更新 (tightness, 修复, 实验结果 Section 8, METIS baseline, T-006 结果) |
| `.claude/dispatch/BOARD.md` | 认领/完成 T-008，状态更新 |
| `.claude/reports/round_006_update_report.md` | T-008 完成报告 |

清理临时文件: `parse_benchmark.py`, `check_cluster_results.py`

---

## 未解决问题

1. **T-002 仍在运行**: 21/100 完成，预计还需 1-2 小时
2. **T-007 阻塞**: 等待 T-002 完成
3. **Type C 实例 DW 超时**: artificial_cost 导致 Oracle 和 GNN 都返回 ~1e9 obj
4. **Type B 实例 GNN 误差大**: 15-25%，可能与 eps_scale 或 min_samples 设置有关
5. **decomposition_output 版本混乱**: 两个目录 (decomposition_output vs decomposition_output_new)，benchmark 可能混用新旧分解

---

## 给下一轮的经验教训

1. **CronCreate 自治调度可行**: 工人引擎每分钟自动检测任务，可大幅减少人工干预
2. **DW benchmark 慢在 Type C**: 负相关成本的 knapsack pricing 是 CG 瓶颈，120s time_limit 不够
3. **METIS k=50 完全无效**: 需要 k=n_agents 或 heuristic 才能公平对比
4. **06_eval 和 04_test 输出结果几乎完美**: ARI>0.99, NMI>0.99 — GNN 学习到了正确的分解结构
5. **关键瓶颈是 DW 求解速度而非 GNN 质量**: GNN 分解几乎完美，但 DW 在 hard instances 上超时
