"""
GAP (Generalized Assignment Problem) synthetic instance generator.

Implements five standard benchmark types from:
  Chu, P.C. & Beasley, J.E. (1997)
  "A genetic algorithm for the generalised assignment problem"
  Computers & Operations Research, 24(1), 17-23.

Output: LP-format string.
"""
import numpy as np


def generate_gap_lp(n_agents: int, n_tasks: int,
                     rng: np.random.Generator,
                     gap_type: str = "A") -> str:
    """Generate a GAP instance in LP format."""
    costs, weights, capacities = _generate_gap_data(n_agents, n_tasks, rng,
                                                     gap_type)
    lines = [f"\\ GAP Type {gap_type} — {n_agents} agents x {n_tasks} tasks",
             "Minimize"]
    obj_terms = []
    for i in range(n_agents):
        for j in range(n_tasks):
            c = costs[i, j]
            if c != 0:
                sign = " + " if c >= 0 else " - "
                obj_terms.append(f"{sign}{abs(c)} x_{i}_{j}")
    obj_str = "".join(obj_terms)
    if obj_str.startswith(" + "): obj_str = obj_str[3:]
    elif obj_str.startswith(" - "): obj_str = "-" + obj_str[3:]
    lines.append("  " + obj_str)
    lines.append("Subject To")
    for j in range(n_tasks):
        terms = " + ".join(f"x_{i}_{j}" for i in range(n_agents))
        lines.append(f"  assign_{j}: {terms} = 1")
    for i in range(n_agents):
        nz = [(j, weights[i, j]) for j in range(n_tasks) if weights[i, j] != 0]
        if nz:
            terms = " + ".join(f"{w} x_{i}_{j}" for j, w in nz)
            lines.append(f"  cap_{i}: {terms} <= {capacities[i]}")
    lines.append("Bounds")
    for i in range(n_agents):
        for j in range(n_tasks):
            lines.append(f"  0 <= x_{i}_{j} <= 1")
    lines.append("Binaries")
    var_names = [f"x_{i}_{j}" for i in range(n_agents) for j in range(n_tasks)]
    line = "  "
    for v in var_names:
        if len(line) + len(v) + 1 > 250:
            lines.append(line.rstrip())
            line = "   " + v + " "
        else:
            line += v + " "
    lines.append(line.rstrip())
    lines.append("End")
    return "\n".join(lines) + "\n"


def generate_gap_txt(n_agents, n_tasks, rng, gap_type="A", filepath=None):
    """Generate GAP in our .txt format for backward compatibility."""
    costs, weights, capacities = _generate_gap_data(n_agents, n_tasks, rng,
                                                     gap_type)
    n_jobs, n_machines = n_tasks, n_agents
    lines = [f"{n_jobs} {n_machines}"]
    for j in range(n_jobs):
        lines.append(" ".join(str(int(costs[i, j])) for i in range(n_machines)))
    for j in range(n_jobs):
        lines.append(" ".join(str(int(weights[i, j])) for i in range(n_machines)))
    lines.append(" ".join(str(int(capacities[i])) for i in range(n_machines)))
    content = "\n".join(lines) + "\n"
    if filepath:
        from pathlib import Path
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        Path(filepath).write_text(content)
    return content


# ---------------------------------------------------------------------------
# Core data generation
# ---------------------------------------------------------------------------

def _generate_gap_data(n_agents, n_tasks, rng, gap_type):
    if gap_type == "A":
        costs, weights = _type_a(n_agents, n_tasks, rng)
    elif gap_type == "B":
        costs, weights = _type_b(n_agents, n_tasks, rng)
    elif gap_type == "C":
        costs, weights = _type_c(n_agents, n_tasks, rng)
    elif gap_type == "D":
        costs, weights = _type_d(n_agents, n_tasks, rng)
    elif gap_type == "E":
        costs, weights = _type_e(n_agents, n_tasks, rng)
    else:
        raise ValueError(f"Unknown GAP type: {gap_type}")
    capacities = _compute_capacities(weights, n_agents, n_tasks, gap_type)
    return costs, weights, capacities


def _type_a(n_agents, n_tasks, rng):
    costs = rng.integers(5, 26, size=(n_agents, n_tasks)).astype(float)
    weights = rng.integers(1, 26, size=(n_agents, n_tasks)).astype(float)
    return costs, weights


