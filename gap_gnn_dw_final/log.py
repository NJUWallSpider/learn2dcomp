import csv

# SCIP status strings (from model.getStatus()) are already human-readable,
# but we keep a mapping for consistency/safety.
SCIP_STATUS_MAP = {
    "optimal": "OPTIMAL",
    "infeasible": "INFEASIBLE",
    "unbounded": "UNBOUNDED",
    "timelimit": "TIME_LIMIT",
    "gaplimit": "GAP_LIMIT",
    "nodelimit": "NODE_LIMIT",
    "sollimit": "SOLUTION_LIMIT",
    "userinterrupt": "INTERRUPTED",
    "memlimit": "MEMORY_LIMIT",
    "totalnodes": "TOTAL_NODES_LIMIT",
}


def init_log_file(log_file):
    with open(log_file, 'w', newline='') as f:
        writer = csv.writer(f)
        header = [
            "Problem", "Instance", "Method", "SolveTime(s)",
            "Final_Gap(%)", "Final_Objective", "Total_Nodes",
            "SolverStatus", "TerminationCondition"
        ]
        writer.writerow(header)


def _format_status(status_code):
    """Convert SCIP status string to a standardised label."""
    if isinstance(status_code, str):
        return SCIP_STATUS_MAP.get(status_code, status_code)
    return str(status_code)


def log_performance(log_file, problem, instance_name, method, solve_time,
                    gap, objective, status, termination, nodes="N/A"):
    try:
        with open(log_file, 'a', newline='') as f:
            writer = csv.writer(f)
            row = [
                problem,
                instance_name,
                method,
                f"{solve_time:.2f}",
                f"{gap*100:.4f}" if isinstance(gap, (int, float)) else "N/A",
                f"{objective:.4f}" if isinstance(objective, (int, float)) else "N/A",
                nodes,
                _format_status(status),
                _format_status(termination),
            ]
            writer.writerow(row)
    except Exception as e:
        print(f"Failed to write log: {e}")
