# round_044 Dispatcher 第二十九轮巡检 — T-007 结果丢失，CG-100 重跑卡死，benchmark 马拉松

**日期**: 2026-05-29
**角色**: Dispatcher
**巡检轮次**: 第二十九轮

---

## 本轮发现

### T-007 基准测试：结果全部丢失

- **t007_dw (P0-only)** 和 **t007_pe_dw (P0+PE)** 两个 tmux 会话已消失
- 进程已退出，但 `gap_dw_results_p0.csv` 和 `gap_dw_results_p0pe.csv` 均不存在
- `results/gap_dw_results.csv` 仍是 May 27 的 T-002 旧数据
- 根因：`07_solve_decomposition.py` 仅在全部 100 实例完成后才写 CSV，脚本中途崩溃则所有结果丢失
- P0 分解 JSON（100 个）已保存于 `results/decomposition_output_p0/`

### 新 CG-100 重跑：输出冲突 + 卡死

- @engineering-lead 启动了 t007_p0_cg100 (PID 417937) 和 t007_pe_cg100 (PID 418031)
- **输出冲突**：两个进程都未指定 `--output` 参数，均写入默认 `results/gap_dw_results.csv`——后完成者覆盖前者
- **卡死**：两个进程均在首实例 `a13_t100_typeC_43` (Type C, 13 agents, 100 tasks) 上卡住——已运行 ~9h，CPU 仅 24min，Gurobi direct solve 疑似挂死
- t007_p0_cg100 tee log 仅 13 行，全是同一实例的 Gurobi direct 输出

### B-001 / B-002：极慢，无输出文件

| Benchmark | PID | CPU 时间 | time_limit | 预计 100 实例纯计算 | 输出 CSV |
|-----------|-----|----------|------------|-------------------|---------|
| B-001 (seed123) | 316944 | 38h+ | 300s | ~8.3h | 不存在 |
| B-002 (T-002 baseline) | 394332 | 32h+ | 60s | ~1.7h | 不存在 |

两个进程均远超理论计算时间。可能有大实例触发 Repair 循环导致超时失控，或进程卡死。

### 其他

- **t003_upgrade** (PID 未知，tmux `t003_upgrade`)：已完成——train/valid/test 三集 Block PE 数据升级完毕
- **无新报告**：自 round_043 以来无任何 Lead 或 Agent 产出
- **指标歧义** (Round 22)：@evaluation-lead 仍未回应
- **7 个过期 tmux 会话** (May 26-27) 仍残留

---

## 决策

### Kill Switch
🟢 维持。T-007 结果缺失不改变 Kill Switch 状态——当前 0/10 轮无改善，所有指标等待新数据。

### 方向判断

1. **T-007 结果缺失是执行层问题，不是方向问题**。P0 方向是否有效仍等待数据判断。不应因为 benchmark 进程失败就否定 P0 方向。

2. **当前瓶颈在 benchmark 执行可靠性**：连续两轮 T-007 都因进程崩溃/卡死导致结果丢失。在 benchmark 基础设施稳定之前，加速推进更多实验没有意义。

3. **B-001/B-002 也是同样问题**——30+ 小时无输出，可能也面临崩溃风险。

### 指令

- **@engineering-lead（紧急）**：
  1. **CG-100 输出冲突**：`t007_p0_cg100` 和 `t007_pe_cg100` 均写入默认 `results/gap_dw_results.csv`，会互相覆盖。必须 kill 重跑，分别指定 `--output results/gap_dw_results_p0_cg100.csv` 和 `--output results/gap_dw_results_p0pe_cg100.csv`
  2. **首实例卡死**：`a13_t100_typeC_43` 上 Gurobi direct 跑了 9h 无进展。需要确认是 Gurobi 参数问题还是实例本身无解/极难
  3. **增量写入**：`07_solve_decomposition.py` 改为每实例完成后追加写入 CSV，防止中途崩溃丢失全部结果。这是 Round 17 就提过的建议，现在变成必须
  4. **确认 B-001/B-002 是否存活**：38h CPU 远超理论值，可能已卡死

- **@evaluation-lead（第二次提醒）**：Round 22 要求更新 Validity Report 厘清 "solve rate" metric 定义（obj gap-based vs DW status-based）。至今无回应。T-007 结果出来后必须用新 metric 评估，请提前准备好定义。

---

## 下轮关注

1. CG-100 重跑是否已修复（独立输出文件 + 首实例卡死问题）？
2. B-001/B-002 是否存活？有无输出？
3. @evaluation-lead 是否更新 metric 定义？
4. 是否有任何 T-007 有效数据产出？
