# round_032: 基于 round_031 发现更新全系统 Python 执行规则

**日期**: 2026-05-28
**目的**: 将 round_031 发现的 V100 Python 环境问题同步到所有系统文件

---

## 背景

round_031 发现 V100 服务器有 3 个 Python，只有 `/opt/miniconda3/bin/python3` 有完整科学计算包。原始 RULES.md、CLAUDE.md、ONBOARDING.md 中多处使用裸 `python3` 或 `bash -lc`，在实际非登录 SSH shell 中会失败。

## 改动

### RULES.md §1（上一轮已完成）
- 重写基础设施铁律：表格化"在哪做/怎么执行"
- 新增 heredoc 黄金标准：`ssh V100 /opt/miniconda3/bin/python3 << 'PYEOF'`
- 更新绝对禁止列表：`ssh V100 python`、`ssh V100 python3`、`ssh V100 "bash -lc..."`等

### CLAUDE.md（本轮）
- "Running code on the server"：新增 3-Python 对比表，新增 heredoc 和 -c 方法示例
- tmux 内命令：`python3` → `/opt/miniconda3/bin/python3`
- "Common commands" 表格：全部改为绝对路径，新增 heredoc 行
- "Quick remote check"：改为绝对路径 + 单行 -c 格式
- "Environment"：明确正确 Python 路径和版本

### ONBOARDING.md（本轮）
- 教训 1 完全重写：从"不要在 ssh 里嵌套复杂脚本"改为"必须用绝对 Python 路径 + heredoc"
  - 新增 heredoc 黄金标准代码示例
  - 新增单行 -c 正确格式
  - 新增写脚本执行正确流程
  - 新增绝对禁止项（裸 python、裸 python3、bash -lc）
- 工作规范：更新"写本地→同步→服务器执行"条目
- 快速检查清单：更新对应条目

## 核心规则（3 条记住即可）

```
1. 永远用 /opt/miniconda3/bin/python3（不用 python3 或 python）
2. 多行代码用 heredoc << 'PYEOF'（delimiter 必须加引号）
3. 一行代码用 -c，外层双引号、内层单引号
```

## 未完成

- 无。全系统 Python 执行规则已一致。
