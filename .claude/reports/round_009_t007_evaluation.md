# Round 009 — T-007: 全流程评估

**日期**: 2026-05-27
**工人**: worker-alpha
**任务**: T-007 — 新实例 → 新模型 → DW 求解 → 对比 Gurobi

---

## 执行的步骤

1. `04_test.py` — GNN 聚类评估（ARI 0.9914, PCR 0.98）
2. `06_eval_instances.py` — 生成 100 个 decomposition JSON
3. `05_visualize_embeddings.py` — t-SNE 可视化
4. `quick_dw_eval.py` — 20 实例快速 DW 评估（被杀，太慢）
5. `07_solve_decomposition.py --time_limit 120` — 全量 100 实例 DW 基准（跑了 64/100 后被杀，太慢）

---

## DW 基准测试结果（64 实例）

### Type A（Easy, tightness=1.30）：13 实例

| 指标 | 值 |
|------|-----|
| Oracle 匹配率 | 10/13 (77%) |
| 平均 Oracle gap | 0.3% |
| 最大 Oracle gap | 1.6% |
| GNN = Oracle | ✅ 13/13 |

### Type B（Tight, tightness=0.50）：13 实例

| 指标 | 值 |
|------|-----|
| Oracle 匹配率 | 5/11 (45%)，2 实例人工变量污染 |
| 平均 Oracle gap | 2.1% |
| 最大 Oracle gap | 13.1% |
| GNN = Oracle | ✅ 13/13 |

### Type C（Hard, tightness=1.30）：12 实例

| 指标 | 值 |
|------|-----|
| Oracle 匹配率 | 0/4 (0%)，8 实例人工变量污染 |
| 平均 Oracle gap | 4.9%（排除人工变量失败的） |
| 最大 Oracle gap | 13.5% |
| 人工变量失败 | 8/12 (67%) |
| TIME_LIMIT 失败 | 部分 |
| GNN = Oracle | ✅ 12/12 |

### Type D（Hard, tightness=1.30）：11 实例

| 指标 | 值 |
|------|-----|
| Oracle 匹配率 | 0/5 (0%)，6 实例人工变量污染 |
| 平均 Oracle gap | 0.6%（排除人工变量失败的） |
| 人工变量失败 | 6/11 (55%) |
| TIME_LIMIT 失败 | 部分 |
| GNN = Oracle | ✅ 11/11 |

### Type E（Easy, tightness=1.30）：15 实例

| 指标 | 值 |
|------|-----|
| Oracle 匹配率 | 14/15 (93%) |
| 平均 Oracle gap | 0.0% |
| 最大 Oracle gap | 0.5% |
| GNN = Oracle | ✅ 15/15 |

---

## 核心发现

### 1. GNN 分解质量：优秀

- **GNN 分解结果始终等于 Oracle 分解结果**（所有 64 实例中 GNN ≈ Oracle）
- 聚类指标优秀：ARI 0.99, PCR 0.98
- t-SNE 可视化显示清晰的 agent 聚类结构
- GNN 的分解生成管线（04_test → 06_eval → DW）已经端到端跑通

### 2. DW 求解器问题严重（三种失败模式）

**模式 1：人工变量污染（最常见）**
- CG 未能生成足够列覆盖所有任务
- MIP 阶段被迫使用人工变量（obj=1e8）
- 结果：Oracle obj = X × 1e8 + 真实成本，完全无用
- 主要影响 Type C (67%) 和 Type D (55%)

**模式 2：RMP MIP 超时（time_limit=120/300）**
- CG 完成后，MIP 阶段无法在规定时间内找到整数最优解
- Oracle 返回 None
- 主要影响 Type C/D

**模式 3：定价问题超时（10 秒硬限制）**
- `_solve_knapsack_pricing` 中 `kp.Params.TimeLimit = 10`
- 对于 tight 实例（Type B/C/D），背包问题 NP-hard，10 秒不够
- CG 提前终止 → 列集不完整 → 次优解或人工变量
- 是模式 1 和模式 2 的根因

### 3. 实例难度与 DW 效果的反比关系

| Type | Tightness | Gurobi Nodes | DW 效果 |
|------|-----------|-------------|---------|
| A | 1.30 | 1.0 (root node) | 优秀 |
| E | 1.30 | 1.0 (root node) | 优秀 |
| B | 0.50 | 多数 1.0 | 一般（1-13% gap） |
| C | 1.30 | 数千到 15 万+ | 差（67% 人工变量失败） |
| D | 1.30 | 数千到 15 万+ | 差（55% 人工变量失败） |

关键洞察：Gurobi 在 Type C/D 上 NodeCount 很大（数万到 15 万+），说明这些实例本身对 branch-and-bound 就很难。DW 并没有降低难度，反而因为定价问题超时变得更差。

---

## 与之前骐达的对比

- 旧实例（α 公式，100% root node 求解）：DW Oracle 成功率 80-90%，GNN 偶尔有偏差
- 新实例（tightness 公式，50% NodeCount>1）：DW 在 Type B/C/D 上显著退化
- GNN 的噪声点问题（T-003 修复的 `reassign_noise_points`）已修复，不再出现 GNN ≠ Oracle

---

## 未解决的问题

1. **DW 求解器定价超时**：10 秒硬限制对 tight 实例不够。需考虑：
   - 动态增加定价时间限制（基于实例规模/tightness）
   - 使用 DP-based 背包求解器（伪多项式，对整数 weights 快）
   - 定价超时时仍返回最佳可行解（当前直接返回 None）
2. **人工变量成本过高**：1e5 → 1e8 → 目标值被毁。可考虑定价失败时的替代策略
3. **全量 100 实例基准未完成**：两个 benchmark 都因太慢被杀。需要先修复定价超时问题再重跑

---

## 给下一轮的经验教训

1. **GNN 管线已就绪**：04_test → 06_eval 的聚类和分解生成 pipeline 运行良好，可以复用
2. **DW 求解器是当前瓶颈**：不是 GNN 的问题，是 DW column generation 的定价效率问题
3. **不要用 300 秒 DW 时间限制**：Type C/D 的 RMP MIP 本身很难，时间限制帮不了定价问题
4. **定价超时 10 秒要调整**：对 100-task Type C 实例，背包至少需要 30-60 秒。或者改为 DP 解法
5. **人工变量策略要重新设计**：当前 1e5→1e8 的两阶段惩罚在定价失败时产生垃圾结果，需要更robust的方案
6. **quick_dw_eval.py、extract_dw_results.py、analyze_decomp.py 应在提交前删除**
