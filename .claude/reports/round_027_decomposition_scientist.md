# Round 027: Add Decomposition Scientist + 3-Stage Research Roadmap

## 改动文件

### 新建
- `.claude/dispatch/DECOMPOSITION_SCIENTIST_PROTOCOL.md` — 分解科学家协议
- `knowledge/decomposition/` + `.gitkeep` — 分解分析记录目录

### 修改
- `.claude/dispatch/DISPATCHER.md` — §2 巡检循环加入 Decomposition Scientist 状态检查；§4 "你指挥谁"加入 @decomposition-scientist；新增分解分析指令格式
- `.claude/dispatch/BOARD.md` — 角色状态表加入 Decomposition Scientist；知识库索引加入 decomposition/；任务队列加入分解分析任务类型；调度日志记录新增
- `CLAUDE.md` — 角色表从 8 个更新为 9 个（新增 L2 科学层）；身份识别加入 Decomposition Scientist 分支；科研闭环加入 Decomposition Analysis 步骤；调度文件表更新
- `.claude/dispatch/RULES.md` — 开头修复（"三个角色" → "所有角色"）；§3 神圣文件加入 `knowledge/**/*.md`；§7 角色速查加入 Decomposition Scientist
- `.claude/dispatch/ONBOARDING.md` — 架构图更新（3 Leads + 1 Scientist）；角色表更新；科研闭环更新；指挥链更新；附录加入 /loop 启动命令
- `.claude/dispatch/RESEARCH_LEAD_PROTOCOL.md` — §0 加入 3 阶段研究路线图意识 + 核心命题
- `knowledge/README.md` — 目录结构表加入 decomposition/

## 核心设计

### Decomposition Scientist 的定位
- **科学层**（和 3 位 Lead 同级，直接向 Dispatcher 汇报）
- 核心问题："为什么这个实例适合这种分解？什么样的块划分真正帮助求解器？"
- 核心命题：**最好的分解未必是最像 GCG 的分解，而是让求解器最快收敛的分解**
- 分析维度：块结构特征（块数量/大小分布/重叠度）、图结构特征（模块度/传导度/谱隙）、求解器反馈（CG 迭代/LP Gap/B&P 节点/最终时间）
- 产出：Decomposition Analysis Report → `knowledge/decomposition/analysis_XXX_简述.md`
- 关联：Research Lead（文献调研）+ Engineering Lead（实现建议）+ Dispatcher（方向决策）

### 3 阶段研究路线图
- Stage 1: Teacher Distillation（GNN ≈ GCG）— 当前阶段
- Stage 2: Solver Feedback — 直接优化求解器表现而非 label 准确率
- Stage 3: End-to-End Learn-to-Decompose — 闭环端到端优化最终求解时间

## 验证

- Decomposition Scientist 协议文件已创建，遵循统一结构（§0-§6）
- `knowledge/decomposition/` 目录已创建
- 所有 7 个更新文件均已验证修改正确
- 9 个角色体系：Dispatcher + 3 Leads + Decomposition Scientist + 3 Agent pools + Knowledge Agent

## 待办

- 首次冷启动测试：新 Claude Code 说"我是 Decomposition Scientist"→ 能正确读取协议并理解自己职责
- `knowledge/decomposition/INDEX.md` 需要在首次分析报告产出后由 Decomposition Scientist 自己创建
