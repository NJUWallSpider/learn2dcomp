# Round 033 — Knowledge Agent: 知识库初始化归档

**日期**: 2026-05-28
**角色**: Knowledge Agent (knowledge-agent)
**轮次**: 第 1 轮知识库巡检

---

## 做了什么

### 1. 创建缺失的 INDEX.md（6 个）

`knowledge/` 目录结构存在但 6/8 子目录缺 INDEX.md：
- `papers/INDEX.md` — 论文索引（空，等待 Paper Agent 产出）
- `experiments/INDEX.md` — 实验索引（已填入 T-002, column diversification 等历史实验摘要）
- `failures/INDEX.md` — 失败记录索引（已填入 5 条记录链接）
- `ideas/INDEX.md` — 研究想法索引（已填入 6 条来自报告的研究想法）
- `decisions/INDEX.md` — 决策记录索引（已填入 6 条关键决策）
- `decomposition/INDEX.md` — 分解分析索引（空，等待 Decomposition Scientist 产出）

### 2. 从历史报告提取失败记录（5 条）

从 `round_010` 到 `round_021` 的报告中提取了关键失败：
- `failures/artificial_cost_pollution.md` — 多层默认值链导致 obj 膨胀 1000× (1e6 vs 1e3)
- `failures/typeC_dw_failure.md` — Type C 实例 DW 0% 成功（固有限制，非 bug）
- `failures/multi_task_initial_columns.md` — CG 阶段加 multi-task 列让 CG 立即收敛到次优解
- `failures/mip_start_infeasible.md` — 手工 MIP start 对 set partitioning 不可行
- `failures/dw_slower_than_direct.md` — DW 对小规模问题更慢（RMP MIP 比原始 MIP 更难）

### 3. 从历史报告提取决策记录（4 条）

- `decisions/tightness_formula.md` — 切换到 tightness 公式生成实例
- `decisions/column_diversification.md` — MIP 阶段列多样化策略
- `decisions/dynamic_pricing_time_limit.md` — 动态定价时间限制
- `decisions/artificial_cost_single_source.md` — artificial_cost 唯一配置来源

### 4. 状态检查

| 检查项 | 状态 |
|--------|------|
| `results.parquet` | 不存在（无实验运行过） |
| `registry/experiments.parquet` | 不存在（无实验注册） |
| `registry/telemetry/` | 不存在 |
| BOARD.md 调度日志 | 5 条（未超过阈值，无需迁移） |
| 调度日志中提问 | 无 |
| 新 Paper Summary | 无 |
| 新 Experiment Log | 无 |
| 新 Benchmark Report | 无 |
| 新 Hypothesis | 无（`hypotheses/INDEX.md` 为空） |
| 新 Instance Family | 无（`instances/INDEX.md` 为空） |

---

## 发现的问题

1. **知识库冷启动完成但不完整**: 8 个子目录的 INDEX.md 已建好，失败记录和决策从报告提取完毕，但实验记录（experiments/）、论文摘要（papers/）、分解分析（decomposition/）为空。这是正常的——这些等待对应 Agent 产出
2. **结构化数据库为空**: `results.parquet` 和 `registry/experiments.parquet` 不存在。需要 Training Agent 首先跑实验并写入 registry，然后 Decomposition Scientist 补充分析字段
3. **历史 benchmark 结果未结构化为 parquet**: round_016 的 100 实例 benchmark 结果只有日志和 markdown 描述，没有写入 `results.parquet`。建议 Engineering Lead 或 Decomposition Scientist 写一个迁移脚本

---

## 给下一轮的经验教训

1. **当 Reports 积累新实验时回来再看**：当前所有活跃实验的结论已提取。当 Training Agent 跑更多实验后，需要本 Agent 再次归档
2. **结构化查询能力暂不可用**：parquet 文件不存在，无法做跨实验 Spearman 分析。这是 v6 升级的下一步
3. **reports/ 中还有未提取的知识**：round_022-032 主要是系统升级报告（调度系统、反熵增、科学数据库），不涉及具体的实验失败/决策，暂不提取到 knowledge/。round_012 (T-007 analysis) 如涉及实验结论可进一步提取
4. **INDEX.md 格式与协议略有差异**：实验中 INDEX.md 用的是开放格式而非协议严格模板——这是有意为之，因为协议模板更适合将来有数据后的迁移

---

## 已创建/修改文件

| 文件 | 操作 |
|------|------|
| `knowledge/papers/INDEX.md` | 新建 |
| `knowledge/experiments/INDEX.md` | 新建 |
| `knowledge/failures/INDEX.md` | 新建 |
| `knowledge/ideas/INDEX.md` | 新建 |
| `knowledge/decisions/INDEX.md` | 新建 |
| `knowledge/decomposition/INDEX.md` | 新建 |
| `knowledge/failures/artificial_cost_pollution.md` | 新建 |
| `knowledge/failures/typeC_dw_failure.md` | 新建 |
| `knowledge/failures/multi_task_initial_columns.md` | 新建 |
| `knowledge/failures/mip_start_infeasible.md` | 新建 |
| `knowledge/failures/dw_slower_than_direct.md` | 新建 |
| `knowledge/decisions/tightness_formula.md` | 新建 |
| `knowledge/decisions/column_diversification.md` | 新建 |
| `knowledge/decisions/dynamic_pricing_time_limit.md` | 新建 |
| `knowledge/decisions/artificial_cost_single_source.md` | 新建 |
