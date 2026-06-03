# Round 016 — Type B Outlier 调查 + report.html 更新

**时间**: 2026-05-30 16:00 CST
**工人**: worker-beta (dispatch 关闭后独立工作)
**任务**: 调查 a14_t79_typeB_42 Oracle-Gurobi gap 31.2% 根因 + 更新 report.html

---

## 执行

1. 修正 report.html 中 T-013 数据错误（a15_t84_typeC_33 和 a15_t78_typeC_18 状态与 round_015 不一致）
2. 写 debug_outlier.py 诊断脚本，在服务器上深入分析 a14_t79_typeB_42
3. 扫描全部 18 个 Type B Oracle OPTIMAL 实例的 gap 分布
4. 更新 report.html 至 Round 016

## 关键发现

### 1. CG-then-MIP Gap — DW 理论局限，非代码 bug

a14_t79_typeB_42 (14 agents × 79 tasks, Type B, tightness 0.50):
- Gurobi Direct: obj=1,165, optimal (0.38s, 51 nodes) — MIP 很简单
- Full LP relaxation: obj=1,106 — integrality gap 仅 5.06%
- DW Oracle: obj=1,529, reports "OPTIMAL" (MIP gap 0.0)
  - CG converged at 68 iterations (all reduced costs ≥ 0)
  - Even with max_cg=500 and time_limit=1200, same result
  - RMP MIP declares optimality because no more columns with negative reduced cost

**根因**: LP 最优时，所有未生成的列都有 non-negative reduced cost，CG 停止。
但 MIP 整数最优解 (1165) 需要的某些列在 LP 最优时有 positive reduced cost —
CG 永远不会生成它们。这是 Dantzig-Wolfe "solve-then-MIP" 的已知局限。

### 2. 第二个 outlier: a13_t85_typeB_67 (13.1% gap)

Type B 共 18 个 Oracle OPTIMAL 实例:
- 2 outliers: a14_t79_typeB_42 (31.2%), a13_t85_typeB_67 (13.1%)
- 8 perfect matches (0.0% gap)
- 中位 gap: 0.74%
- 两个 outlier 都是大实例 (79+ tasks) + Type B (wide range + aggressive tightness)

### 3. Type B 为什么更严重

Type B = costs U[1,100], weights U[1,100], tightness 0.50:
- Wide weight range (1-100) + tight capacity → 每个 agent 只能选 ~2.8 个 task
- LP 可以 fractionally 组合多个 columns per agent → low LP cost
- MIP 必须每个 agent 选一个 column → combinatorial gap 大
- 大实例 (79+ tasks) → 更多组合 → LP-MIP gap 更明显

## report.html 更新

1. 修正 T-013 结果表格（a15_t84_typeC_33 → TIME_LIMIT, a15_t78_typeC_18 → DW 失败 505,911/5 art vars）
2. 更新 meta 日期至 2026-05-30 (Round 015)
3. Type B 行标注 2 个 outliers
4. 新增 8.7 节: Type B Outlier CG-then-MIP Gap 详细分析
5. 更新 8.8 节 (原 8.7): METIS Baseline
6. 更新第 9 章核心结论和剩余问题

## 未解决问题

- **Type C DW 失败**: 0/8 干净求解 — 需 longer pricing time 或 column stabilization
- **Type D TIME_LIMIT (50%)**: 调查确认大实例 (67-100 tasks) MIP phase 在 120s 内无法找到可行解。即使延长至 600s + mip_gap=1%，MIP 仍 TIME_LIMIT。Gurobi 受限 license 可能有模型大小限制。10/10 小实例 (42-62 tasks) OPTIMAL (0.6-57s)
- **T-002 剩余 35 实例**: OOM crash 未跑完
- **DW 改进方向**: branch-and-price, multiple pricing, initial column diversity
- **GNN 训练 plateau**: epoch ~10 收敛

## 经验教训

- **MIP gap=0.0 不代表真实最优**: DW RMP 的 MIP gap 只衡量 MIP vs RMP LP bound，不衡量 MIP vs 真实最优
- **Type B tightness=0.50 可能是双刃剑**: 成功制造了困难实例，但在 DW 中引发了 CG-then-MIP gap
- **不要相信 "OPTIMAL" 状态**: 需要与 Gurobi Direct 对比才能确认
- **Type D 大实例 DW 不可行**: 67+ tasks 的 Type D 实例 MIP RMP 太大，受限 license 下无法在合理时间内求解
