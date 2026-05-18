# 完整的使用CGLP加速CFLP求解的代码，与其他代码无直接关联
import itertools
import log
import os
import time
import gurobipy as gp
from gurobipy import GRB
from CFLP import DataLoader

def lift_and_project_callback(model, where):
    """
    Gurobi 回调函数，用于在MIP节点上添加 lift-and-project cuts。
    """
    # 仅在MIP节点找到LP最优解时运行
    if where == gp.GRB.Callback.MIPNODE and model.cbGet(gp.GRB.Callback.MIPNODE_STATUS) == gp.GRB.OPTIMAL:
        # count = model.cbGet(gp.GRB.Callback.MIPNODE_NODCNT)
        # if count > 10:
        #     return

        if model._cuts_added > 1000:
            return

        # 获取LP松弛解的变量值
        y_vals = model.cbGetNodeRel(model._vars_y)
        x_vals = model.cbGetNodeRel(model._vars_x)
        facilities = model._facilities
        customers = model._customers
        
        # 遍历所有分数解的设施
        for i in facilities:
            # 只关心那些y[i]为分数的设施
            if 0.001 < y_vals[i] < 0.999:
                # 高效地遍历连接到该设施的客户
                for j in customers:
                    # 如果 x[i,j] > y[i]，则违反了约束
                    if x_vals[i, j] > y_vals[i] + 1e-6: # 使用一个小的容差
                        # 添加懒惰约束 (lazy cut)
                        model.cbLazy(model._vars_x[i, j] <= model._vars_y[i])
                        model._cuts_added += 1
        
        # if n_cuts_added > 0:
        #     print(f"Callback: 在节点上添加了 {n_cuts_added} 个 L&P cuts。")

def build_model(data_loader):
    # 加载数据
    n_facilities, n_customers, fixed_cost, capacity = data_loader.read_metadata()
    demands, costs = data_loader.read_data()
    customers = range(1, n_customers + 1)
    facilities = range(1, n_facilities + 1)
    valid_pairs = set(costs.keys())

    # 创建Gurobi模型
    model = gp.Model("CFLP")

    # 定义变量
    y = model.addVars(facilities, vtype=gp.GRB.BINARY)  # 设施开放状态
    # z = model.addVars(facilities, vtype=gp.GRB.BINARY)  # 设施关闭状态
    x = model.addVars(valid_pairs, lb=0, ub=1, vtype=gp.GRB.CONTINUOUS, name='x')  # 客户分配

    # for v in y.values():
    #     v.setAttr('BranchPriority', 10)
    # for v in z.values():
    #     v.setAttr('BranchPriority', 10)

    facility_to_customers = {i: [] for i in facilities}
    for i, j in valid_pairs:
        facility_to_customers[i].append(j)

    model._vars_y = y
    model._vars_x = x
    model._facilities = facilities
    model._customers = customers
    model._demands = demands
    model._capacity = capacity
    model._once = False
    model._cuts_added = 0
    model.update()

    # 目标函数：最小化总成本
    model.setObjective(
        y.prod(fixed_cost) + x.prod(costs),
        gp.GRB.MINIMIZE
    )

    # model.setObjective(
    #     sum(fixed_cost[i] * y[i] for i in facilities) + 
    #     sum(costs[i,j] * x[i,j] for i in facilities for j in customers),
    #     gp.GRB.MINIMIZE
    # )

    # 约束：每个客户的需求必须被满足
    model.addConstrs(
        (x.sum('*', j) == 1 for j in customers), name="demand"
    )

    # for j in customers:
    #     model.addConstr(
    #         sum(x[i,j] for i in facilities) >= 1,
    #         name=f"demand_{j}"
    #     )

    # Hull Reformulation
    # for i in facilities:
    #     model.addConstr(
    #         sum(demands[i,j] * x[i,j] for j in customers if (i,j) in valid_pairs) <= capacity * y[i],
    #     )
    #     for j in customers:
    #         if (i,j) in valid_pairs:
    #             model.addConstr(x[i,j] <= y[i])
    
    # big-M Reformulation
    M = 2000
    
    # 预处理 demands 以匹配 x 的索引
    demand_dict = gp.tupledict({(i, j): demands[j] for i, j in valid_pairs})

    # for i in facilities:
    #     y[i].VarName = f"ind_disjunction_{i}_disjunct_1"
    #     # z[i].VarName = f"ind_disjunction_{i}_disjunct_2"
    #     model.addConstr(
    #         x.prod(demand_dict, i, '*') <= capacity[i] + M * (1 - y[i]),
    #         name=f"c_disjunction_{i}_disjunct_1"
    #     )

        # model.addConstr(
        #     x.sum(i, '*') <= M * (1 - z[i]),
        #     name=f"c_disjunction_{i}_disjunct_2"
        # )


        # model.addConstr(y[i] + z[i] == 1)
        
    model.update() 
    model._cglp_models = {}

    for i in facilities:
        customers_for_i = facility_to_customers.get(i, [])

        cglp = gp.Model(f"CGLP_{i}")
        cglp.setParam('OutputFlag', 0)

        alpha = cglp.addVars(customers_for_i, lb=-1, ub=1, name="alpha")
        beta = cglp.addVar(lb=-1, ub=1, name="beta")
        delta = cglp.addVar(lb=-GRB.INFINITY, name="delta")

        u_x = cglp.addVar(lb=0, name="u_x")
        u_y = cglp.addVar(lb=-GRB.INFINITY, name="u_y")
        u_0 = cglp.addVars(customers_for_i, lb=0, name="u_0")
        u_1 = cglp.addVars(customers_for_i, lb=0, name="u_1")

        v_x = cglp.addVar(lb=0, name="v_x")
        v_y = cglp.addVar(lb=-GRB.INFINITY, name="v_y")
        v_0 = cglp.addVars(customers_for_i, lb=0, name="v_0")
        v_1 = cglp.addVars(customers_for_i, lb=0, name="v_1")

        for j in customers_for_i:
            cglp.addConstr(alpha[j] >= -u_x * demands[j] + u_0[j] - u_1[j])
            cglp.addConstr(alpha[j] <= -v_x + v_0[j] - v_1[j])
        cglp.addConstr(delta <= -capacity[i] * u_x - gp.quicksum(u_1[j] for j in customers_for_i) + u_y)
        cglp.addConstr(delta <= -gp.quicksum(v_0[j] for j in customers_for_i))
        cglp.addConstr(beta >= u_y)
        cglp.addConstr(beta >= v_y)

        model._cglp_models[i] = {'model': cglp, 'alpha': alpha, 'beta': beta, 'delta': delta}

    return model



