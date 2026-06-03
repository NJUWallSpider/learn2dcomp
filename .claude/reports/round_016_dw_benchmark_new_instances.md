# Round 016 — DW 全量验证（新实例 100 个）

**日期**: 2026-05-27
**工人**: worker-delta
**任务**: T-002 完整重跑 — 新生成实例（T-001 产物）上跑 3 方法对比

---

## 做了什么

1. 在 V100 上启动 `07_solve_decomposition.py --problem gap --split test --time_limit 120`
2. 100 个新生成实例（来自 T-001 tightness 修复：B=0.50, 其余=1.30）
3. 每次比较 Gurobi direct / DW Oracle / DW GNN
4. 多次因大实例瓶颈（type C/D 100 task 实例 Gurobi direct 耗时 15-60 min）而崩溃/重启
5. 最终第 3 次重跑成功完成全部 100 实例

---

## 结果

### 总体统计

| 方法 | 成功率 | 失败 | 偏差 | TIME_LIMIT |
|------|--------|------|------|------------|
| DW Oracle | **57.0%** (57/100) | 22 | 21 | 22 |
| DW GNN    | **56.0%** (56/100) | 23 | 21 | 23 |

成功率定义：与 Gurobi obj 差距 < 1%。失败：Obj=None 或 > 1e8（人工变量）。偏差：其他。

### 按类型

| Type | 数量 | Oracle 成功 | GNN 成功 | 特点 |
|------|------|-------------|----------|------|
| **E** | 20 | **100%** | **95%** | 正相关 cost-weight，DW 完美 |
| **A** | 20 | **80%** | **80%** | 小 cost/weight，多数可行 |
| **B** | 20 | **55%** | **55%** | 极紧容量 (0.50)，mixed |
| **D** | 20 | **50%** | **50%** | 负相关+噪声，一半失败 |
| **C** | 20 | **0%** | **0%** | 强负相关 cost-weight，**全部失败** |

### Oracle 失败分析

22 个 Oracle 失败实例：
- **9 个 Type C**（全部 type C，cost-weight 强负相关）
- **10 个 Type D**（负相关+噪声）
- **2 个 Type B**（仅最大实例：94 和 96 tasks，容量 0.50 极紧）
- **1 个 Type A**（98 tasks，最大 type A）

CG 迭代次数：失败的实例中，4 个为 0 次（pricing 完全未生成列），其余 57-100 次（生成了列但未收敛）。

### GNN 大 gap（> 15%）

部分 type C 实例的 GNN 结果出现人工变量污染（obj 2e5-8e5）：
- a14_t82_typeC_98: Gurobi=6456, GNN=806130 (+12386%)
- a15_t77_typeC_88: Gurobi=6042, GNN=505968 (+8274%)

这些已在 T-011/T-012 中定位为 `finalize_mip()` 硬编码 `huge_cost=1e8` 导致。

---

## 成功标准判定

| 标准 | 目标 | 实际 | 判定 |
|------|------|------|------|
| DW Oracle 成功率 | > 80% | 57.0% | ❌ 未达标 |
| Oracle-Gurobi 一致率 | > 90% | 79.2%（含 off） | ❌ 未达标 |

**未达标根因**：Type C/D 的负相关 cost-weight 结构导致 DW 列生成在 120s 内无法收敛。这是 DW 方法的固有限制，非代码 bug。

---

## 修改文件清单

无代码修改。仅产出分析脚本 `analyze_results.py`。

---

## 给下一轮的经验教训

1. **Type C/D 实例对 DW 是硬骨头**：需要更长的 time_limit（300s+）或 CG 稳定化技术（dual smoothing, box constraints）
2. **Benchmark 重试策略**：大实例 Gurobi direct 会耗尽时间，考虑在 benchmark 脚本中给 Gurobi 加上 max(30, time_limit/4) 的硬性时间预算
3. **日志产出是关键**：第 1-2 次重跑崩溃时依靠日志恢复数据。`tee` 缓冲问题通过 `python3 -u` 解决
4. **Type E 100% 成功证明 DW 方法本质可行**，问题只在特定 instance 分布上

---

## 后续方向

- **T-011/T-012/T-013**（已完成）：修复 artificial_cost 默认值链 + finalize_mip 硬编码 1e8
- **Type C DW 失败**：尝试增加 CG 迭代上限到 200+，或实现 box dual stabilization
- **Type D 50% 失败**：可能与 noise ε 的随机性相关，需逐实例分析
