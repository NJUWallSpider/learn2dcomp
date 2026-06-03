# Round 006 — T-006: 重新训练 GNN

**日期**: 2026-05-27
**工人**: worker-alpha（接手 beta 的关键路径任务）
**任务**: T-006 — 用新数据集训练 GraphTransformer + SupCon

---

## 训练结果

### 配置
- 设备：Tesla V100-PCIE-32GB (CUDA)
- 模型：GraphTransformer (hidden_dim=128, num_layers=3)
- 损失：SupCon (temperature=0.3, per-instance)
- 优化器：Adam (lr=0.001) + ReduceLROnPlateau (factor=0.5, patience=5)
- 训练集：1000 实例，batch_size=4，num_workers=4
- 验证集：100 实例

### Loss 曲线

| 阶段 | Train Loss | Val Loss |
|------|-----------|----------|
| Epoch 1 | 4.7849 | 4.4570 |
| Epoch 8 | 4.3487 | 4.3947 |
| Epoch 21 (best) | 4.3396 | 4.3910 |
| Epoch 50 (final) | 4.3395 | 4.3909 |

- **收敛**：Loss 从 4.78 降至 4.34 (train)，验证从 4.46 降至 4.39
- **无 early stop**：val loss 从 epoch 21 到 50 几乎不变（4.3909-4.3910），耐心值 15 但 loss 未恶化
- **模型保存**：`models/best_model_gap.pth` (1.8 MB)

### 问题

- Val loss 的 plateau 非常平坦（epoch 21-50 几乎不变），可能是 batch_size=4 导致梯度噪声大
- Train loss 与 val loss 差距小（4.34 vs 4.39），说明无过拟合

---

## 项目状态总结

**已完成**：T-001, T-003, T-004, T-005, T-006, T-008
**阻塞**：T-002 (DW benchmark 崩溃，delta 修复中)
**阻塞于 T-002**：T-007

---

## 给下一轮的经验教训

1. **训练在 21 epoch 后达到最佳**：未来可降低 max_epochs 到 25 或增加 patience 到 20
2. **关键路径只剩最后一步**：T-007 等待 T-002 完成。如果 delta 无法修复 T-002，可考虑跳过旧实例验证，直接用新实例+MPS跑 T-007
3. **tmux 会话管理**：训练完成后 tmux 自动退出，日志存于 /tmp/train_gnn.log
