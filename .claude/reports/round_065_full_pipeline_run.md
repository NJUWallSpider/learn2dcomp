# round_065: 全流水线自主运行

## 做了什么

串行跑了完整 7 步流水线（01→02→03→06→07），输出到 results/gap_dw_results.csv。

## 结果

| 步骤 | 耗时 | 结果 |
|------|------|------|
| 01 生成实例 | <30s | 1200 LP (1000 train + 100 valid + 100 test) |
| 02 构建数据集 | ~15min | 1200 .pt，32 并行 GCG labeling |
| 03 训练 GNN | ~125min | 50 epoch，Train 8.68 / Val 8.78，epoch 15 后完全收敛 |
| 06 生成分解 | 7s | 100 test instances |
| 07 三路求解 | ~100min | 见下 |

### 07 三路对比（100 test instances, time_limit=300s）

| | SCIP direct | GCG auto | GCG GNN |
|---|---|---|---|
| 求解数 | 100 | 100 | 100 |
| 平均 Obj | 2551.1 | 2548.6 | 2548.8 |
| 平均时间 | 89.6s | 17.8s | 18.3s |
| 平均 Blocks | - | 14.6 | 14.6 |

- GCG 方法比 SCIP 快 ~5x
- GCG GNN 和 GCG auto 几乎持平（Obj 差 0.2，时间多 0.5s）
- 个别硬实例上 SCIP 超时（300s），GCG 方法在 10-30s 内到最优（如 instance 97: SCIP 300s/0.05% gap, GCG GNN 28s/optimal）

## 发现的问题

1. **训练慢**：GPU 利用率仅 28%，瓶颈在 CPU 数据加载（HeteroData 反序列化 + batch 合并）。已改 config.py：batch_size 4→8, num_workers 4→16，下次训练生效。
2. **Loss 早收敛**：epoch 15 后 Train/Val Loss 完全持平到 50，early stopping 未触发（patience=15 < 50-15=35）。考虑降低 max_epochs 或调 patience。
3. **GCG GNN ≈ GCG auto**：GNN 学到的分解和 GCG 自动检测几乎一致，说明 GNN 有效复制了 GCG 的行为。

## 待解决

- 训练提速：改参数后需重新跑 03 验证 GPU 利用率是否提升
- GCG GNN 能否超越 GCG auto？需要更难的实例（tightness 改革后的实例尚未生成）