def solve_and_log(model, log_file, instance_name, callback=None):
    """
    使用指定的策略求解模型，并记录性能指标。

    Args:
        model (gp.Model): 要解决的Gurobi模型。
        log_file (str): CSV日志文件的路径。
        instance_name (str): 当前求解的实例名称。
        strategy_name (str): 正在使用的求解策略的名称（例如 "Gurobi Default"）。
        callback (function, optional): 要在优化期间使用的回调函数。
    """

    
    # 重置模型并初始化自定义指标
    model.reset()
    model._cuts_added = 0
    model._initial_root_bound = None
    model._once = False
    model.update()

    # 设置模型参数
    model.setParam('TimeLimit', 150)
    model.setParam('Seed', 123)
    
    model.setParam('LazyConstraints', 1)
    # PreCrush=1 告知 Gurobi 我们将添加用户割平面，这有助于保留原始模型结构
    # model.setParam('PreCrush', 1)
    # model.setParam('Cuts', 0)
    # model.write(f"temp_{strategy_name}_valid.lp")
    t_start = time.time()
    model.optimize(callback)
    solve_time = time.time() - t_start

    # 收集指标
    final_objective = model.ObjVal if model.status in (GRB.OPTIMAL, GRB.TIME_LIMIT) else 'N/A'
    final_gap = model.MIPGap if model.status in (GRB.OPTIMAL, GRB.TIME_LIMIT) else 'N/A'
    total_nodes = model.NodeCount if hasattr(model, 'NodeCount') else 'N/A'
    status = model.status

    cuts_added = model._cuts_added
    
    # 记录到CSV
    log.log_performance(
        log_file, "CFLP", instance_name, "Gurobi_BranchPriority",
        transform_time=0, solve_time=solve_time, gap=final_gap, objective=final_objective,
        status=status, termination=model.status, nodes=total_nodes,
        cuts_added=cuts_added
    )
    print(f"    完成. 时间: {solve_time:.2f}s, 目标值: {final_objective}, Gap: {final_gap}, 节点数: {total_nodes}")
    

# 主程序
if __name__ == "__main__":
    path = 'data/raw/facilities/scale_50_200'  # 数据集路径
    log_file = 'results/CFLP_scale_50_200.csv'
    
    files = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
    files_with_path = [os.path.join(path, f) for f in files]
    
    if not os.path.exists(log_file):
        log.init_log_file(log_file)

    count = 0
    for file_path in files_with_path:
        instance_name = os.path.basename(file_path)
        print(f"\n正在求解实例 {instance_name}")
        
        data_loader = DataLoader(str(file_path))
        model = build_model(data_loader)

        solve_and_log(model, log_file, instance_name)

        if count >= 14:
            break
        count += 1

    print(f"\n评估完成。结果已保存到 {log_file}")