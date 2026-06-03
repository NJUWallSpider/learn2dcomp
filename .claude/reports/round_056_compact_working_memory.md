# Round 056: Compact 系统 — 短期工作记忆层

## 做了什么

在 Research OS 文件系统状态机上叠加了**短期工作记忆层**（`compacts/`），核心机制是**覆盖写而非追加**，防止 Agent 上下文随轮次指数腐烂。

## 核心变化

| 新增 | 说明 |
|------|------|
| `compacts/` 目录 | 12 个 `<slot>.md`，每个角色一个 |
| 覆盖写规则 | 用 Write 工具覆盖整个文件，禁止 `>>` 追加 |
| 读 3 类限制 | 每轮只读 compact + 新 events + 当前 task |
| 差异化 compact 周期 | Agents 每 5 loop / Leads 每 10 loop / Dispatcher 每 6 loop / Knowledge Agent 每轮 |
| Knowledge Agent 语义记忆 | 记录"学到了什么"而非"发生了什么" |
| Dispatcher 大脑皮层 | Active Directions + Signals + Resource State + Pending Decisions |

## 修改的文件

- `protocols/RULES.md`：新增 §17 Compact 系统（覆盖写规则 + 读 3 类限制 + 频率表 + compacts vs events 对照）
- `protocols/ONBOARDING.md`：全部 12 条 /loop 指令更新，每条加上 `读 compacts/<slot>.md 恢复工作记忆 →` 开头和 `→ 覆盖写 compacts/<slot>.md` 结尾
- `CLAUDE.md`：调度中心文件表新增 compacts/ 行、Tier 2 受保护列表新增 compacts/、Dispatcher 接手读新增 compact
- `knowledge/meta_system/research_os_architecture.md`：v9→v10，目录树新增工作记忆层，新增 compact vs events 对照章节

## 新建的文件

- `compacts/dispatcher.md` — 方向层大脑皮层
- `compacts/research-lead.md`
- `compacts/engineering-lead.md`
- `compacts/evaluation-lead.md`
- `compacts/decomposition-scientist.md`
- `compacts/paper-agent-1.md`
- `compacts/paper-agent-2.md`
- `compacts/training-agent-1.md`
- `compacts/training-agent-2.md`
- `compacts/benchmark-agent-1.md`
- `compacts/benchmark-agent-2.md`
- `compacts/knowledge-agent.md` — 语义记忆（Stable Lessons + Repeated Failures + Deprecated Directions）

## 设计原则

1. **覆盖写不追加**：compact 自己不能腐烂
2. **compacts ≠ events**：events 是审计真相（append-only），compacts 是工作记忆（overwrite）
3. **先读 compact 再读增量**：不是"重新读整个世界"
4. **不 compact events/**：永远不压缩日志
5. **规模适配**：不过度工程化（无 vector DB、无 RAG、无 embedding）

## 验证

- 目录存在：`ls .claude/dispatch/compacts/` 返回 12 个文件
- 所有 loop 指令含 compact：`grep -c "compacts/" protocols/ONBOARDING.md` 返回 24（12 读 + 12 写）
- RULES.md §17 存在：确认
