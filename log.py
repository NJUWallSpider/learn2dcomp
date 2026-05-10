import time
import csv
import math
import gurobipy as gp

# Gurobi状态码到可读字符串的映射
GUROBI_STATUS_MAP = {
    gp.GRB.LOADED: "LOADED",
    gp.GRB.OPTIMAL: "OPTIMAL",
    gp.GRB.INFEASIBLE: "INFEASIBLE",
    gp.GRB.INF_OR_UNBD: "INF_OR_UNBD",
    gp.GRB.UNBOUNDED: "UNBOUNDED",
    gp.GRB.CUTOFF: "CUTOFF",
    gp.GRB.ITERATION_LIMIT: "ITERATION_LIMIT",
    gp.GRB.NODE_LIMIT: "NODE_LIMIT",
    gp.GRB.TIME_LIMIT: "TIME_LIMIT",
    gp.GRB.SOLUTION_LIMIT: "SOLUTION_LIMIT",
    gp.GRB.INTERRUPTED: "INTERRUPTED",
    gp.GRB.NUMERIC: "NUMERIC",
    gp.GRB.SUBOPTIMAL: "SUBOPTIMAL",
    gp.GRB.INPROGRESS: "INPROGRESS",
    gp.GRB.USER_OBJ_LIMIT: "USER_OBJ_LIMIT",
}
 
# 初始化日志文件（如果不存在）
def init_log_file(log_file):
    with open(log_file, 'w', newline='') as f:
        writer = csv.writer(f)
        header = [
            "Problem", "Instance", "Relaxation", "TransformTime(s)", "SolveTime(s)",
            "Final_Gap(%)", "Final_Objective", "Total_Nodes",
            "Cuts_Added", "SolverStatus", "TerminationCondition"
        ]
        writer.writerow(header)

def _format_status(status_code):
    """将Gurobi状态码转换为可读字符串"""
    return GUROBI_STATUS_MAP.get(status_code, str(status_code))

# 记录单次运行结果
def log_performance(log_file, problem, instance_name, relaxation, transform_time, solve_time,
                   gap, objective, status, termination, nodes="N/A", cuts_added="N/A"):
    try:
        with open(log_file, 'a', newline='') as f:
            writer = csv.writer(f)
            row = [
                problem,
                instance_name,
                relaxation,
                f"{transform_time:.2f}",
                f"{solve_time:.2f}",
                f"{gap*100:.4f}" if isinstance(gap, (int, float)) else "N/A",
                f"{objective:.4f}" if isinstance(objective, (int, float)) else "N/A",
                nodes,
                cuts_added,
                _format_status(status),
                _format_status(termination)
            ]
            writer.writerow(row)
    except Exception as e:
        print(f"写入文件失败: {e}")
