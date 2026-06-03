# Round 005 — 仓库清理 (T-004)

**日期**: 2026-05-27
**工人**: worker-beta (替 gamma 执行)
**任务**: T-004 — 删除 CFLP/UFLP 残留，保留 debug 文件

---

## 执行内容

删除了以下废弃文件:
- `CFLP_gurobi.py` — CFLP 项目残留
- `CFLP.py` — (不存在)
- `UFLP_Benders.py` — UFLP 项目残留
- `UFLP_gurobi.py` — UFLP 项目残留

清理了所有 `__pycache__` 目录。

保留了 8 个 debug_*.py 文件:
- debug_check_dim.py
- debug_clustering.py
- debug_dataloader.py
- debug_license.py
- debug_params.py
- debug_rmp.py
- debug_rmp2.py
- debug_step2.py

## 验证

- CFLP/UFLP 文件确认已删除（`ls CFLP_*.py UFLP_*.py` 返回空）
- debug_*.py 文件完整保留
- 无 `__pycache__` 目录残留
