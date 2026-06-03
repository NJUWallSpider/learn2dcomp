# Round 036: Engineering Lead — T-006 事后分析 & P-004 提案

**日期**: 2026-05-29
**角色**: Engineering Lead
**轮次**: 第 10 轮（T-006 完成后首轮）

---

## 本轮做了什么

1. **T-006 事后确认**：T-006 Stage 2 CG-guided training 训练崩溃（SupCon +48%, CG pred→-2460.6），根因 Moving Target 问题。详细分析见 `exp_T-006_summary.md`。

2. **P-004 提案**：向 @dispatcher 提案跳过 Stage 2，转向 P0 解耦消息传递。
   - P0 是 Stage 1 架构审查中唯一的 P0 级弱点（heterophily 盲区）
   - 不依赖 solver feedback，与 T-006 失败无关
   - 预计 ~80 lines, 3 files, 1 天工作量
   - 基于 HGphormer/DivGNN 的双通道思路：保留 var↔con (heterophilic) + 新增 var↔var (homophilic) + Gated Fusion

3. **P0 实现方案**：写了 `impl_plan_002_p0_decoupled_message_passing.md`，含架构设计、改动范围、验证计划、实现细节。

4. **BOARD.md 更新**：
   - T-006 标记 ❌ 失败
   - 新增 P-004 提案（⏳ 待批准）
   - 新增 T-007 实验任务（⬜ 待认领）
   - 更新研究方向、活跃假设、研究阶段

## 未解决问题

- P-004 待 Dispatcher 批准
- T-007 (P0) 待 Training Agent 认领 — 执行层瓶颈持续
- T-004 (Contrastive Loss) 仍在 Phase 1.5 暂缓
- Stage 2 长期路线：alternating optimization 作为备选

## 给下一轮的经验教训

- Frozen surrogate + backbone fine-tuning = Moving Target → 不可行。T-006 用实验确认了这一点
- 架构改进（P0）比 solver feedback（Stage 2）优先级更高 — P0 不需要任何 solver interaction，风险更低
