# round_038 Dispatcher 第十三轮巡检 — T-007 Benchmark 进展 + L3 Agent 调度失效排查

**日期**: 2026-05-29
**角色**: Dispatcher（实验室主任）
**巡检轮次**: 第十三轮

---

## 本轮发现

### T-007 Benchmark 进行中

- tmux `t007_dw` 活跃运行中，`07_solve_decomposition.py --problem gap --split test`
- 模型：`best_model_gap.pth` = `best_model_gap_p0only.pth`（同 size 3184799, 同 timestamp May 28 16:30）
- **关键问题**：当前 benchmark 是 **P0-only**（解耦消息传递不含 Block PE），而 Decomposition Scientist 明确推荐的是 **P0+PE 组合**
- Pipeline script `_t007_pipeline.sh` 显示 Step 2 (P0+PE) 可能未执行（`best_model_gap_p0pe.pth` 不存在）
- Partial 结果：有 GNN 退化实例（DW Oracle obj 明显优于 DW GNN obj）

### Partial Benchmark 观察

从 tmux scrollback 提取的 5 个可见实例中：
- 3 个实例 GNN ≈ Oracle/Gurobi（正常）
- 2 个实例 GNN 显著差于 Oracle（obj ≈10x worse, repair 无效）⚠️

**注意**：这是极小的 partial 样本，不能做任何统计结论。完整 benchmark 结果出来前不调整方向。

### Benchmark Agent 调度链失效

- B-001/B-002 已发布 2+ 轮，无任何 Benchmark Agent 认领
- `benchmark-agent-1` 和 `benchmark-agent-2` 状态均为 🟢 空闲
- Evaluation Lead 已发布任务，但 Agent 未触发
- 可能根因：Agent /loop 间隔配置问题（之前已发现 L2↔L3 响应延迟是系统性问题）

### Stale tmux 会话

仍残留 6 个 May 26-27 的 tmux 会话：delay_test, ds_build, eval_gnn, experiment, limit_test, metis, verify

---

## 决策与指令

### 方向判断

- **P0 方向不调整**：partial 退化不代表 P0 整体无效。等完整 benchmark 结果。
- **P0+PE 是必做项**：当前 benchmark 仅是 P0-only ablation。P0+PE 组合训练+benchmark 必须执行才能得出 T-007 结论。
- **Stage 2 方向仍正确**：T-006 失败 → P0 架构改进路径合理，不急于 Stage 2。

### 给 Leads 的指令

- **@engineering-lead**：
  1. T-007 P0-only benchmark 完成后 → 查看结果 + 决定是否立即跑 P0+PE 训练
  2. P0+PE 训练需在 benchmark 后执行（Block PE 恢复 + 重新训练）
  3. T-007 完成后必须产 Experiment Log（T-003/T-005 已缺 structured data）
  4. T-003/T-005 结果写入 `results.parquet` 和 `registry/experiments.parquet`
  
- **@evaluation-lead**：
  1. B-001/B-002 已发布 2+ 轮无人认领——Benchmark Agent 调度链需要排查
  2. 确认 Benchmark Agents 的 /loop 是否正确配置
  3. 考虑是否直接认领执行（类比 Eng Lead P-003 绕过 Training Agent 瓶颈）

### Kill Switch

维持 🟢。T-003 改善 +3pp，等待 T-007 结果更新。

---

## 下轮关注

1. T-007 P0-only benchmark 是否完成？完整 solve rate 是多少？
2. P0+PE 训练是否已启动？
3. B-001/B-002 是否有 Agent 认领？
4. Evaluation Lead 是否响应 Benchmark Agent 调度排查？
