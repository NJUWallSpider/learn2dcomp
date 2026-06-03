# round_035_dispatcher_round2_phase1_launch

**日期**: 2026-05-28
**角色**: Dispatcher（实验室主任）
**巡检轮次**: 第二轮

---

## 本轮发现

### 三家产出高度收敛

Research Lead、Engineering Lead、Decomposition Scientist 三家独立分析收敛于同一结论：

1. **Stage 1 已收敛**：GNN ≈ Oracle 在共同求解实例上（0.99x RT, CG diff=0）
2. **瓶颈在 Type C/D**：Oracle solve rate 仅 50-55%（Teacher Ceiling 限制）
3. **cg_iterations 是 Runtime surrogate**：ρ=0.64 (Oracle)
4. **heterophily 盲区是架构缺口**：缺少 var↔var homophilic 通道
5. **n_blocks 是噪声**：ρ≈0.05，不应作为优化目标

### knowledge/ 大幅充实

从空壳变为有实际内容：decisions/(5), decomposition/(3), failures/(5), hypotheses/(3), instances/(5), papers/(3)。

---

## 决策

### 提案审批
- **P-001 (research-lead)**: 批准。3 方向按 Engineering Lead 的 3-Phase 排序：Phase 1 执行 P1+P2，Phase 2 执行 P0。
- **P-002 (decomposition-scientist)**: 有条件批准。授权 Stage 2 准备工作，完整启动需等 Phase 1 结果 + CG 可预测性验证。

### 方向指令
- @engineering-lead: Phase 1 — T-003 (Block PE) + T-004 (Contrastive Loss) + T-005 (CG Prediction)，3 并行实验
- @decomposition-scientist: 采集图结构指标 + CG Telemetry pipeline
- @evaluation-lead: 首次激活 — 独立验证 T-002 基线可信度
- @research-lead: 待命，等 Phase 1 实验结果

### Kill Switch
全绿，基线刚建立。Column Diversity 仍待采集。

---

## 未完成/下轮关注

1. Evaluation Lead 的 Validity Report — 是否发现基线数据问题？
2. Engineering Lead 是否下发了 T-003/T-004/T-005？
3. Column Diversity telemetry 是否完成？
4. Phase 1 实验是否有显著改善（Type C/D solve rate ≥5pp）？
