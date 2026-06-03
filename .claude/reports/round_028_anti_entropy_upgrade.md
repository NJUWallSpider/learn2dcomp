# Round 028: Anti-Entropy Upgrade — 系统 v5

## 问题诊断

用户指出系统的 6 类缺陷（结构性/调度/科研/数据闭环/冲突/频率），根源是"系统越来越聪明，但越来越慢"的熵增问题。

## 改动总览

### 结构性修复：主动提案权
- DISPATCHER.md — 从"所有方向自己决定"改为"审批提案 + 方向决策"双重职责
- RESEARCH_LEAD_PROTOCOL.md — 新增主动提案权：发现方向直接 `@dispatcher proposal`
- ENGINEERING_LEAD_PROTOCOL.md — 新增主动提案权 + 资源否决权
- EVALUATION_LEAD_PROTOCOL.md — 新增主动提案权 + 一票否决权
- DECOMPOSITION_SCIENTIST_PROTOCOL.md — 新增主动提案权 + 数据发言权
- BOARD.md — 新增提案区表格

### 调度修复：日志拆分 + BOARD 瘦身
- BOARD.md — 重写为"当前态"：只保留角色状态、提案区、任务队列、Kill Switch 状态、最近 5 条日志。从 ~110 行缩减
- logs/dispatch_log/ — 新建，v3 历史日志已迁移
- logs/experiment_log/ — 新建
- logs/benchmark_log/ — 新建
- logs/README.md — 写入规则

### 科研修复：Kill Switch
- RULES.md §10 — Kill Switch 机制定义
- DISPATCHER.md §3 — Kill Switch 触发后强制切换方向的规则
- BOARD.md — Kill Switch 状态表（CG/LP Gap/Runtime/Column Diversity）
- DECOMPOSITION_SCIENTIST_PROTOCOL.md — 每轮更新 Kill Switch 表的职责

### 冲突解决
- RULES.md §9 — 决策优先级：Evaluation 一票否决 > Engineering 资源否决 > Decomposition Scientist 数据发言 > Research 提案 > Dispatcher 终裁
- 冲突升级流程：3 轮内解决，Dispatcher 终裁

### 数据闭环
- DECOMPOSITION_SCIENTIST_PROTOCOL.md — results.parquet 列结构定义（20+ 字段），维护职责
- KNOWLEDGE_AGENT_PROTOCOL.md — 从 parquet 做统计查询的能力
- BOARD.md — 结构化数据表

### 差异化 Loop 间隔
| 角色 | 旧 | 新 |
|------|----|----|
| Dispatcher | 120s | 900s (15min) |
| Research Lead | 120s | 600s (10min) |
| Engineering Lead | 120s | 600s (10min) |
| Evaluation Lead | 120s | 600s (10min) |
| Decomposition Scientist | 120s | 600s (10min) |
| Paper/Training/Benchmark Agents | 120s | 不变（按需，长间隔更合理） |
| Knowledge Agent | 120s | 1800s (30min) |

## 已修改文件清单

新建：logs/ (4 个文件)、logs/dispatch_log/v3_legacy.md
重写：BOARD.md
修改：DISPATCHER.md、RULES.md、RESEARCH_LEAD_PROTOCOL.md、ENGINEERING_LEAD_PROTOCOL.md、EVALUATION_LEAD_PROTOCOL.md、DECOMPOSITION_SCIENTIST_PROTOCOL.md、KNOWLEDGE_AGENT_PROTOCOL.md、ONBOARDING.md、CLAUDE.md

## 核心设计理念

三个系统解决熵增：
1. **Event Bus（思想）** — 提案机制 = 去中心化的方向来源
2. **Structured Metrics DB（思想）** — results.parquet = 从"记忆"到"统计"
3. **Kill Switch System（实现）** — 10 轮无改善 = 强制切换，防止局部最优
