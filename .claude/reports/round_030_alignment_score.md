# Round 030: Solver Alignment Score — 自动化假设发现

## 新增机制

系统新增 **Solver Alignment Score**——自动计算每个 intermediate metric 与 solver runtime 的 Spearman 相关系数，回答：

> "你怎么知道优化这个指标是对的？"

## 核心公式

```
alignment_score[metric] = |spearman_corr(metric_values, runtime_values)|
```

值域 0.0–1.0。绝对值（方向不重要，相关即有用）。

## 三分级

| 等级 | 阈值 | 含义 | 动作 |
|------|------|------|------|
| 🟢 高对齐 | \|ρ\|>0.5 | 该指标预测求解器性能 | 结构指标→自动生成 Hypothesis 给 Engineering Lead |
| 🟡 中对齐 | 0.3<\|ρ\|<0.5 | 可能有用 | 积累更多数据 |
| 🔴 低对齐 | \|ρ\|<0.3 | 可能是噪声 | 连续 3 期低对齐→从优化目标中移除 |

## 自动化规则

1. 高对齐 (>0.5) 且是结构指标 → 自动提案："modularity 对 runtime 的 alignment=0.72，建议在 GNN loss 中加入"
2. 高对齐 (>0.5) 且是过程指标 → 标记为 Surrogate Target
3. 低对齐 (<0.2) 连续 3 期 → 自动标记为噪声，停止优化
4. \|Δρ\|>0.2 → 触发分析：数据分布变了？

## 与现有系统集成

- **Decomposition Scientist §2 步骤 7**：每 5 轮计算一次
- **BOARD.md**：新增 Solver Alignment Score 仪表板（在 Kill Switch 下方）
- **Knowledge Agent**：新增 alignment 查询能力（5 种查询模式）
- 输出文件：`knowledge/decomposition/alignment_scores.md`

## 科研价值

直接回答论文最核心的质疑：如果 train_accuracy 的 alignment 持续 <0.1，而 modularity 的 alignment=0.72——这就是 Stage 2 (Solver Feedback) 的定量依据，证明"学习 GCG labels"不是正确方向。

## 已修改文件

- DECOMPOSITION_SCIENTIST_PROTOCOL.md — 新增步骤 7（Solver Alignment Score），原步骤 7-11 重编号为 8-12
- BOARD.md — 新增 Solver Alignment Score 仪表板
- KNOWLEDGE_AGENT_PROTOCOL.md — 新增 alignment 查询能力
