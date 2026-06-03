# Round 029: v6 — Scientific Database Upgrade

## 改动目标

用户指出系统还缺 6 个核心层：
1. Experiment Registry（实验注册中心 — 结构化实验元数据 + 血缘 DAG）
2. Causal Hypothesis Layer（因果假设 — 假设→证据→反例→置信度）
3. Instance Taxonomy（实例分类学 — 什么实例适合什么分解）
4. Solver Telemetry（求解器内部状态 — pricing degeneracy, dual oscillation, column reuse ratio）
5. Experiment DAG（实验血缘追溯 — parent/child/proposal 关系）
6. 从"markdown 世界"升级到"结构化科学数据库"

## 新建文件

### registry/
- `registry/README.md` — experiments.parquet 完整 schema（30+ 字段：标识/配置/训练指标/分解指标/求解器指标/Solver Dynamics/状态）
- `parent_exp` + `proposal_origin` + `decision_origin` 字段实现 Experiment DAG

### knowledge/hypotheses/
- `knowledge/hypotheses/INDEX.md` — 活跃假设/已证伪假设/已确认假设 三区表格
- 置信度更新规则：支持+0.05，反例-0.15，<0.3 证伪，>0.85 确认

### knowledge/instances/
- `knowledge/instances/INDEX.md` — 实例家族（Family）索引
- 9 维实例特征定义（density, constraint_coupling, block_diagonal_ratio, row/col clustering_coeff...）
- 核心研究命题："不同 MILP 结构存在不同最优分解范式"

## 修改文件

### DECOMPOSITION_SCIENTIST_PROTOCOL.md（最大改动）
新增 4 个步骤（§2 步骤 8-11）：
- 步骤 8：因果假设追踪（HYP-XXX.md 格式 + 置信度更新规则）
- 步骤 9：实例分类学研究（聚类 → Family → 分解策略映射）
- 步骤 10：Solver Telemetry（cg_trace.parquet + bp_trace.parquet schema，Dual oscillation/Pricing degeneracy/Column reuse ratio/Branching instability/Reduced-cost distribution）
- 步骤 11：实验血缘追溯（Experiment DAG，从 parent_exp + proposal_origin 字段构建）

协议版本升级为 v6。

### KNOWLEDGE_AGENT_PROTOCOL.md
- 归档来源表新增：Hypothesis、Instance Family、Experiment Record、Solver Telemetry
- 结构化查询从单表扩展为 4 类：跨实验分析、因果假设验证、实例家族查询、实验血缘追溯
- 角色重新定位："不再是整理 markdown 的秘书，而是科研分析员"
- 协议版本升级为 v6

### BOARD.md
- 知识库索引新增：knowledge/hypotheses/、knowledge/instances/
- 结构化数据表新增：registry/experiments.parquet、registry/telemetry/
- Knowledge Agent 角色重新定位
- 调度日志新增 v6 升级记录

### RULES.md
- §3 神圣文件新增：knowledge/**/*.parquet、registry/**/*.parquet、registry/**/*.md
- 版本升级为 v6

### knowledge/README.md
- 目录结构表新增：hypotheses/、instances/

### CLAUDE.md + ONBOARDING.md
- 数据层描述 + 版本更新

## 系统现状

```
科学数据层（v6 新增）:
├── registry/experiments.parquet    ← 实验注册中心 + DAG 血缘
├── registry/telemetry/             ← Solver 内部状态
├── results.parquet                 ← 实例级 metrics
├── knowledge/hypotheses/           ← 因果假设系统
└── knowledge/instances/            ← 实例分类学

知识层（v4-v5）:
├── knowledge/decomposition/        ← 分解质量分析
├── knowledge/papers/               ← 论文摘要
├── knowledge/experiments/          ← 实验日志 + 横评
├── knowledge/failures/             ← 失败记录
├── knowledge/ideas/                ← 研究想法
└── knowledge/decisions/            ← 关键决策
```

从 "AI 帮我做实验" 到 "AI 开始学习组合优化中的结构科学"。
