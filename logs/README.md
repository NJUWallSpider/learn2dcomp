# Logs — 调度日志存档

BOARD.md 只保留最近 5 条日志。完整历史存放在此。

## 目录

| 目录 | 内容 | 写入者 |
|------|------|--------|
| `dispatch_log/` | Dispatcher 决策记录、方向切换、提案审批 | Dispatcher, Knowledge Agent |
| `experiment_log/` | 实验日志索引（指针指向 `knowledge/experiments/`） | Training Agents, Engineering Lead |
| `benchmark_log/` | Benchmark 日志索引（指针指向 `knowledge/experiments/`） | Benchmark Agents, Evaluation Lead |

## 写入规则

- BOARD.md 超过 5 条日志时，最旧的条目迁移到 `dispatch_log/round_XXX.md`
- 不再修改的归档日志以独立文件存储
- 日志文件命名：`dispatch_log/YYYY-MM-DD_简述.md`
