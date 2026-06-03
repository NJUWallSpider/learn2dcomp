# Round 014 — 修复 finalize_mip() 硬编码 1e8（真正的污染源）

**时间**: 2026-05-30 13:50 CST
**工人**: worker-gamma
**任务**: T-012 — 验证 artificial_cost 修复，发现并修复真正的污染根因

---

## 发现

T-011 修复了 CG 阶段的 1e6 默认值，但验证时发现 Oracle obj 仍然膨胀。
根因是 `finalize_mip()` 中**第二个独立的问题**：

**`solvers/gap_dw.py:214`** — `finalize_mip()`:
```python
# 旧代码
huge_cost = 1e8   # ← 硬编码，覆盖 config 的 artificial_cost (1e5)
for var in self._artificial_vars:
    var.Obj = huge_cost
```

### 污染机制（两阶段）

| 阶段 | 旧行为 | 问题 |
|------|--------|------|
| CG LP | `self.artificial_cost` (曾是 1e6，T-011 修复后为 config 1e5) | T-011 已修复 |
| MIP | `huge_cost = 1e8` 硬编码 | **真正的污染源** — 每个残留人工变量贡献 1e8 |

实例 a15_t63_typeC_83 有 63 tasks → 63 个人工变量。MIP 解中有 2 个残留 → obj 膨胀 2×1e8 = 200,000,000。加上真实 cost ~5,000 = 200,005,060。

## 修复

### 修改的文件

**`solvers/gap_dw.py:210-223`** — `finalize_mip()`:
- 旧: `huge_cost = 1e8` 硬编码
- 新: 直接使用 `self.artificial_cost`（来自 config，当前 1e5）
- 理由: 与 CG 阶段保持一致，config 是唯一配置来源

**`solvers/gap_dw.py:225-239`** — 新增 `solve()` 覆盖:
- MIP 求解后检测人工变量使用情况
- 如果有人工变量 X > 0.5，打印警告并记录到 result dict
- `_SubGAPDWSolver` 通过继承自动获得此行为

### 影响范围

| 文件 | 改动 |
|------|------|
| `solvers/gap_dw.py` | `finalize_mip()`: 1 行删 + 1 行改；新增 `solve()`: 15 行 |

## 验证

```
Test 1: GAPDWSolver without artificial_cost → ValueError ✅
Test 2: GAPDWSolver with explicit value → PASS ✅
Test 3: grep 1e8 in gap_dw.py → 零残留 ✅
Test 4: solve() override contains artificial_vars_used check ✅
Test 5: a15_t63_typeC_83:
  - Oracle obj: 200,005,060 → 205,060 (1000× 减少)
  - 2 artificial vars detected ✅
  - DW FAILED correctly flagged
```

### 解释 205,060

205,060 = 2 × 100,000 (人工变量惩罚) + 5,060 (真实列成本)。Gurobi optimal = 4,908。
该实例的 DW 列集合无法形成可行的整数解（需 2 个人工变量覆盖 2 个 task），属于**合法 DW 失败**。

## 未解决问题

- **8 个 Type C 污染实例需重跑**：用修复后的代码重跑，区分"真 DW 失败"和"1e8 污染"
- **T-002 剩余 35 实例**：从未跑完
- **report.html 更新**：反映最终结果
- **人工变量失败的处理**：当前只标记 `artificial_vars_used`，调用方 (`07_solve_decomposition.py`) 可选择将 obj 设为 NaN 或保留惩罚值

## 经验教训

- **一个 bug 修完不代表问题解决**：T-011 修复了明面上的 1e6，但真正的污染来自 MIP 阶段的 1e8。两个独立问题叠加
- **硬编码是万恶之源**：`1e8` 分散在代码中，grep 1e6 找不到它。config 集中管理所有参数才能避免
- **验证修复时不要只看表面**：T-011 修复后如果直接 close，污染仍在。必须实际跑污染实例验证
