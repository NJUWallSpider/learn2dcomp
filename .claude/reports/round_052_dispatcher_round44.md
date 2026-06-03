# round_052 Dispatcher 第四十四轮巡检 — B-001 报告颠覆核心假设

**日期**: 2026-05-29 | **轮次**: 第四十四轮

---

## 重大发现：B-001 Multi-Seed 报告

Benchmark Agent 1 产出 `bench001_T003_multiseed.md`，使用正确 metric（obj gap to Gurobi Direct）重新评估 T-003：

### 旧 metric（DW status=2）→ 新 metric（obj ≤ 5% Gurobi optimal）

| 方法 | 旧"求解率" | 新求解率 | Median Gap |
|------|-----------|---------|-----------|
| DW Oracle | 100% | **15%** (15/97) | 31.3% |
| DW GNN (T-003) | 100% | **4%** (4/97) | 11,700% |

### 关键结论

1. **"T-003 80% 求解率"是虚假指标** — DW status=OPTIMAL 完全不能衡量分解质量
2. **Type C "+15pp" 改善不成立** — 正确 metric 下 GNN Type C 求解率 = 0%
3. **DW Oracle 本身仅 15% 求解率** — 这是 GNN 的实际天花板
4. **但 B-001 使用 max_cg_iterations=40** — 低于 T-003 原始评估的 100，部分解释了 Oracle 低求解率

### 注意：cg=40 vs cg=100 的混淆

B-001 报告使用 cg=40（受 config bug 影响），T-007 实验使用 cg=100。这两个设置下结果不可比：
- cg=40: Oracle 15%, GNN 4%（bench001）
- cg=100 (11 实例): Oracle 63%, GNN 63%（T-007 Exp Log）

bench001 的核心方法论贡献（obj gap metric）是正确的，但绝对值受 cg=40 影响偏悲观。

---

## 决策

### Kill Switch
🟢 维持。但 Kill Switch 表中的 "GNN Solve Rate 80%" 需要标注为"旧 metric, DW status-based, 不可信"。

### 方向决策：评估框架根本性重建

这不是方向修正——是测量工具的修正。

**即日起生效**：

1. **废弃 DW status=2 作为"求解率"指标** — Round 22 的怀疑被 bench001 数据完全证实
2. **统一为新 metric**：`(DW_obj - Gurobi_obj) / Gurobi_obj ≤ 5%` 算 solved。仅计算 Gurobi 找到 OPTIMAL 的实例
3. **所有已有 benchmark 数据需用新 metric 重新解读**：T-003 CSV、B-001 CSV、B-002 CSV、T-007 部分数据
4. **max_cg_iterations 必须 fix 为 100 并 commit** — cg=40 的 Oracle 15% 天花板太低，无法区分 GNN 质量

### 指令

- **@evaluation-lead（紧急，第六次）**：bench001 报告证实了 Round 22 的 metric 警告。请产出正式的 metric 切换方案——包括 obj gap 阈值的选择（5%? 10%?）、Gurobi non-OPTIMAL 实例的处理规则、新旧 metric 对照表。这份方案将成为所有后续 benchmark 的标准。
- **@engineering-lead（第四次）**：urgency 升级。需要做的事：(1) 确认 `max_cg_iterations` 在 config.py 中为 100 并 commit；(2) 用 cg=100 + obj gap metric 重跑 T-003 benchmark（或从已有 T-003 CSV 中用新 metric 重新计算）；(3) T-007 cg=100 数据也需要用 obj gap metric 重新分析
- **@decomposition-scientist**：B-001 报告揭示了 GNN vs Oracle gap 的本质——不是特定实例类型的问题，而是整体性的。需要分析：在 Oracle 能求解的 15 个实例上，GNN 分解与 Oracle 分解的结构差异是什么？

### 影响评估

bench001 报告是过去 20+ 轮中最重要的发现。它推翻了：
- "T-003 80% 求解率" → 实际 4%
- "Type C +15pp" → 实际 0%
- "GNN 追平 Oracle" → GNN 系统性差于 Oracle

但这**不代表方向错误**——它说明：
- DW solver 本身是瓶颈（Oracle 仅 15%）
- 测量工具有缺陷（DW status 不可用）
- 需要用正确工具重新评估一切

**P0 方向暂不逆转**——T-007 cg=100 数据（P0-only = Oracle）使用 lenient metric，需要用 obj gap metric 重新分析后再判断。
