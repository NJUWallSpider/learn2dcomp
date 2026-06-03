# Round 033: Decomposition Scientist 首轮分析 — Stage 1 基线建立

## 做了什么

1. **初始化结构化科学数据库**：
   - `results.parquet`: 从 `gap_dw_results.csv` 构建，300 rows（100 实例 × 3 方法），含 instance_id, method, instance_type, n_blocks, cg_iterations, runtime, lp_gap, bp_nodes, status, tightness
   - `registry/experiments.parquet`: T-002 实验元数据
   - 脚本：`_init_results_db.py`, `_rebuild_results.py`（临时，分析完成后删除）

2. **T-002 基线分解分析** (`knowledge/decomposition/analysis_001_baseline_t002.md`)：
   - 5 个关键发现（详见报告）
   - 核心结论：GNN ≈ Oracle 在成功实例上（0.99x runtime ratio, CG diff=0）→ Stage 1 已收敛
   - Type C/D 瓶颈：Oracle 仅 50-55% 求解率 → Teacher Ceiling

3. **因果假设系统** (HYP-001/002/003)：
   - HYP-001: cg_iterations 预测 runtime (ρ=0.64 Oracle) — 置信度 0.85 (已确认)
   - HYP-002: Type C/D 需要质变 — 置信度 0.65
   - HYP-003: GNN 在成功实例上 = Oracle — 置信度 0.70

4. **实例分类学** (FAM-001~005)：
   - FAM-001 (Type A): 95% solve, 简单
   - FAM-002 (Type B): 90% solve, 中等
   - FAM-003 (Type C): 55% solve, 瓶颈 ← 最需要研究
   - FAM-004 (Type D): 50% solve, 最高难度
   - FAM-005 (Type E): 100% solve, 最简单

5. **Solver Alignment Score** (`knowledge/decomposition/alignment_scores.md`)：
   - 首次计算完成
   - cg_iterations: 🟢 高对齐 (ρ=0.64)
   - n_blocks: 🔴 低对齐 (ρ≈0.05) — 不应作为优化目标

6. **BOARD.md 更新**：
   - Kill Switch 状态表：基线建立
   - Solver Alignment Dashboard：填入实际数据
   - Proposal P-002：启动 Stage 2 试点
   - 调度日志

## 发现的问题

- Oracle runtime 在 t002_parsed_results.csv 中缺失（仅 TIME_LIMIT 实例有值），需要从 gap_dw_results.csv 获取完整数据
- 图结构指标（modularity, conductance, spectral_gap）全部缺失 → 无法分析"什么结构特征决定求解难度"
- Column diversity, pricing_success_rate 等 solver dynamics 指标缺失 → 需要 Solver Telemetry

## 未解决的问题

1. 图结构指标尚未采集 → 需要写一个计算脚本，对 100 个 MPS 实例计算 modularity/conductance/spectral_gap
2. Solver Telemetry 尚未采集 → CG trace / B&P trace 无数据
3. train_accuracy（GNN 对 GCG label 的准确率）尚未计算 → 无法验证 alignment(accuracy, runtime)
4. Type C/D 实例的根因分析尚未进行 — 为什么 Oracle 在这些实例上失败？

## 给下一轮的经验

- gap_dw_results.csv（100 实例完整数据）是比 t002_parsed_results.csv（65 实例精简版）更好的数据源
- cg_iterations 的 alignment 极高（per-type ρ 在 0.55-0.96 之间）→ 这是最可靠的 surrogate metric
- n_blocks 完全不能预测 runtime → 不要把"优化块数量"作为目标
- GNN 和 Oracle 在共同成功实例上表现几乎相同 → 改进 GNN 的重点应该是"让更多实例成功"而非"让成功实例更快"
