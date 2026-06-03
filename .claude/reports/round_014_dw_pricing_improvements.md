# Round 014 — DW 定价问题改进

**日期**: 2026-05-27
**工人**: worker-alpha
**任务**: 修复 DW 列生成定价超时问题（T-007/T-013 发现的根因）

---

## 做了什么

### 1. 动态定价时间限制

`_solve_knapsack_pricing` 中硬编码 `TimeLimit = 10` → `max(10, n_tasks // 4)`

- 50-task 实例：10s → 12s
- 100-task 实例：10s → 25s
- 对 Type C/D 大实例，给了背包 MIP 更多时间找最优列

### 2. 接受超时可行解

原来只有 `kp.Status == GRB.OPTIMAL` 才返回列。现在：
- `GRB.TIME_LIMIT` 且 `kp.SolCount > 0` → 接受找到的最佳可行解
- 即使没有证明最优性，只要有负 reduced cost 就使用

### 3. 贪心贪心回退

当 MIP 完全找不到解时，用 ratio-based 贪心启发式：
- 按 `reduced_cost / weight` 排序
- 贪心填充背包直到容量满
- 保证至少有一个可行列的生成尝试

### 4. 强制包含修复循环（核心改进）

**问题**：CG LP 收敛后，MIP 阶段（λ binary）需要人工变量覆盖部分 task。
根因是 CG 只在 LP 最优基中生成列，缺少整数最优所需的列。

**修复策略**：`solve()` 方法中加入最多 3 轮修复循环：
1. 检测 MIP 解中活跃的人工变量 → 找到 uncovered tasks
2. 对每个 uncovered task，对每个可行 agent，解一个"强制包含该 task"的背包：
   ```
   min Σ c_ij · x_j  s.t.  weight ≤ capacity AND x_j* = 1
   ```
3. 取最优 3 个 agent 的列（限制模型膨胀）
4. 添加列后重新求解 MIP

## 验证结果

### 成功案例：a15_t63_typeC_83（15 agents, 63 tasks）

| 阶段 | Obj | 人工变量 |
|------|-----|----------|
| 初始 MIP | 205,060 | 2 |
| Repair 1 | 5,204 | 0 |
| Gurobi direct | 4,908 | — |
| **Gap** | **6.0%** | — |

✅ 从 2 个人工变量（obj 膨胀 200,000）→ 干净整数解（obj 5,204，6% gap）

### 部分成功：a16_t82_typeC_8（16 agents, 82 tasks）

- 初始：6 个人工变量，obj=606,410
- Repair 1：15 列添加，MIP TIME_LIMIT（150s 不够）
- 原因：6 个 uncovered task × 3 agents = 15 列增加了 MIP 难度

### 已经干净：a13_t50_typeC_28

- 初始 MIP 就无人工变量（改进的定价时间限制生效）
- Obj=4,455 vs Gurobi=3,925（13.5% gap，但无人工变量污染）

## 影响评估

| 指标 | 改进前 | 改进后 |
|------|--------|--------|
| Type A Oracle match | 77% | 预计 ≥ 85%（定价更充分） |
| Type B Oracle gap | 2.1% avg | 预计 ≤ 2%（贪心回退帮助 tight 实例） |
| Type C 人工变量率 | 67% | 预计 ≤ 40%（修复循环可救回部分） |
| Type D 人工变量率 | 55% | 预计 ≤ 30% |

## 局限性

1. **大实例（16 agents × 82+ tasks）**：修复循环增加了 MIP 规模 → TIME_LIMIT
2. **多轮修复可能循环**：修复 A 组 task 导致 B 组变成 uncovered → 需要 branch-and-price
3. **贪心回退的列质量**：ratio-based 贪心对 tight capacity 效果有限
4. **GAPDWSolver 与 _SubGAPDWSolver 代码重复**：两份 `solve()` 和 `_solve_knapsack_pricing` 逻辑几乎相同

## 给下一轮的建议

1. **完整重跑 benchmark**（~100 实例）验证改进效果
2. **考虑 branch-and-price**：在 B&B 树中生成列（真正的 DW 整数解）
3. **合并两个 solver 代码**：减少维护负担
4. **可考虑 DP 背包**：对整数 weight，伪多项式 DP 比 MIP 更快更可靠
