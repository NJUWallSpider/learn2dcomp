# Round 013 — 修复 artificial_cost 默认值 bug

**时间**: 2026-05-30 12:45 CST
**工人**: worker-gamma
**任务**: T-011 — 修复 artificial_cost 1e6 默认值覆盖 config 值

---

## 做了什么

修复了 `artificial_cost` 参数传递链中的危险默认值，确保 `config.py` 是唯一配置来源。

### 修改的文件

**`solvers/gap_dw.py:32-35`** — `GAPDWSolver.__init__()`:
- 旧: `artificial_cost=1e6` (危险默认值)
- 新: `artificial_cost=None` → `raise ValueError("artificial_cost must be provided")`
- 理由: 调用方必须显式传入 artificial_cost，静默使用 1e6 不再可能

**`07_solve_decomposition.py:170-175`** — `solve_gap_dw()`:
- 旧: `artificial_cost=1e6` (危险默认值)
- 新: `artificial_cost=None` → 从 `config.DW_PARAMS['artificial_cost']` 读取
- 理由: 调用方可能不传（如 quick_dw_eval.py），此时从 config 读取

**`07_solve_decomposition.py:480,514`** — 调用点:
- 旧: `config.DW_PARAMS.get('artificial_cost', 1e6)` (静默 fallback)
- 新: `config.DW_PARAMS['artificial_cost']` (KeyError 如果缺失)
- 理由: config 缺失时立即报错，不用隐藏的默认值

### 影响范围

| 文件 | 改动 |
|------|------|
| `solvers/gap_dw.py` | 1 行改 + 2 行加（默认值 + 检查） |
| `07_solve_decomposition.py` | 3 行改（默认值 + 两处 .get()） |

## 验证

- `grep -rn "1e6" solvers/gap_dw.py 07_solve_decomposition.py` → 无结果
- `_SubGAPDWSolver` 子类不受影响（已显式接收 artificial_cost 参数）
- `quick_dw_eval.py` 不受影响（已从 config 读取，通过 solve_gap_dw 的 None→config 路径）

## 未解决问题

- **需要重跑 Type C 实例验证修复**: 用新代码跑受影响的 8 个 Type C 实例，确认 Oracle obj 不再被膨胀
- **config 当前值为 1e5**: 需要确认 1e5 是否合适（之前是 1e3）。Type C 实例的 real costs 最高约 ~5000，1e5 是 20× margin，应该足够
- **T-002 剩余 35 实例**: 仍需要重跑
- **report.html**: 需更新最终结果

## 经验教训

- **永远不要在多个地方设默认值**: config → solve_gap_dw → GAPDWSolver 三层都有默认值是 bug 的根源。现在只有一处（config.py）
- **静默 fallback 是 bug 温床**: `.get(key, default)` 在 key 不存在时静默使用默认值。用 `[key]` 直接索引，缺失时立即 KeyError
- **证据驱动修复**: 即使代码路径看起来正确，也要相信数据证据（Oracle obj 膨胀到 N×1e8 只能用 1e6 解释）
