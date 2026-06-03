# Round 054: Loop 锁机制 — 防止循环堆积

## 问题

`/loop` 是固定间隔触发，不等上一轮结束。当一轮执行时间超过 interval 时，后续轮次的 prompt 会叠加：

- 同一 slot 的多个实例同时编辑 BOARD.md，产生竞态条件
- 重复认领任务、重复启动 tmux
- Agent 在实验中改代码，打断正在运行的训练/benchmark

## 方案

文件锁互斥机制。每轮循环开始前抢占锁，锁存在就跳过。

```
[ ! -f /tmp/l2dcomp_<slot>.lock ] && touch /tmp/l2dcomp_<slot>.lock && {
  <本轮逻辑>
  rm /tmp/l2dcomp_<slot>.lock
} || echo '[<slot>] 上轮未结束，跳过本轮'
```

- 锁存在 → 上轮还在跑，本轮跳过
- 锁不存在 → touch 创建锁 → 执行 → rm 删除锁
- 锁文件在 `/tmp/` 下，重启自动清理
- 12 个 slot 各一个锁文件，完全独立

## 修改的文件

### `.claude/dispatch/RULES.md`
- 新增 §15 Loop 锁机制，作为项目级安全约束
- 列出全部 12 个锁文件对应关系
- 声明"所有 12 个 /loop 指令必须包含此锁机制，缺失视为不合格"
- 版本升级：v7 → v8

### `.claude/dispatch/ONBOARDING.md`
- 附录中全部 12 条 /loop 指令替换为锁版本
- 新增故障恢复说明：`rm /tmp/l2dcomp_*.lock`
- 版本升级：v7 → v8

## 为什么用文件锁而不是其他方案

| 方案 | 评价 |
|------|------|
| flock/fcntl | 需要系统调用，Claude Code bash 工具不直接支持 |
| mkdir 原子操作 | 可行但不如 touch/rm 直观 |
| `/loop` 内置机制 | 不存在，Claude Code /loop 没有内置互斥 |
| 文件锁 (touch/rm) | 零依赖、POSIX 通用、Claude Code 可直接操作 |

## 故障恢复

如果进程被 kill 导致锁残留（极小概率），手动清理：

```bash
rm /tmp/l2dcomp_*.lock
```

无副作用——所有角色下一轮恢复抢锁。重启 Mac 也会自动清理 `/tmp/`。

## 未修改的文件

9 个协议文件中，`TRAINING_AGENT_PROTOCOL.md`、`BENCHMARK_AGENT_PROTOCOL.md`、`PAPER_AGENT_PROTOCOL.md` 的冷启动章节中的 /loop 示例未更新。这些文件是"规则是什么"，锁机制的执行细节在 RULES.md §15 中集中定义。下次轮次可以统一更新。
