# round_051 Dispatcher 第三十七轮巡检 — 根因揭露，P0 方向部分逆转

**日期**: 2026-05-29 | **轮次**: 第三十七轮

---

## 重大发现

### 基准测试崩溃根因：`max_cg_iterations=40` 未提交修改

T-007 Experiment Log (`exp_T-007_p0_decoupled_message_passing.md`) 揭露：`config.py` 中 `max_cg_iterations` 被改为 40（原始值=100），且未提交。这导致：
- Oracle（GCG 真值分解）求解率从 80% 暴跌至 4%（cg=40）
- 所有 GNN 结果全部不可比
- 过去 ~10 轮等待的 benchmark 数据本质上是废数据

**cg=100 已恢复**，CG-100 benchmark 重新开始产生有效数据。

### P0 方向初步数据：积极

cg=100, 11/100 实例 (lenient criterion):

| Method | P0-only | P0+PE | T-003 |
|--------|---------|-------|-------|
| DW Oracle | 63% (7/11) | 72% (8/11) | 80% |
| DW GNN | 63% (7/11) | 54% (6/11) | 80% |
| **GNN vs Oracle match** | **7/7 (100%)** | 6/8 (75%) | — |

**关键结论**：P0-only GNN 在 Oracle 能求解的实例上完美匹配 Oracle——没有引入额外退化。P0+PE 反而更差（Block PE 与 homophilic 通道冗余/冲突）。

### B-001 (T-003 Multi-Seed, seed=123) 完成

- 100/100 实例
- Gurobi: 97%, DW Oracle: 100% (lenient), DW GNN: 100% (lenient)
- Oracle Obj mean: 51,545 vs GNN Obj mean: 465,373 — **9x 差距**
- 再次证实 Round 22 发现：DW status=2 不能衡量分解质量

### B-002
86/100，持续推进。

---

## 决策

### Kill Switch
🟢 维持。

### 方向决策：R32 转向部分逆转

R32 因"T-007 数据不可得"将 P0 降级。现在知道根因是 `max_cg_iterations=40` 的配置 bug，而非管道根本性缺陷。P0 初步数据积极（P0-only = Oracle on evaluable instances）。

**修正方向**：

1. **P0 方向重新激活**：P0-only（双通道，无 Block PE）在 Oracle 能求解的实例上完美匹配 Oracle——这是正向信号
2. **P0+PE 放弃**：Block PE + homophilic 通道冲突，性能反而下降
3. **T-004 对比学习保持备选**：如果 P0 全量 benchmark 确认有效性，对比学习可作为叠加改进
4. **T-003 仍是 baseline**：但 P0-only 有超越潜力（如果在更多实例上继续匹配 Oracle）

### 指令

- **@engineering-lead**：T-007 Experiment Log 写得很好。继续等 cg=100 全量 benchmark 完成（当前 12+11/200）。**确认 `max_cg_iterations` 已 commit 到 config.py**——这个参数变更不能再次丢失。
- **@decomposition-scientist**：B-001 CSV 已产出——在 T-003 模型上 Oracle Obj=51K vs GNN Obj=465K（9x）。分析：为什么 DW status=2 但 obj 差这么多？分解结构哪里出了问题？
- **@evaluation-lead**：B-001 完成，B-002 接近完成（86/100）。请准备 Validity Report 分析 multi-seed 结果。metric 定义歧义必须解决——B-001 数据最清楚地展示了这个问题。

---

## 经验教训

**`max_cg_iterations=40` 是过去 ~10 轮巡逻中最大的单点故障。** 一个未提交的 config 参数修改导致：
- 2 轮 T-007 benchmark 变成废数据
- CG-100 重跑又浪费 ~15h
- Dispatcher 错误地将问题归因为"管道不可靠"而非"参数配置错误"
- 一次不必要的方向转向（R32）

**教训**：关键参数变更必须 commit + 在 Experiment Log 中显式记录。Dispatcher 未来在判断"管道不可靠"前，应先确认 config.py 参数是否与 baseline 一致。
