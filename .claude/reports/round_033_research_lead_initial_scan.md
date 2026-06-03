# Round 033: Research Lead 首轮巡检 — Heterophily GNN 调研启动

## 本轮做了什么

- 刷新 RESEARCH_LEAD_PROTOCOL.md → 确认身份和 §1 冷启动流程
- 读 BOARD.md → 发现 Dispatcher 已指派 `@research-lead: 调研 heterophily GNN 用于 MIP 分解`
- 执行初步文献扫描（3 组搜索，覆盖 heterophily GNN、MILP 分解学习、graph transformer）
- 产出 Research Brief: `knowledge/papers/research_scan_2026-05-28.md`
  - 3 个可行动方向：Heterophily-Aware GNN [主推]、Block-Structure PE [配套]、对比学习增强 [低成本]
  - 3 个不推荐方向：Subgraph GNNs（内存瓶颈）、MILPnet（路线不兼容）、端到端 RL（Stage 跳级）
- 向 Dispatcher 提交 proposal P-001
- 为 Paper Agents 创建搜索任务 S-001（heterophily GNN 深度调研）和 S-002（MILP block structure learning）

## 关键发现

- MIP constraint-variable 二部图天然具有 heterophily，但当前 GraphTransformer 对所有边统一 message passing，未区分同配/异配信号
- 2025 年 heterophily GNN 文献的核心趋势是"解耦"——将 homophily 和 heterophily 信号分通道处理再融合（HGphormer, DivGNN, SimPlex-GT）
- Structure-Aware Bipartite Representations (2024) 直接证明 block structure annotation 在二部 MILP 图上有 2-11% 改善
- 以上发现与 Dispatcher 的 "heterophily GNN" 指令高度一致

## 进行中

- S-001: paper-agent-1 深度调研 heterophily GNN 架构
- S-002: paper-agent-2 深度调研 MILP block structure learning
- 下一轮：整合 Paper Agent 结果 → 完整 Research Report → @dispatcher 汇报

## 给下一轮

- Paper Agent 结果预计在下一轮可用，Research Lead 需要做去重+分类+评估+提炼
- 注意关注 paper-agent-1 和 paper-agent-2 是否都完成了任务（交叉验证）
- 如果 Paper Agent 报告中有可复现代码/仓库，优先记录（Engineering Lead 需要）
