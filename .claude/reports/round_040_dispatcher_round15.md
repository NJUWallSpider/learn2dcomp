# round_040 Dispatcher 第十五轮巡检 — P0+PE 训练进行中，Benchmark 极慢但存活

**日期**: 2026-05-29
**角色**: Dispatcher（实验室主任）
**巡检轮次**: 第十五轮

---

## 本轮发现

### P0 Benchmark 进展

- 进程存活（PID 157248, 13h CPU），但仅 ~17/100 实例可见于 tmux scrollback
- 输出目标：`results/gap_dw_results_p0.csv`（当前不存在 — 脚本仅在全部完成后写入 CSV）
- 当前实例：`a14_t73_typeA_91`（正在读取 MPS）
- 速度显著偏慢但进程未卡死

### P0+PE 训练进展

- tmux `t007_pe_train`，epoch 35/50
- **Loss 完全平坦**：Train Loss 4.3395, Val Loss 4.3909（epoch 25-35 无变化）
- 与 T-003 baseline 的 SupCon loss（~4.35）持平
- ⚠️ 训练 loss 层面 P0 架构未显示任何优势

### Engineering Lead 响应活跃

- 已按 Round 13-14 指令启动 P0+PE 训练
- BOARD.md 由 Eng Lead 自行更新（epoch 25, loss 4.3395）
- L3 Agent 绕过模式确立：Lead 直接执行替代 Agent 调度

### 角色状态

| 角色 | 新输出？ | 状态 |
|------|----------|------|
| Engineering Lead | ✅ BOARD 更新 | P0+PE training 进行中 |
| Research Lead | — | 待命（1 天无输出） |
| Evaluation Lead | — | 待命（无新报告） |
| Decomposition Scientist | — | 待命（等 T-007 结果） |
| All L3 Agents | — | 空闲/名义活跃 |

---

## 决策

### Kill Switch
🟢 维持。等待 T-007 结果更新 Kill Switch 表。

### 方向判断

1. **P0 训练 loss 平坦 ≠ P0 无效**。SupCon loss 衡量的是 embedding 与 GCG label 的一致性，不是分解质量。P0 的解耦消息传递可能学到不同的 embedding 结构（var↔var homophilic 通道），这种结构差异不会体现在 SupCon loss 中，但可能体现在聚类后的分解结构上。**DW solve rate 是唯一有效的判断标准**。

2. **P0 benchmark 极慢但不宜干预**。进程存活，可能因大实例（t90-t100）导致。干预风险（kill + 重跑）高于等待风险（多等几小时）。

3. **P0 vs P0+PE vs T-003 三向对比是 T-007 完成后必需的分析**。仅 P0-only 或仅 P0+PE 不够 — 需要知道解耦消息传递和 Block PE 各自贡献了多少。

### 指令

- **@engineering-lead**：
  1. P0+PE 训练完成后直接启动 P0+PE benchmark（无需等 Dispatcher）
  2. 所有 benchmark 完成后输出三向对比表（P0-only vs P0+PE vs T-003）
  3. P0 benchmark 的 `gap_dw_results_p0.csv` 写入后通知 Dispatcher

---

## 下轮关注

1. P0 benchmark 是否完成？
2. P0+PE 训练是否完成（epoch 50/50）？
3. P0+PE benchmark 是否已启动？
4. 是否有 Benchmark Agent 认领 B-001/B-002？
