# Round 003 — 深度学习与数据核实

**日期**: 2026-05-27
**背景**: 被要求不要盲目动手，先彻底理解项目现状。本报告基于对代码 diff、实验数据、
  服务器进程、前两轮报告的仔细阅读。

---

## 当前项目实际状态（基于证据）

### 实验数据（results/gap_dw_results.csv）

**只有 5 个实例**，不是 100 个。`experiment` tmux 会话中运行的 07_solve_decomposition.py
被中断，导致 CSV 不完整。

| 实例 | Gurobi | DW Oracle | DW GNN | 结论 |
|------|--------|-----------|--------|------|
| a13_t100_typeC_43 | 6396 (0.01s) | INFEASIBLE | INFEASIBLE | 大实例(1300 vars) CG 第一轮 LP 就失败 |
| a13_t40_typeB_12 | 345 | 345 ✓ | 345 ✓ | 完美 |
| a13_t40_typeB_62 | 390 | 390 ✓ | 390 ✓ | 完美 |
| a13_t41_typeB_37 | 298 | 298 ✓ | 298 ✓ | 完美 |
| a13_t42_typeB_57 | 334 | 334 ✓ | **353 ✗** | GNN 分解有问题 (+5.7%) |

**关键发现**:
- Oracle DW 匹配 Gurobi 的 4/4 实例 → **数据一致性问题已解决**（parse_gap_gurobi 修复有效）
- INFEASIBLE 的实例是最大那个（100 tasks）→ artificial_cost 修复可能未同步到服务器
- GNN 有一个实例给出不同（更差）的目标值 → GNN 分解不是完美的

### 服务器运行状态

- `experiment` tmux: 交互式 shell，之前跑过 07_solve_decomposition.py 但被中断
  （输出停在 typeA_21）。之后有手动 Gurobi 测试命令
- `solve2` tmux: 窗口存在但无输出，可能是挂起状态
- 没有长时间运行的训练或求解任务

### 未提交代码修改（另一个 Claude 会话的工作）

| 文件 | 改动 |
|------|------|
| 03_train_gnn.py | AMP 混合精度 + ReduceLROnPlateau + gradient clipping + batch_idx 传入 |
| gnn_model.py | num_layers=3 + SupCon per-instance（temperature 0.1→0.3） |
| 04_test.py | 小改（4 行） |
| 05_visualize_embeddings.py | 小改（3 行） |
| 06_eval_instances.py | 小改（7 行） |
| config.py | 参数调整（+ 我 Round 001 的 artificial_cost 改动） |
| 07_solve_decomposition.py | + parse_gap_gurobi（我 Round 001 的改动） |
| report.html | 我 Round 001 的更新 |
| run_guide.html | 我 Round 001 的更新 |

训练代码修改质量评估：
- ✅ 去掉重复 PE 计算（从 .pt 读取，不重新算）—— 修了报告中的 known issue
- ✅ AMP + scheduler + gradient clipping —— 训练稳定性提升
- ⚠️ SupCon 改为 per-instance（temperature 0.1→0.3）—— 逻辑正确但未验证
- ⚠️ num_layers 从 2→3 —— 合理但未验证

### executive_dashboard.html 的问题

- 数据面板说 "5 instances" 又说 "out of 100" —— **数字自相矛盾**
- 基于只有 5 个实例的数据做推断，但表述成好像有 100 个实例的结论
- 需要等完整的 100 实例跑完后重新生成

### 项目根目录新增文件

- CFLP_gurobi.py, UFLP_Benders.py, UFLP_gurobi.py —— 看起来像是另一个会话在扩展
  到新问题类型（CFLP → UFLP）。与 GAP pipeline 无关。
- 8 个 debug_*.py —— 大部分与 DW RMP 调试相关。不应删除，因为 DW 问题尚未解决。

---

## 给下一轮的经验教训

1. **CSV 数据优先于摘要文字**：Round 002 报告说 "100 个测试实例"，但 CSV 只有 5 行。
   任何数字在没有直接看到原始数据前，都是不可信的。

2. **Oracle DW = Gurobi 说明数据提取修复有效**：4/4 成功实例中 Oracle 目标值完全匹配
   Gurobi，证明 parse_gap_gurobi 解决了之前的数据不一致问题。

3. **DW INFEASIBLE 仍然存在**：a13_t100_typeC_43（最大的实例）在第一轮 CG LP 就失败了。
   artificial_cost 从 1e6 改成 1e3 可能没有同步到服务器（uncommitted changes）。

4. **GNN 分解不是完美的**：a13_t42_typeB_57 中 GNN 给出了不同的目标值（353 vs 334）。
   需要检查该实例的 GNN 分解 JSON，看哪些变量被分错了。

5. **Dashboard 的自动刷新是无害的**：`<meta refresh>` 只是重新读取静态 HTML，不执行
   任何命令，不会影响服务器进程。

6. **不要删 debug 文件**：DW 问题还在，debug_rmp.py 和 debug_rmp2.py 仍然有用。
   它们就是为调查当前 INFEASIBLE 问题而写的。

---

## 建议的下一步（供用户选择，非自行执行）

1. **先跑完完整的 100 实例测试**：让 solve 脚本在 tmux 中跑完，拿到完整数据
2. **验证 training 改动**：提交 03_train_gnn.py + gnn_model.py 的改进，在服务器
   上重跑训练验证 loss 是否改善
3. **调查 DW INFEASIBLE**：在服务器上单独跑 a13_t100_typeC_43，用 debug_rmp.py
   确认是 artificial_cost 还是其他问题
4. **调查 GNN 分解错误**：检查 a13_t42_typeB_57_decomposition.json，对比 GNN
   分解和 oracle 分解的差异
