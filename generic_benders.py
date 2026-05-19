import gurobipy as gp
from gurobipy import GRB
from abc import ABC, abstractmethod

class GenericBenders(ABC):
    """
    通用多切平面 Benders 分解框架 (Multi-cut L-shaped Method)
    适用于：随机规划、N个独立子块问题。
    特点：基于原问题构建，自动处理 RHS 更新和 Cut 生成。
    """
    def __init__(self, n_scenarios, probabilities=None, name="GenericBenders", eta_lb=-GRB.INFINITY):
        self.n_scenarios = n_scenarios
        # 如果未提供概率，默认等概率
        if probabilities is None:
            self.probs = [1.0 / n_scenarios] * n_scenarios
        else:
            self.probs = probabilities
        
        self.eta_lb = eta_lb
            
        self.master = gp.Model(f"{name}_Master")
        self.subs = []  # 存储 N 个子问题模型
        
        # --- 关键配置 ---
        self.master.Params.LazyConstraints = 1
        self.master_vars = None
        self.etas = []  # 存储 N 个 eta 变量 [eta_0, eta_1, ...]

    @abstractmethod
    def build_master(self, model):
        """
        构建主问题变量和静态约束。
        返回: 主问题变量容器 (dict, list, etc.)
        注意: 不要在此处 setObjective，只需定义变量。
        """
        pass
    
    @abstractmethod
    def get_master_cost(self, master_vars):
        """
        返回第一阶段（主问题）的直接成本表达式。
        """
        pass

    @abstractmethod
    def build_subproblem(self, model, scenario_id):
        """
        构建第 k 个子问题 (原问题形式)。
        返回: 任何你需要在后续引用的数据结构 (通常无需返回，存入 model._info 即可)
        """
        pass

    @abstractmethod
    def get_linking_map(self, sub_model, scenario_id, master_vars):
        """
        【核心方法】定义子问题约束与主问题变量的连接关系。
        
        必须返回一个字典 (Dict):
        {
            Constraint_Object: RHS_Expression
        }
        
        - Constraint_Object: 子问题中的 Gurobi 约束对象。
        - RHS_Expression: 该约束对应的右端项表达式 (可以是常数，也可以包含 master_vars)。
        
        框架会利用这个字典做两件事：
        1. 数值更新: 计算 RHS_Expression 的值赋给 Constraint.RHS
        2. 生成 Cut: 计算 Constraint.Pi * RHS_Expression 添加到主问题
        """
        pass

    def _init_models(self):
        # 1. 构建主问题
        self.master_vars = self.build_master(self.master)
        
        # 2. 为每个场景添加 eta 变量 (代表第二阶段成本)
        # 目标函数: Min MasterCost + sum(p_s * eta_s)
        self.etas = []
        obj_expr = self.get_master_cost(self.master_vars)
        
        for s in range(self.n_scenarios):
            # 使用初始化时指定的 eta 下界
            eta = self.master.addVar(lb=self.eta_lb, name=f"eta_{s}")
            self.etas.append(eta)
            obj_expr += self.probs[s] * eta
            
            # 3. 构建子问题
            sub = gp.Model(f"Sub_{s}")
            sub.Params.OutputFlag = 0
            sub.Params.InfUnbdInfo = 1 # 允许获取 FarkasDual
            sub.Params.DualReductions = 0
            self.build_subproblem(sub, s)
            self.subs.append(sub)
            
        self.master.setObjective(obj_expr, GRB.MINIMIZE)

    def _callback(self, model, where):
        if where == GRB.Callback.MIPSOL:
            # 1. 获取主问题数值解
            # 为了支持 evaluate_expr 解析任意包含 master_vars 的表达式，
            # 我们需要构建一个 Var -> Value 的映射。
            # 最稳健的方法是获取所有变量的值。
            all_vars = self.master.getVars()
            all_vals = model.cbGetSolution(all_vars)
            val_map = {v: val for v, val in zip(all_vars, all_vals)}
            
            eta_vals = model.cbGetSolution(self.etas)
            
            # 2. 循环处理每一个场景 (子问题)
            for s in range(self.n_scenarios):
                sub_model = self.subs[s]
                
                # --- A. 获取连接映射 (Linking Map) ---
                link_map = self.get_linking_map(sub_model, s, self.master_vars)
                
                # --- B. 更新并求解子问题 ---
                # 遍历映射，更新 RHS
                for constr, rhs_expr in link_map.items():
                    # 计算 rhs_expr 在当前 x_vals 下的数值
                    if isinstance(rhs_expr, gp.LinExpr) or isinstance(rhs_expr, gp.Var):
                        rhs_val = self._evaluate_expr(rhs_expr, val_map)
                        constr.RHS = rhs_val
                    else:
                        constr.RHS = rhs_expr
                
                sub_model.optimize()
                
                # --- C. 生成 Cuts ---
                status = sub_model.Status
                
                if status == GRB.OPTIMAL:
                    # Optimality Cut
                    sub_obj = sub_model.ObjVal
                    # 检查是否违反估值: eta_s < sub_obj
                    if sub_obj > eta_vals[s] + 1e-6:
                        # 构建 Cut: eta_s >= sum(Pi * RHS_Expr)
                        cut_expr = gp.LinExpr()
                        # 遍历所有约束
                        for constr in sub_model.getConstrs():
                            rhs_expr = link_map.get(constr, constr.RHS)
                            cut_expr += constr.Pi * rhs_expr
                        
                        # 添加 Cut
                        model.cbLazy(self.etas[s] >= cut_expr)
                        
                elif status == GRB.INF_OR_UNBD or status == GRB.INFEASIBLE:
                    # Feasibility Cut
                    # 构建 Cut: 0 >= sum(FarkasDual * RHS_Expr)
                    cut_expr = gp.LinExpr()
                    for constr in sub_model.getConstrs():
                        rhs_expr = link_map.get(constr, constr.RHS)
                        cut_expr += constr.FarkasDual * rhs_expr
                    
                    model.cbLazy(cut_expr >= 0)

    def _evaluate_expr(self, expr, val_map):
        """辅助函数：计算 Gurobi 表达式在给定解下的数值"""
        if isinstance(expr, (float, int)):
            return expr
            
        # 手动计算 LinExpr = sum(coeff * var) + const
        val = 0.0
        if isinstance(expr, gp.Var):
             return val_map.get(expr, 0.0)
             
        if isinstance(expr, gp.LinExpr):
            for i in range(expr.size()):
                var = expr.getVar(i)
                coeff = expr.getCoeff(i)
                val += coeff * val_map.get(var, 0.0)
            val += expr.getConstant()
            return val
        return 0.0

    def solve(self):
        """
        求解 Benders 分解问题。
        
        Args:
            time_limit (float, optional): 时间限制 (秒)。
            mip_gap (float, optional): 相对 MIP Gap 停止条件 (默认 1e-4, 即 0.01%)。
                                       在 Branch-and-Cut 模式下，当 (UB-LB)/UB < mip_gap 时停止。
            log_file (str, optional): Gurobi 日志文件路径。
        """
        self._init_models()
        
        # 开启 Gurobi 日志以便用户看到 Gap 收敛过程
        self.master.setParam('OutputFlag', 1) 

        self.master.optimize(self._callback)