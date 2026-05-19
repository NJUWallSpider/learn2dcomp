# 完整的使用CGLP加速CFLP求解的代码，与其他代码无直接关联
import itertools
import log
import os
import time
import gurobipy as gp
from gurobipy import GRB
from CFLP import DataLoader

def build_model(data_loader):
    # 加载数据
    n_facilities, n_customers, fixed_cost, capacity = data_loader.read_metadata()
    demands, costs = data_loader.read_data()
    customers = range(1, n_customers + 1)
    facilities = range(1, n_facilities + 1)
    valid_pairs = set(costs.keys())

    # 创建Gurobi模型
    model = gp.Model("UFLP")

    # 定义变量
    y = model.addVars(facilities, vtype=gp.GRB.BINARY)  # 设施开放状态
    x = model.addVars(valid_pairs, lb=0, ub=1, vtype=gp.GRB.CONTINUOUS, name='x')  # 客户分配

    for i, j in valid_pairs:
        x[i, j].VarName = f"subproblem_{j}_x_{i}_{j}"
    for i in facilities:
        y[i].VarName = f"master_y_{i}"


    # 目标函数：最小化总成本
    model.setObjective(
        y.prod(fixed_cost) + x.prod(costs),
        gp.GRB.MINIMIZE
    )

    # 约束：每个客户的需求必须被满足
    model.addConstrs(
        (x.sum('*', j) == 1 for j in customers), name="demand"
    )

    model.addConstrs(
        (x[i, j] <= y[i] for i, j in valid_pairs), name="linkage"
    )

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

    # 设置模型参数
    model.setParam('TimeLimit', 150)
    model.setParam('Seed', 123)
    
    t_start = time.time()
    model.optimize(callback)
    solve_time = time.time() - t_start

    # 收集指标
    final_objective = model.ObjVal if model.status in (GRB.OPTIMAL, GRB.TIME_LIMIT) else 'N/A'
    final_gap = model.MIPGap if model.status in (GRB.OPTIMAL, GRB.TIME_LIMIT) else 'N/A'
    total_nodes = model.NodeCount if hasattr(model, 'NodeCount') else 'N/A'
    status = model.status

    cuts_added = 0
    
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
    path = 'data/raw/facilities/test'  # 数据集路径
    log_file = 'results/CFLP_test.csv'
    
    files = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
    files = sorted(files)
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

        # break

        # if count >= 1:
        #     break
        # count += 1

    print(f"\n评估完成。结果已保存到 {log_file}")