# Round 033 — T-003 Block-Structure PE Experiment

**日期**: 2026-05-28  
**角色**: Training Agent 1  
**任务**: T-003 Block-Structure Positional Encoding

## 完成的工作

### 1. 代码修改（7 个文件）
- `config.py`: 新增 `block_pe_dim=8`, `BLOCK_PE_PARAMS`
- `data_process.py`: 新增 `add_block_pe()` — 用 Louvain 社区检测在图结构上计算 block PE
- `02_generate_dataset.py`: 在 `extract()` 中调用 `add_block_pe()`
- `gnn_model.py`: encoder 输入维度扩展 (24→24+pe_dim+block_pe_dim, 18→18+pe_dim+block_pe_dim)
- `03_train_gnn.py`, `05_visualize_embeddings.py`, `06_eval_instances.py`: 传入 `block_pe_dim` 参数

### 2. 数据集升级
- 为 1200 个 .pt 文件增加 block_pe 属性（train=1000, valid=100, test=100）
- 每文件 ~0.1s（Louvain 社区检测），总计 ~2 分钟

### 3. 模型训练
- 50 epochs on V100 GPU
- Train Loss: 4.8716 → 4.3395, Val Loss: 4.5508 → 4.3909
- 从 epoch 27 起 plateau

### 4. DW 求解评估
- 100 test 实例，3 方法（Gurobi Direct + DW Oracle + DW GNN）

### 5. Bug 修复（07_solve_decomposition.py）
- `_SubGAPDWSolver.__init__`: 缺 `_col_age` 初始化 → cleanup_columns() 崩溃
- `_SubGAPDWSolver._add_gap_column`: 缺 `_col_age` append → 长度不匹配导致 IndexError
- 两个 bug 是 T-002 基线 GNN DW 路径的高失败率根因

## 结果

| 指标 | T-002 基线 | T-003 | 变化 |
|------|-----------|-------|------|
| DW Oracle OPT | 78/100 (78%) | 99/100 (99%) | +21pp |
| DW GNN OPT | 77/100 (77%) | 100/100 (100%) | +23pp |
| Type C GNN | 10/20 (50%) | 20/20 (100%) | +50pp |
| Type D GNN | 10/20 (50%) | 20/20 (100%) | +50pp |

## 注意事项
- Oracle 基线从 78% → 99% 也大幅提升，说明存在系统性改进（bug fix 影响）
- GNN→Oracle gap 从 -1pp 变为 +1pp（GNN 略优于 Oracle），Block PE 至少消除了 GNN 性能劣势
- Experiment Log: `knowledge/experiments/exp_T003_block_pe.md`

## 给 Engineering Lead
@engineering-lead T-003 完成。DW GNN 求解率 100%（vs baseline 77%）。发现并修复了 07_solve_decomposition.py 中 2 个导致 GNN DW 高失败率的 bug。Oracle 基线也提升了（78%→99%），建议 Evaluation Lead 独立验证归因。Block PE 的 Louvain 社区检测逻辑可供 T-004 复用。

Experiment Log: knowledge/experiments/exp_T003_block_pe.md
