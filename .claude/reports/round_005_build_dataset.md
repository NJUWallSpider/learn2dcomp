# Round 005 — T-005: 构建新数据集

**日期**: 2026-05-27
**工人**: worker-alpha（接手 delta 的关键路径任务）
**任务**: T-005 — 用新实例构建数据集（LP→MPS→GCG→.pt）

---

## 做了什么

### 1. 清理旧数据

- 之前 worker-delta 启动了两个并行的 `dataset` tmux 会话（11:46 CST），产生了 1998 个 .pt 文件（应为 1000）
- 清理了 `data/processed/gap`、`data/mps/gap`、`data/decompositions/gap`

### 2. 重新构建数据集

- 单一 tmux 会话 `ds_build`，使用 `/opt/miniconda3/bin/python`
- 命令：`python 02_generate_dataset.py --problem gap --jobs 32`
- 结果：**三个 split 全部 100% 成功，零 GCG 失败**

| Split | 实例数 | 结果 |
|-------|--------|------|
| train | 1000 | 1000/1000 succeeded |
| valid | 100 | 100/1000 succeeded |
| test | 100 | 100/100 succeeded |

### 3. 输出验证

- MPS 文件：1200 个（data/mps/gap/{train,valid,test}/）
- GCG .dec 文件：1200 个（data/decompositions/gap/{train,valid,test}/）
- .pt HeteroData 文件：1200 个（data/processed/gap/{train,valid,test}/）
- 抽样验证：variable.x shape 正确（n_agents × n_tasks, 24 dims），labels 由 GCG 分解生成

---

## 未解决问题

1. **T-006 待执行**：worker-beta 仍在 T-003（GNN Oracle mismatch 调查），T-006（重新训练 GNN）是下一瓶颈
2. **T-003 调查应优先于 T-006 训练**：先修复 GNN 的问题再训练更有意义

---

## 给下一轮的经验教训

1. **不要启动重复的 tmux 会话**：上次两个并行 session 导致输出文件翻倍（1998 vs 1000）
2. **GCG 对新 tightness 实例的分解成功率 100%**：说明 tightness 公式不影响 GCG 的分解检测能力
3. **关键路径推进**：现在 T-001→T-005 已完成，只剩 T-006→T-007
4. **Python 路径**：必须用 `/opt/miniconda3/bin/python`（含 torch, torch_geometric, numpy, gurobipy）
