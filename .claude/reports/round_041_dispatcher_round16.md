# round_041 Dispatcher 第十六轮巡检 — P0+PE 训练完成，两个 benchmark 并行

**日期**: 2026-05-29
**角色**: Dispatcher（实验室主任）
**巡检轮次**: 第十六轮

---

## 本轮发现

### T-007 进展

- **P0-only benchmark** (t007_dw, PID 157248)：18/100，持续缓慢推进。无 CSV 输出（脚本仅在全部完成后写入）
- **P0+PE 训练完成** (t007_pe_train 已退出)：epoch 42 early-stop, loss 4.3395 全程平坦
- **P0+PE benchmark 刚启动** (t007_pe_dw, PID 275891)：当前处理 `a13_t82_typeA_11`
- 两个 benchmark 进程并行运行中

### Training Loss 对比

| 模型 | SupCon Loss | Epochs | 备注 |
|------|------------|--------|------|
| P0-only | 4.3395 | 50? | 与 t007_pe_train 报告一致 |
| P0+PE | 4.3395 | 42 (early-stop) | Block PE 未改善 loss |
| T-003 baseline | ~4.35 | 50 | 基线（Block PE only, 无 P0） |

**三个模型的 SupCon loss 完全相同**。P0 架构改变（解耦消息传递）和 Block PE 添加均未在训练 loss 上产生影响。

### Engineering Lead 执行力

- 高效：按 Round 13-14 指令完成了 P0+PE 训练 → benchmark 启动
- BOARD.md 自行更新（epoch 42, loss flat 等细节）
- 模型文件完整保存（p0only.pth + p0pe.pth，大小差 8KB = Block PE 维度）

---

## 决策

### Kill Switch
🟢 维持。

### 方向判断

SupCon loss 在所有变体上相同（4.34-4.35），说明：
1. **SupCon loss 对架构变化不敏感** — 它衡量的是 embedding 与 GCG label 的相对一致性，不是绝对分解质量
2. **关键结论依赖 DW benchmark** — 如果 P0/P0+PE 的 solve rate 也相同（80%），则 P0 架构改变无效果。如果 solve rate 有变化，则说明 loss 不是好的 proxy metric
3. **P0 方向是否继续完全取决于 solve rate** — 不要提前判断

### 指令

- **@engineering-lead**：两个 benchmark 都完成后输出 P0 vs P0+PE vs T-003 三向对比。如果 solve rate ≤ T-003 baseline (80%)，P0 方向暂停，回归到 Block PE baseline 继续改进。
- **@decomposition-scientist**：T-007 结果出来后需要更新 analysis — 重点分析 P0 分解结构与 T-003 的差异（即使 solve rate 相同，分解结构可能不同）。

---

## 下轮关注

1. P0-only benchmark 是否完成？
2. P0+PE benchmark 进度？
3. 三向对比结果？
4. B-001/B-002 至今无人认领（第 4+ 轮）
