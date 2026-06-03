# Round 010 — T-002 DW Benchmark 崩溃调查与状态更新

**日期**: 2026-05-28
**工人**: worker-gamma
**任务**: 监控 T-002 / 处理崩溃 / 更新主板

---

## 做了什么

### T-002 DW Benchmark 崩溃

- **进程 PID 3790851** 在 65/100 实例时消失（无错误信息，疑似 OOM kill）
- **最后输出**: `a15_t77_typeC_88` Gurobi direct 求解中（92 行 × 1155 列）
- **tmux dw_full** 会话已自动清理
- **CSV 文件** (`results/gap_dw_results.csv`) 不存在 — 脚本未写到 CSV 阶段
- **日志文件** (`results/dw_full_benchmark.log`) 保留 65 个实例的完整输出
- **T-007** (`tmux t007_eval`, 新模型分解) 仍在运行: 39/100

### 主板更新

- T-002: 🟡 阻塞 → ✅ 部分完成 (65/100, OOM crash)
- worker-delta: 🟠 卡住 → 🟢 空闲释放
- 调度日志追加崩溃确认记录
- gamma 心跳更新

---

## 未解决问题

1. **T-002 日志需解析**: 65 实例数据在 `dw_full_benchmark.log` 中，需写脚本提取 Obj/Gap/Time/CG iters 统计
2. **T-002 可能需重跑**: 65/100 不完整，部分类型分布可能不均衡。但如果 65 实例已有足够统计意义，可直接使用
3. **T-007 仍在运行**: 39/100 (新模型分解, t007_eval)，预计还需数小时
4. **OOM 根因**: 大实例 Gurobi direct 求解（无 time_limit）在高 agent 数 × task 数时内存耗尽
5. **Gurobi direct 无 time_limit**: 大 Type C 实例 Gurobi 在 B&B 上耗时 30-60 min+，是主要瓶颈

---

## 给下一轮的经验教训

1. **OOM 风险**: Gurobi direct 求解大 GAP 实例无 time_limit，内存随 B&B tree 增长。应给 Gurobi direct 也设 time_limit（如 300s）
2. **日志是唯一数据来源**: 崩溃时 CSV 未写入，但 tee 的日志保留了所有输出。解析日志是恢复数据的唯一途径
3. **两路并行有资源竞争**: 两个 07_solve_decomposition 进程同时跑可能竞争内存/CPU，增加 OOM 风险
4. **应分批跑**: 建议按 instance type 分批跑 benchmark，避免单个进程处理所有 100 实例
