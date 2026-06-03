# Round 023 — 监控岗交接文档

**日期**: 2026-05-27
**角色**: 监控助手（/loop 值守）
**目的**: 关掉当前会话后，新会话可以无缝接手 V100 监控

---

## 一、监控岗职责

只读值守 V100 服务器 + 本地 Claude 活动，每 3 分钟一轮。**绝不干扰运行中的任务。**

---

## 二、启动方式

在新 Claude Code 会话中输入：

```
/loop 3m 检测V100服务器状态，包含三部分：

1. 训练状态：SSH到V100执行 — nvidia-smi查询GPU状态、检查03_train_gnn进程、tail -3 log_step3.txt。只读不干扰。

2. 新报告检测：检查服务器 /home/ycliu/projects/learn2dcomp/.claude/reports/ 下24h内新增的.md报告。有新报告则读取并摘要。

3. 同级Claude活动：检查本地 /Users/a1-6/projects/learn2dcomp/.claude/reports/ 下最近报告、check最近30分钟内修改的项目文件数量、本地claude进程数量。判断其他Claude实例是否在活跃修改项目。

用中文简洁汇报：训练进度+GPU状态、有无新报告、其他Claude实例活动状态。
```

这会创建一个每 3 分钟的 cron job（session-only，7 天自动过期）。

---

## 三、每轮执行的具体命令

### 1. GPU + 进程检查（SSH V100，一次调用完成）

```bash
ssh V100 "nvidia-smi --query-gpu=utilization.gpu,temperature.gpu,memory.used --format=csv,noheader; (ps aux|grep -E '03_train|07_solve|python3.*gap'|grep -v grep||echo no-proc)"
```

关注点：
- GPU 利用率 > 0% → 有人在跑 GPU 训练
- 显存使用 > 1 GB → 模型已加载
- 有 `03_train_gnn` 进程 → wjzhu 在训练
- 有 `07_solve` 或 `python3.*gap` 进程 → ycliu 在跑 benchmark/DW 调试

### 2. 新报告检测（SSH V100）

```bash
ssh V100 "ls -lt /home/ycliu/projects/learn2dcomp/.claude/reports/|head -3"
```

关注点：
- 文件时间戳在 24h 内 → 新报告，需读取摘要
- 读取命令：`ssh V100 "cat /home/ycliu/projects/learn2dcomp/.claude/reports/<文件名>"`

### 3. 本地活动检测

```bash
echo "py:$(find /Users/a1-6/projects/learn2dcomp/ -name '*.py' -mmin -30 -type f 2>/dev/null|wc -l) claude:$(ps aux|grep -i claude|grep -v grep|wc -l)"
```

关注点：
- py 修改数 > 3 → 活跃施工中
- Claude 进程数 > 5 → 多个 Claude 实例在工作
- 两者都高 → 项目在快速迭代

---

## 四、输出格式

每轮输出一行，格式固定：

```
GPU [利用率] | [进程状态] | [有无新报告] | 本地 [N] py / [N] Claude — [活跃/静止]
```

示例：
- `GPU 空闲 | 无进程 | 无新报告 | 本地 6 py / 10 Claude — 静止`
- `GPU 空闲 | PID 4156212: a15_t63_typeC_83 MIP 300s | 2 新报告！| 本地 8 py / 9 Claude`

---

## 五、权限配置

需要在 `.claude/settings.local.json` 的 `permissions.allow` 中加入：

```json
"Bash(ssh V100 *)",
"Bash(ssh *)",
"Bash(find *)",
"Bash(echo *)"
```

否则每轮都会弹确认框。文件位置：`/Users/a1-6/projects/learn2dcomp/.claude/settings.local.json`

---

## 六、经验规则

### 安全铁律
- 所有 SSH 命令只读（nvidia-smi、ps、ls、cat、tail）
- 绝不 kill、rm、killall
- SSH 超时设 15 秒（`--timeout 15000`）

### 信息密度
- 一轮 = 3 个并行 Bash 调用，不串行
- 服务器静止时一句话带过，不展开
- 有变化时展开详情（新进程、新报告、异常 GPU 占用）

### 何时建议停掉监控
- 服务器完全静止 > 10 轮（30 分钟以上）
- 没有任何运行中任务、没有 GPU 活动、没有新报告
- 主动向用户提议：`CronDelete <job_id>`

### 自动 commit
- 每 30 分钟一次，独立 cron job
- 规则：如果 git status 显示 4+ 文件修改 + 多个 untracked 调试文件 → 跳过（施工中）
- 只在变更稳定、无其他 Claude 活跃时 commit

---

## 七、V100 环境速查

| 项目 | 值 |
|------|-----|
| GPU | Tesla V100-PCIE-32GB |
| 项目路径 | `/home/ycliu/projects/learn2dcomp` |
| 报告目录 | `/home/ycliu/projects/learn2dcomp/.claude/reports/` |
| 训练日志 | `log_step3.txt`（不存在时说明无训练） |
| 其他用户 | wjzhu（GPU 训练）、mip（Jupyter） |
| 文件同步 | mutagen（本地编辑自动同步） |

---

## 八、当前 cron job 模板

| 用途 | 间隔 | Cron 表达式 | 命令 |
|------|------|-------------|------|
| V100 监控 | 3 min | `*/3 * * * *` | 本文 §二 的 prompt |
| 自动 commit | 30 min | `*/30 * * * *` | 本文 §六 的 commit 规则 |

两个都是 session-only，会话结束后自动消失，需要在新会话中重新创建。

---

## 九、启动新会话的步骤

1. 打开新 Claude Code（项目目录：`/Users/a1-6/projects/learn2dcomp`）
2. 确认 settings.local.json 权限配置到位
3. 输入 `/loop 3m <本文§二的完整prompt>`
4. 第一轮立即执行，确认 SSH 通、输出格式正确
5. 后续自动每 3 分钟执行，无需人工干预