def _type_b(n_agents, n_tasks, rng):
    costs = rng.integers(1, 101, size=(n_agents, n_tasks)).astype(float)
    weights = rng.integers(1, 101, size=(n_agents, n_tasks)).astype(float)
    return costs, weights


def _type_c(n_agents, n_tasks, rng):
    """Type C — strong negative correlation (harder instances). c_ij = 111 - a_ij"""
    weights = rng.integers(1, 51, size=(n_agents, n_tasks)).astype(float)
    costs = 111.0 - weights
    return costs, weights


def _type_d(n_agents, n_tasks, rng):
    """Type D — negative correlation with noise. c_ij = 111 - a_ij + eps"""
    weights = rng.integers(1, 51, size=(n_agents, n_tasks)).astype(float)
    noise = rng.integers(-5, 6, size=(n_agents, n_tasks)).astype(float)
    costs = 111.0 - weights + noise
    costs = np.maximum(costs, 1.0)
    return costs, weights


def _type_e(n_agents, n_tasks, rng):
    """Type E — positive correlation, large-scale benchmark."""
    costs = rng.integers(1, 101, size=(n_agents, n_tasks)).astype(float)
    eps = rng.uniform(-0.2, 0.2, size=(n_agents, n_tasks))
    weights_raw = costs / 100.0 + eps
    w_min, w_max = weights_raw.min(), weights_raw.max()
    if w_max - w_min < 1e-9:
        weights = np.full_like(weights_raw, 13.0)
    else:
        weights = 1.0 + 24.0 * (weights_raw - w_min) / (w_max - w_min)
    weights = np.round(np.clip(weights, 1, 25))
    return costs, weights


def _compute_capacities(weights, n_agents, n_tasks, gap_type):
    tightness = {"A": 1.30, "B": 0.50, "C": 1.30, "D": 1.30, "E": 1.30}[gap_type]
    total_weight = weights.sum()
    avg_weight = total_weight / (n_agents * n_tasks)
    fair_share = n_tasks / n_agents * avg_weight
    base_cap = int(tightness * fair_share)
    min_w_per_task = weights.min(axis=0)
    min_feasible_cap = int(min_w_per_task.max()) + 1
    capacity = max(base_cap, min_feasible_cap)
    return np.full(n_agents, capacity, dtype=int)


def parse_lp_dims(lp_text):
    """Extract n_agents, n_tasks from LP variable names."""
    import re
    agents, tasks = set(), set()
    for m in re.finditer(r'x_(\d+)_(\d+)', lp_text):
        agents.add(int(m.group(1))); tasks.add(int(m.group(2)))
    return max(agents) + 1, max(tasks) + 1


def lp_to_txt(lp_text, txt_path):
    """Convert LP format to our .txt format for GAPInstance loading."""
    import re
    na, nt = parse_lp_dims(lp_text)
    costs = np.zeros((na, nt), dtype=float)
    weights = np.zeros((na, nt), dtype=float)
    capacities = np.zeros(na, dtype=float)
    obj_match = re.search(r'Minimize\s*\n\s*(.+)', lp_text, re.DOTALL)
    if obj_match:
        obj_line = obj_match.group(1).replace('\n', ' ')
        for m in re.finditer(r'([+-]?\s*\d+(?:\.\d+)?)\s*x_(\d+)_(\d+)', obj_line):
            val = float(m.group(1).replace(' ', ''))
            i, j = int(m.group(2)), int(m.group(3))
            costs[i, j] = val
    for m in re.finditer(r'cap_(\d+):\s*(.+?)\s*<=?\s*(\d+)', lp_text):
        i = int(m.group(1))
        expr = m.group(2)
        capacities[i] = float(m.group(3))
        for wm in re.finditer(r'(\d+)\s*x_(\d+)_(\d+)', expr):
            w = float(wm.group(1))
            _, j = int(wm.group(2)), int(wm.group(3))
            weights[i, j] = w
    n_jobs, n_machines = nt, na
    with open(txt_path, 'w') as f:
        f.write(f"{n_jobs} {n_machines}\n")
        for j in range(n_jobs):
            f.write(" ".join(str(int(costs[i, j])) for i in range(n_machines)) + "\n")
        for j in range(n_jobs):
            f.write(" ".join(str(int(weights[i, j])) for i in range(n_machines)) + "\n")
        f.write(" ".join(str(int(capacities[i])) for i in range(n_machines)) + "\n")
