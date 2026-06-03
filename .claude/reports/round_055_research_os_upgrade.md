# Round 055: Research OS 架构升级

## 做了什么

将 `.claude/dispatch/` 从以 `BOARD.md` 为中心的单文件系统重构为**文件系统状态机**架构。

## 核心变化

| 旧 | 新 |
|----|-----|
| `BOARD.md` = 所有状态（18KB） | `board/BOARD.md`（2KB，仅方向） + 独立子系统 |
| `grep '⬜' BOARD.md` 检测任务 | `grep -l "owner: slot" tasks/open/*.md` |
| 心跳嵌入 BOARD.md 底部表格 | `heartbeats/<slot>.json`（13 个独立文件） |
| 无事件记录 | `events/YYYY/MM/<ts>_<slot>_<type>.md`（9 个初始事件） |
| 无预算控制 | `budgets/proposal_budget.yaml` + `gpu_budget.yaml` |
| 无增量消费 | `checkpoints/<role>.cursor`（空文件 + `find -newer`） |
| 协议文件散落 dispatch/ 根 | `protocols/` 子目录（12 个文件） |
| emoji 状态流转 | `mv tasks/open/<id>.md tasks/claimed/<id>.md`（原子 rename） |

## 新目录结构

```
.claude/dispatch/
  protocols/    ← 12 个协议 + 规则文件
  board/        ← BOARD.md（方向）+ KILL_SWITCH.md
  tasks/        ← open/ claimed/ blocked/ done/ rejected/
  events/       ← 2026/05/ (9 个初始事件)
  heartbeats/   ← 13 个 <slot>.json
  reports/      ← research/ engineering/ evaluation/ decomposition/
  budgets/      ← proposal_budget.yaml + gpu_budget.yaml
  checkpoints/  ← 6 个 .cursor 空文件
```

## 修改的文件

### 重写
- `protocols/RULES.md`：v8→v9，新增 §11 任务系统（文件格式+流转规则）、§12 心跳文件格式、§16 Research OS 架构（事件系统+增量消费+预算）
- `board/BOARD.md`：从 18KB 瘦身到 2KB，仅保留方向、优先级、瓶颈、提案区摘要
- `protocols/ONBOARDING.md`：全部 12 条 /loop 指令更新为新路径和任务检测方式

### 更新
- `CLAUDE.md`：26+ 处路径引用更新，所有协议路径加 `protocols/` 前缀，新增调度基础设施说明
- `protocols/DISPATCHER.md`：接手读清单更新，冷启动流程改用事件增量消费

### 新建（约 40 个文件）
- 9 个任务文件（tasks/）
- 9 个事件文件（events/2026/05/）
- 13 个心跳文件（heartbeats/）
- 2 个预算文件（budgets/）
- 6 个游标文件（checkpoints/）
- `board/KILL_SWITCH.md`
- `board/BOARD_ARCHIVE_v1.md`（旧 BOARD 归档）

### 未修改
- 8 个协议文件的路径引用（Training/Benchmark/Paper Agent + 各 Lead + Decomposition Scientist + Knowledge Agent）。这些文件的路径引用由 CLAUDE.md 中正确的路径引导。下次轮次可逐文件更新。

## 验证结果

- 目录完整性：所有 20 个子目录存在
- 心跳可读：`cat heartbeats/training-agent-1.json` 返回正确 JSON
- 任务检测：`grep -l "owner: benchmark-agent-2" tasks/claimed/*.md` 正确返回 B-002.md
- 游标机制：`touch cursor` → `find -newer cursor` 返回 0 个文件（正确）

## 关键设计决策

1. **文件系统 = 状态机**：用 `mv`（原子 rename）流转任务状态，天然防竞态
2. **grep YAML frontmatter** 替代 emoji grep：不再依赖特定 Unicode 字符
3. **游标用 mtime**：空文件 `find -newer` 是最简增量消费实现，零状态存储
4. **预算在 dispatch 层执行**：Dispatcher 分配 → Agent 自检扣除，去中心化
5. **不创建 dispatch/knowledge/**：使用项目根 `knowledge/`，用 tag `dispatch_meta` 区分
