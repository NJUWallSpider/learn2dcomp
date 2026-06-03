# Round 034: Decomposition Scientist 第二轮 — T-003/T-005/T-006 分析

## 做了什么

1. **T-003 Block PE 结果分析**：
   - GNN 77%→80% (+3pp overall), Type C 50%→65% (+15pp)
   - GNN 首次追平 Oracle (80% = 80%)
   - Type A/B/D/E 无变化（A/B/E 已近天花板，D 是根本瓶颈）
   - 分析报告：`knowledge/decomposition/analysis_002_T003_T005_T006.md`

2. **T-005 CG Prediction 结果纳入**：
   - Test ρ=0.61 → 验证 Stage 2 关键前提
   - Per-type ρ: Type C 0.80 (最高), Type D 0.50 (最低)
   - 更新 Solver Alignment Scores

3. **T-006 Stage 2 失败分析**：
   - 根因：Moving Target 问题（frozen predictor 分布外失效）
   - 科学价值：不是简单的"调参失败"，是 surrogate optimization 的根本挑战
   - 推荐近期路径：P0 架构改进 + Inference-time candidate selection

4. **假设系统更新**（5 个假设全部刷新）：
   - HYP-001: 0.85→0.90 (+T-005 证据)
   - HYP-002: 0.65→0.60 (Type C 被 Block PE 改善 → 部分修正，Type C/D 需区分)
   - HYP-003: 0.70→0.75 (+T-003 GNN=Oracle 整体)
   - HYP-004 (新增): Block PE 有效性 → 0.70
   - HYP-005 (新增): Naive surrogate 不可行 → 0.65

5. **BOARD.md 更新**：
   - Kill Switch: GNN Solve Rate 改善 +3pp
   - Solver Alignment: 新增 T-005 CG prediction ρ=0.61
   - 调度日志

## 发现的问题

- T-003 bench log (`t003_bench.log`) 包含 92 个实例（含 a16_*），与 T-003 报告声称的 100 实例不一致
- Per-instance 精细数据采集困难——bench log 格式与 T-002 CSV 不同，需要专门的解析器
- Kill Switch 中 CG Iterations / LP Gap / Runtime 的 per-instance 数据需要从 T-003 bench log 正确解析后才能更新

## 未解决的问题

1. 图结构指标（modularity, conductance, spectral_gap）仍未采集
2. Per-instance T-003 vs T-002 对比无法完成（bench log 格式兼容性问题）
3. Type D 瓶颈（50% 求解率）尚无有效解决方案——需要新的分解范式
4. T-007 (P0 解耦消息传递) 仍在训练中（Epoch 24/50）→ 结果待分析

## 给下一轮的经验

- T-003 bench log 的解析难度说明了需要标准化的 benchmark 输出格式（CSV/parquet 而非纯文本 log）
- Type C 改善 (+15pp) 证明架构改进比单纯的 label accuracy 优化更有效——这与 HYP-002 修正方向一致
- T-006 失败不是无用的——它提供了 "什么方法不可行" 的关键信息，对 Engineering Lead 的方案设计有指导价值
- 下一轮重点：T-007 结果分析 + 图结构指标采集
