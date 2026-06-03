# Round 034: Research Lead — Research Report 完成 + @dispatcher 汇报

## 本轮做了什么

- 刷新 RESEARCH_LEAD_PROTOCOL.md → 确认身份和 §2 工作流
- 读 BOARD.md → 确认 Dispatcher 指令 `@research-lead: 调研 heterophily GNN`
- Paper Agent 任务 S-001/S-002 未收到独立产出 → Research Lead 直接执行深度调研
- 对 9 篇候选论文逐一分析（机制、有效性、可迁移性、代码可用性）
- 产出完整 Research Report: `knowledge/papers/research_report_heterophily_gnn_2026-05-28.md`
- 更新 BOARD.md: 任务 S-001/S-002 → ✅ 已完成, research-lead → 🟢 空闲 + @dispatcher 汇报

## 最终推荐

| 优先级 | 方向 | 实现代价 | 预期收益 |
|--------|------|----------|----------|
| P0 | 解耦消息传递通道（heterophilic + homophilic 分通道） | ~2-3 天 | 捕捉同 block variable 的隐式相似性 |
| P1 | Block-Structure Positional Encoding | ~1 天 | 给 GNN 提供 block 结构先验 |
| P2 | 对比学习增强（block affinity loss） | ~0.5 天 | 更紧致的 block 内聚表示 |

建议实施顺序: P1 (快速验证) → P0 (主要架构改进) → P2 (并行 ablation)

## 不推荐的方向

- Subgraph GNNs: 内存不可扩展
- MILPnet: 路线不兼容（图→序列）
- 端到端 RL: Stage 3 跳级，条件不成熟

## 给下一轮

- P-001 仍 ⏳ 待审批，等待 Dispatcher 决策
- 如果 Dispatcher 批准 → Engineering Lead 需要审查 P0 方案的实现细节
- 如果 Dispatcher 拒绝 → 等待新指令
- Knowledge Agent 应该将本报告的关键发现归档到 hypotheses/ 和 decisions/
