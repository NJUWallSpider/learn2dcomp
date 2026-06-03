# Round 006 — T-008: 更新技术报告

**日期**: 2026-05-27
**工人**: worker-gamma
**任务**: T-008 — 根据最新实验结果更新 report.html

---

## 做了什么

### report.html 更新内容

1. **日期和版本号**：更新为 2026-05-27, Round 005 迭代
2. **Section 1.1 (gap_generator.py)**：更新 tightness 描述，注明 Type B=0.50 经实验调优，70% 实例 NodeCount>1
3. **Section 1.5 (辅助文件)**：删除 CFLP.py 文件卡片（已清理），更新 debug_*.py 卡片（8 个，注明 DW 调试保留）
4. **Section 2.1 (GAP 参数表)**：Type B tightness 从 1.20 更新为 0.50，加实验调优备注
5. **Section 5 (训练后差距)**：新增两个已修复 gap：
   - reassign_noise_points 根因修复（T-003 成果）
   - CFLP/UFLP 遗留代码清理（T-004 成果）
6. **Section 6 (工程管理)**：更新 CFLP 遗留代码条目为 generic_benders.py 仅剩
7. **Section 7 (路线图)**：Phase 5.4 标记为已完成 (Round 005)
8. **新增 Section 8 (实验结果)**：
   - 8.1 T-001: tightness 调优结果表（70% NodeCount>1）
   - 8.2 T-003: GNN≠Oracle 根因修复（obj 对比表）
   - 8.3 T-005: 数据集重建（1200/1200 成功，GCG 100%）
   - 8.4 T-006: GNN 重训练占位符（进行中，Epoch 23/50）
   - 8.5 T-002: DW 全量验证占位符（进行中）
9. **TOC**：新增 Section 8 链接
10. **Footer**：更新日期

### 当前进度总结

| 任务 | 状态 | 关键成果 |
|------|------|----------|
| T-001 | ✅ | Type B tightness 0.50, 70% NodeCount>1 |
| T-002 | 🟡 进行中 | DW benchmark 在 tmux dw_full 中运行 |
| T-003 | ✅ | 根因: reassign_noise_points 盲目合并噪声点 |
| T-004 | ✅ | CFLP/UFLP 清理，8 debug 文件保留 |
| T-005 | ✅ | 1200 实例数据集，GCG 100% 成功 |
| T-006 | 🔵 进行中 | Epoch 23/50, Train Loss ~4.34 |
| T-007 | ⬛ 阻塞 | 等待 T-002, T-006 |
| T-008 | ✅ | report.html 已更新 |

---

## 未解决问题

1. **T-002/T-006 仍在运行**：report.html 中留了占位符，需补充最终结果
2. **T-007 全流程评估**：阻塞中，需 T-002 和 T-006 都完成后才能开始
3. **report.html Section 8.4/8.5 占位符**：待 T-002/T-006 完成后需更新具体数值

---

## 给下一轮的经验教训

1. **report.html 是活文档**：每次实验迭代后应更新，不只是"做完项目后写"
2. **占位符策略可行**：对于依赖未完成任务的结果，先写占位符保证文档框架完整，后续填充数据即可
3. **Section 8 实验结果应成为常规**：每次 Round 后在其中追加新的结果卡片
4. **目前 5/8 任务完成**：T-006 (训练) 预计 30 min 内完成，T-002 (DW) 可能需要更久
