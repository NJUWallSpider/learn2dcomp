# round_053: Decomposition Scientist v7 Metric Paradigm Shift

## 做了什么

- **写 `knowledge/decomposition/analysis_003_metric_paradigm_shift.md`**：完整记录 DW status → obj gap to Gurobi 的 metric 范式转移。旧 metric（DW MIP Status = OPTIMAL）被 bench001 证明完全误导——"100% 求解率"下 GNN median obj 是 Gurobi 的 117x。新 metric：(DW_obj - Gurobi_obj) / Gurobi_obj ≤ 5%。
- **重建 `knowledge/hypotheses/INDEX.md`**：HYP-001~005 全部标记为 deprecated（基于 DW status metric）。新建 v7 era 三个假设。
- **创建 HYP-006** (conf=0.80)：DW Solver CG 容量是最大瓶颈 — Oracle 仅 15% @ cg=40。
- **创建 HYP-007** (conf=0.60)：GNN DW FAILED 率是区分分解质量的关键指标 — 7/21 vs Oracle 1/21。
- **创建 HYP-008** (conf=0.55)：P0 解耦消息传递在 Oracle-solvable 实例上匹配 Oracle — 13/13 lenient。
- **更新 `knowledge/decomposition/INDEX.md`**：添加 analysis_003 条目，旧分析标记 ⚠️ deprecated。
- **更新 BOARD.md**：Kill Switch 切换到 obj gap baseline，v7 重置计数器。更新 decomposition-scientist 状态。写 dispatch log 汇报。

## 关键数据

```
Old metric (DW status): Oracle "100%", GNN "100%"
New metric (obj gap ≤5%): Oracle 15% (15/97), GNN 4% (4/97)

Per-Type Oracle obj≤5%:
Type A: 30%, Type B: 20%, Type C: 15%, Type D: 12%, Type E: 0%

T-007 (cg=100, 21 inst):
Oracle lenient: 13/21 (62%), Oracle strict: 1/21 (5%)
GNN lenient: 13/21 (62%), GNN strict: 1/21 (5%)
GNN DW FAILED: 7/21 vs Oracle 1/21
```

## 根因层次

L1: max_cg_iterations=40 是根本瓶颈 → 即使完美分解也 85% 无法收敛
L2: Oracle 在 cg=100 下 lenient 从 15% 跃升到 ~63% → 但 strict 仍仅 5%
L3: GNN 在 Oracle-solvable 实例上匹配 Oracle → 但 DW FAILED 率 7x → 分解结构更脆弱

## 未解决问题

- results.parquet 需要以 obj gap metric 重建（当前 300 行基于 DW status，不可靠）
- FAM-001~005 实例分类学需要 obj gap 下重新分类（Type E 从"最容易"变为 Oracle 0%）
- HYP-001 需要在 obj gap metric 下重新验证
- 全量 100 实例 cg=100 benchmark 需要 unrestricted Gurobi license
- Solver Alignment Score 需要基于 obj gap 数据重新计算

## 给下一轮的经验教训

- DW status = OPTIMAL 只表示 "MIP 在当前可用列上找到最优解"，与全局最优无关。任何依赖此指标的结论都需要重新验证。
- CG 40 轮在 100-task 实例上严重不足。即使 Oracle 分解也需要 CG 100+ 轮。
- Type E（最大规模实例）CG 收敛最差（Oracle 0%）——之前被 DW status 掩盖。
- bench001 的 obj gap 数据目前只有 aggregate，需要 per-instance obj gap 值才能更新 results.parquet。
