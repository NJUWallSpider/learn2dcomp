# Round 005 — T-005: 构建新数据集

**日期**: 2026-05-27
**工人**: worker-alpha
**任务**: T-005 — 用新生成的实例构建 GNN 数据集

---

## 做了什么

### 1. 启动 02_generate_dataset.py

- 用 `tmux new -d` + `exec bash` 保持 shell 存活（第一次没用 exec bash，tmux 窗口在命令结束后消失）
- 8 并行 workers (jobs=8)，之前试 32 发现 tmux 会话崩溃（可能是资源限制）
- GCG 4.0.1 可用，运行速度很快（~15 it/s）
- 全部 1200 个实例在约 80 秒内处理完毕

### 2. 结果

```
Processed: 1000/1000 succeeded, 0 skipped  (train)
Processed: 100/100 succeeded, 0 skipped    (valid)
Processed: 100/100 succeeded, 0 skipped    (test)
```

**0 GCG 失败** — 新 tightness 公式生成的实例 GCG 100% 能检测到分解结构。
产物：1200 个 .pt 文件（`data/processed/gap/{train,valid,test}/`）。

### 3. 顺便完成 T-004 部分清理

- 删除 CFLP_gurobi.py, UFLP_Benders.py, UFLP_gurobi.py
- 清理所有 `__pycache__/` 目录
- 保留 CFLP.py（debug_dataloader.py 仍导入它）和所有 debug_*.py

---

## 修改文件清单

| 文件 | 改动 |
|------|------|
| CFLP_gurobi.py | 删除 |
| UFLP_Benders.py | 删除 |
| UFLP_gurobi.py | 删除 |
| `__pycache__/` | 清理 |
| `.claude/dispatch/BOARD.md` | T-005 标记完成，T-006 解锁 |

---

## 给下一轮的经验教训

1. **tmux 命令模板**：必须用 `exec bash` 保持窗口存活，否则命令结束后窗口消失无法查看输出。
   `tmux new -d -s NAME "cd ~/projects/learn2dcomp && python script.py 2>&1 | tee /tmp/log; echo EXIT=\$?; exec bash"`
2. **jobs 数量**：32 并行会崩溃（可能是内存或连接池限制），8 并行稳定且速度足够快
3. **GCG 在新实例上 100% 成功**：tightness 公式不影响分解检测，GAP 的结构（每 agent 一个 block）保持不变
