# Round 002 — 执行仪表盘搭建与项目现状审计

**日期**: 2026-05-27
**背景**: 上级要求搭建一份自动更新的 HTML 执行仪表盘，汇总所有历史阶段工作。

---

## 做了什么

### 1. 项目现状审计（数据驱动）

从服务器和本地汇总了所有可用数据：

| 数据源 | 位置 | 内容 |
|--------|------|------|
| `gap_dw_results.csv` | `results/` | 100 测试实例 DW vs Gurobi 对比 |
| `decomposition_output/` | `results/` | 200 个分解 JSON（100 实例 × 2 方法） |
| `best_model_gap.pth` | `models/` | 1.8MB 训练好的 GNN 模型 |
| `training_loss_curve.png` | `results/training_plots/` | 训练曲线图 |
| `tsne_visualization.png` | `models/` | t-SNE embedding 可视化 |

### 2. 关键发现（审计结论）

**实例难度问题未解决**：
- 100/100 测试实例 Gurobi 全部在 root node 求解（NodeCount=1.0）
- Gurobi 平均求解时间 0.007s — 实例过于简单
- 容量 tightness 公式已修改但未重新生成实例验证

**DW 列生成严重异常**：
- 76/100 实例 DW 返回 INFEASIBLE（artificial_cost 修复可能未重跑）
- 24 个 "成功" 实例的 DW 目标值与 Gurobi 全部不一致
- DW Oracle ≡ DW GNN 在所有实例上结果完全相同（可能是 GNN 完全复制了 oracle 行为，也可能是两者都坏了）

**数据不一致风险（Round 001 未解决问题 #1）**：
- `a15_t53_typeD_34`: Gurobi=3336, DW=271（DW 值低于理论下界 ~2968，不可能）
- `a15_t41_typeC_73`: Gurobi=2602, DW_Oracle=234, DW_GNN=260（Oracle 和 GNN 不一致！）

**未提交代码堆积**：
- 8 个文件有未提交修改（AMP、LR scheduler、gradient clipping、SupCon batch-aware）
- 10 个 debug_*.py 文件未清理

### 3. 搭建执行仪表盘

- 创建 `executive_dashboard.html`（项目根目录）
- 左侧时间线导航 + 右侧详细内容
- 5 分钟自动刷新（`<meta refresh>`）
- 基于 git 历史 + 轮次报告 + 实验数据，如实汇报

---

## 修改文件清单

| 文件 | 改动类型 | 内容 |
|------|----------|------|
| `.claude/reports/round_002_executive_dashboard.md` | 新建 | 本报告 |
| `executive_dashboard.html` | 新建 | 执行仪表盘 |

---

## 未解决问题

1. **DW INFEASIBLE 问题**：artificial_cost 修复（1e6→1e3）是否已在服务器上生效？需重跑验证
2. **实例太简单**：tightness 公式修改后未重新生成实例。需重跑 `01_generate_instances.py`
3. **DW-Gurobi 目标值不一致**：即使改完 artificial_cost，还有 24 个"成功"实例目标值全错
4. **GNN = Oracle**：GNN 和 Oracle 结果完全一致，不清楚是 GNN 学会了还是两者用了同样的错误数据
5. **未提交代码**：需要提交或放弃 uncommitted changes
6. **debug 文件**：10 个 debug_*.py 需要清理（如果不再需要）

---

## 给下一轮的经验教训

1. **轮次报告不足以重建完整历史**：Round 001 之前的 commit（project start, CFLP→GAP switch, cross-scale training）没有对应的轮次报告，只能从 commit message 推断。重要阶段必须写报告。
2. **实验结果是唯一真相来源**：CSV、JSON 数据比代码 diff 更能说明问题。审计应先看数据再看代码。
3. **DW 对数值极度敏感**：artificial_cost 差一个数量级就导致 76% 失败率。任何涉及数值参数的修改都必须跑完整验证。
4. **不要相信"修好了"**：Round 001 修了 artificial_cost，但数据表明问题可能仍在（或未重跑）。每次声称修复后必须附上新的实验结果。
