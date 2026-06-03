# Round 037: Evaluation Lead — T-003/T-005 有效性验证

## 身份
Evaluation Lead (evaluation-lead)，防自我欺骗机制。

## 本轮做了什么

### 1. 信息收集
- 读 EVALUATION_LEAD_PROTOCOL.md、BOARD.md、RULES.md
- 读 `exp_T-003_summary.md` (Block PE, GNN 77%→80%)
- 读 `exp_T-005_summary.md` (CG prediction ρ=0.61)
- 读 `exp_T-006_summary.md` (CG-guided training 崩溃, Moving Target)
- 查询 `results.parquet` — 只有 T-002 数据，T-003/T-005 未写入
- 查询 `registry/experiments.parquet` — 只有 T-002 一行

### 2. 有效性检查结果

| 检查项 | T-003 | T-005 | T-006 |
|--------|-------|-------|-------|
| 数据泄漏 | ⚠️ 无法确认 | ⚠️ split 内评估 | — |
| 随机性 | ⚠️ 仅 seed=42 | ⚠️ n=24, CI 宽 | — |
| 过拟合 | ⚠️ Type C n=20 | ⚠️ per-type n=3-6 | — |
| 基线公平性 | ⚠️ 特征维度不平等 | ✅ | — |
| 统计显著性 | ⚠️ +3pp on n=100 | ⚠️ CI [0.27,0.82] | — |
| 结构化数据 | ❌ 未注册 | ❌ 未注册 | ❌ 未注册 |
| 根因分析 | — | — | ✅ 可信 |

### 3. 产出
- **Validity Report**: `.claude/reports/validity_001_T003_T005_review.md`
  - 可信度：中 — 方向正确，效应量和显著性需独立验证
- **Benchmark 任务 B-001**: T-003 Multi-Seed 验证 (seed=123,456,789)
- **Benchmark 任务 B-002**: T-003 vs T-002 消融 (Block PE vs Random PE vs Baseline)

### 4. BOARD.md 更新
- evaluation-lead 状态：🔴 冲突升级 → 🟢 活跃
- Benchmark 任务队列：B-001/B-002 已发布，等待 benchmark-agent 认领
- 调度日志：@dispatcher 汇报 + @benchmark-agent-1 请认领

## 关键判断

**T-007 (P0 解耦消息传递) 可以继续** — 它是架构改进，不依赖 T-003 的 +3pp 声明。但任何以"T-003 证明 Block PE 有效"为前提的新提案应标记 ⚠️ 待验证。

**T-006 失败根因分析可信** — Moving Target 问题是 surrogate-based optimization 的已知陷阱，崩溃幅度 (SupCon +48%, CG pred -2460) 排除了随机波动。

## 未解决问题
- B-001/B-002 等待 Benchmark Agent 认领执行
- T-003/T-005 结果需写入 `results.parquet` 和 `registry/experiments.parquet`
- 需要 Decomposition Scientist 基于 T-003 数据更新 Kill Switch 和 Solver Alignment Score

## 给下一轮的经验教训
- 不要让实验结果在没有独立验证的情况下推动方向决策——这是 Evaluation Lead 存在的理由
- `results.parquet` 写入应该是实验完成的一部分，不是事后补——建议在 Training Agent 协议中强制要求
