# 提供从CFLP的txt格式算例读取数据和建立模型的函数
import pyomo.environ as pyo
from pyomo.gdp import *
import gurobipy as gp
from gurobipy import GRB
import numpy as np

class DataLoader:
    def __init__(self, file_path):
        self.n_facilities = 0
        self.n_customers = 0
        self.fixed_costs = {} # (设施ID): 固定成本
        self.capacities = {}  # (设施ID): 容量

        self.demands = {}      # 客户ID: 需求
        self.transport_costs = {}  # (设施ID, 客户ID): 运输成本
        with open(file_path, 'r') as file:
            self.lines = file.readlines()

    def read_metadata(self):
        """
        Return:
            n_facilities
            n_customers
            fixed_costs (dict)
            capacities (dict)
        """
        # 跳过空行和'Code'行
        line_idx = 3
        meta_data = self.lines[line_idx].strip().split()
        self.n_facilities = int(meta_data[0])
        self.n_customers = int(meta_data[1])

        # 读取每个设施的固定成本和容量
        line_idx += 2 # 跳过 "Fixed Cost  Capacity" header
        for i in range(self.n_facilities):
            facility_id = i + 1
            parts = self.lines[line_idx + i].strip().split()
            self.fixed_costs[facility_id] = float(parts[0])
            self.capacities[facility_id] = int(parts[1])
        
        return self.n_facilities, self.n_customers, self.fixed_costs, self.capacities

    def read_data(self):
        """
        Return:
            self.demands (dict)
            self.transport_costs (dict)
        """
        if not self.n_facilities:
            self.read_metadata()

        # 定位到 "Demand & Transportation Cost" 部分
        start_idx = 0
        while self.lines[start_idx].strip() != "Demand & Transportation Cost":
            start_idx += 1

        # 优化：一次性读取所有数据行，然后用Numpy处理
        line_idx = start_idx + 1 # 指向第一个客户的需求行
        
        # 每个客户占用两行（需求和成本）
        end_idx = line_idx + self.n_customers * 2
        data_lines = [line.strip().split() for line in self.lines[line_idx:end_idx]]

        # 从交错的行中提取需求和成本
        demand_lines = data_lines[0::2]
        cost_lines = data_lines[1::2]

        for j in range(self.n_customers):
            customer_id = j + 1
            self.demands[customer_id] = int(demand_lines[j][1])
            
            # 使用Numpy解析成本行，比Python循环更快
            costs_for_customer = np.array(cost_lines[j], dtype=np.float64)
            for i in range(self.n_facilities):
                facility_id = i + 1
                cost = costs_for_customer[i]
                if cost < 1e9:
                    self.transport_costs[facility_id, customer_id] = cost

        return self.demands, self.transport_costs

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
    z = model.addVars(facilities, vtype=gp.GRB.BINARY)  # 设施关闭状态
    x = model.addVars(valid_pairs, lb=0, ub=1, vtype=gp.GRB.CONTINUOUS, name='x')  # 客户分配

    facility_to_customers = {i: [] for i in facilities}
    for i, j in valid_pairs:
        facility_to_customers[i].append(j)

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

    # Rename x variables based on customer (j) instead of facility (i)
    for i, j in valid_pairs:
        x[i, j].VarName = f"subproblem_{j}_x_{i}_{j}"

    for i in facilities:
        y[i].VarName = f"master_y_{i}"
        z[i].VarName = f"master_z_{i}"
        model.addConstr(
            x.prod(demand_dict, i, '*') <= capacity[i] + M * (1 - y[i]),
            name=f"c_disjunction_{i}_disjunct_1"
        )

        model.addConstr(
            x.sum(i, '*') <= M * (1 - z[i]),
            name=f"c_disjunction_{i}_disjunct_2"
        )

        model.addConstr(y[i] + z[i] == 1)

        # model.addConstr(
        #     x.prod(demand_dict, i, '*') <= capacity[i] * y[i],
        #     name=f"c_disjunction_{i}_disjunct_1"
        # )

    model.update()
    return model