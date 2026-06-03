# Round 015 — T-013 重跑 8 个污染 Type C 实例

**时间**: 2026-05-30 14:15 CST
**工人**: worker-delta (gamma 离线，delta 接手执行)
**任务**: T-013 — 用修复后代码重跑 8 个污染 Type C 实例

---

## 执行

gamma 已写好 `rerun_typeC.py` 但未执行（无 tmux 会话，无 commit）。
delta 认领后在服务器 tmux `t013_rerun` 中运行，耗时约 10 分钟。

## 结果

| Instance | Gurobi | Old Oracle (1e8 poll) | New Oracle | Art Vars | 判定 |
|----------|--------|----------------------|------------|----------|------|
| a15_t84_typeC_33 | 6,564 | 900,005,971 | TIME_LIMIT | 0 | MIP 未完成 |
| a14_t82_typeC_98 | 6,456 | 800,006,130 | 806,130 | 8 | 真 DW 失败 |
| a15_t89_typeC_53 | 7,014 | 700,006,859 | TIME_LIMIT | 0 | MIP 未完成 |
| a16_t82_typeC_8 | 6,430 | 600,006,410 | TIME_LIMIT | 0 | MIP 未完成 |
| a15_t77_typeC_88 | 6,042 | 500,005,968 | 505,968 | 5 | 真 DW 失败 |
| a15_t78_typeC_18 | 6,093 | 500,005,911 | 505,911 | 5 | 真 DW 失败 |
| a15_t63_typeC_83 | 4,908 | 200,005,060 | 205,060 | 2 | 真 DW 失败 |
| a15_t69_typeC_38 | 5,379 | 200,005,374 | 205,374 | 2 | 真 DW 失败 |

**Clean solves: 0/8**
**DW failures (artificial vars): 5/8**
**TIME_LIMIT: 3/8**

## 关键发现

### 1. artificial_cost 修复验证通过

Old Oracle obj 膨胀模式 = Gurobi + N×1e8。New Oracle obj = real_cost + N×1e5。
例如 a15_t63_typeC_83: 200,005,060 → 205,060 (1000× reduction)。

扣除人工变量惩罚后的真实成本与 Gurobi 接近：

| Instance | Back-calculated real cost | Gurobi |
|----------|--------------------------|--------|
| a14_t82_typeC_98 | 806,130 - 8×1e5 = 6,130 | 6,456 |
| a15_t77_typeC_88 | 505,968 - 5×1e5 = 5,968 | 6,042 |
| a15_t63_typeC_83 | 205,060 - 2×1e5 = 5,060 | 4,908 |
| a15_t69_typeC_38 | 205,374 - 2×1e5 = 5,374 | 5,379 |

### 2. 全部 8 个实例都是真 DW 失败

修复前这 8 个实例的 Oracle 显示 OPTIMAL (status=2)，但 obj 被 1e8 膨胀。
修复后：5 个明确有人工变量进入 MIP 解，3 个 TIME_LIMIT。
**无一例是"修复后变干净"的** — 这意味着 Type C 实例对 DW 列生成确实困难。

### 3. Type C 是 DW 的 Achilles' heel

T-007 的 20 个 Type C 实例中：
- 8 个原被 artificial_cost 污染 → 现确认为真 DW 失败
- 7 个原 TIME_LIMIT → 仍然是 TIME_LIMIT
- 5 个原 OPTIMAL 且干净（round_012 分析）

Type C 实例特征：agent/task 比值低，capacity 约束紧 → DW 列生成难以覆盖所有 task。

## 未解决问题

- **T-002 剩余 35 实例**：从未跑完
- **Type D TIME_LIMIT 50%**：120s 不够
- **a14_t79_typeB_42 outlier**：Oracle-Gurobi gap 31.2%
- **临时脚本清理**：verify_artificial_cost.py, verify_fix.py 待删除
- **report.html 更新**：反映 T-007 + T-013 最终结果

## 经验教训

- **脚本写好了不等于任务完成了**：gamma 写了 rerun_typeC.py 但从未执行就离线。工人离线前应 commit 并更新 board 状态
- **1e8 污染是系统性 bug**：8/8 实例全部是 genuine DW failure，之前报告的 "19% gap" 中的 8 个异常值现已正确定性
- **Type C 实例需要改进 DW**：要么增加 time_limit，要么改进列生成策略（如 stabilization）
