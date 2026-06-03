"""
GAP (Generalized Assignment Problem) synthetic instance generator.

Implements the five standard benchmark types from:

  Chu, P.C. & Beasley, J.E. (1997)
  "A genetic algorithm for the generalised assignment problem"
  Computers & Operations Research, 24(1), 17-23.

  Yagiura, M. et al. — extended Type E and large-scale instances.
  https://www-or.amp.i.kyoto-u.ac.jp/~yagiura/gap/

Type parameter ranges and capacity formulas match the OR-Library benchmark
distribution used by virtually all GAP papers.

Output: LP-format string with named variables x_{i}_{j} and named
constraints assign_{j} (linking) and cap_{i} (subproblem).
"""

import numpy as np


def generate_gap_instance(
    n_agents: int,
    n_tasks: int,
    rng: np.random.Generator,
    gap_type: str = "A",
) -> str:
    """
    Generate a GAP instance in LP format.

    Parameters
    ----------
    n_agents : int
        Number of agents (machines).  Each agent = one DW subproblem.
    n_tasks : int
        Number of tasks (jobs).
    rng : np.random.Generator
        Seeded random state for reproducibility.
    gap_type : str
        One of "A", "B", "C", "D", "E".  Determines the joint distribution
        of costs c_ij, resource consumptions a_ij, and capacity tightness.

    Returns
    -------
    str : LP file content.
    """
    costs, weights, capacities = _generate_gap_data(n_agents, n_tasks, rng, gap_type)

    lines = []
    lines.append(f"\\ GAP Type {gap_type} — {n_agents} agents × {n_tasks} tasks")
    lines.append("Minimize")
    obj_terms = []
    for i in range(n_agents):
        for j in range(n_tasks):
            if costs[i, j] != 0:
                sign = " + " if costs[i, j] >= 0 else " - "
                obj_terms.append(f"{sign}{abs(costs[i, j])} x_{i}_{j}")
    obj_str = "".join(obj_terms)
    if obj_str.startswith(" + "):
        obj_str = obj_str[3:]
    elif obj_str.startswith(" - "):
        obj_str = "-" + obj_str[3:]
    lines.append("  " + obj_str)

    lines.append("Subject To")

    # Assignment constraints (linking → master in DW)
    for j in range(n_tasks):
        terms = " + ".join(f"x_{i}_{j}" for i in range(n_agents))
        lines.append(f"  assign_{j}: {terms} = 1")

    # Capacity constraints (one per agent → subproblem in DW)
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
        if len(line) + len(v) + 1 > 250:   # LP format line limit is typically 255
            lines.append(line.rstrip())
            line = "   " + v + " "
        else:
            line += v + " "
    lines.append(line.rstrip())

    lines.append("End")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Core data generation — public so tests / other code can call it directly
# ---------------------------------------------------------------------------

def _generate_gap_data(
    n_agents: int,
    n_tasks: int,
    rng: np.random.Generator,
    gap_type: str,
):
    """Return (costs, weights, capacities) for a GAP instance."""

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
        raise ValueError(f"Unknown GAP type: {gap_type}. Use A, B, C, D, or E.")

    # Compute capacities
    capacities = _compute_capacities(weights, n_agents, n_tasks, gap_type)
    return costs, weights, capacities


# ---------------------------------------------------------------------------
# Per-type cost / weight generators
# ---------------------------------------------------------------------------

def _type_a(n_agents, n_tasks, rng):
    """
    Type A — independent, no correlation.

    c_ij ~ U_int[5,  25]
    a_ij ~ U_int[1,  25]
    """
    costs = rng.integers(5, 26, size=(n_agents, n_tasks)).astype(float)
    weights = rng.integers(1, 26, size=(n_agents, n_tasks)).astype(float)
    return costs, weights


def _type_b(n_agents, n_tasks, rng):
    """
    Type B — independent, wider range.

    c_ij ~ U_int[1, 100]
    a_ij ~ U_int[1, 100]
    """
    costs = rng.integers(1, 101, size=(n_agents, n_tasks)).astype(float)
    weights = rng.integers(1, 101, size=(n_agents, n_tasks)).astype(float)
    return costs, weights


def _type_c(n_agents, n_tasks, rng):
    """
    Type C — strong negative correlation (harder instances).

    a_ij ~ U_int[1, 50]
    c_ij = 111 - a_ij
    """
    weights = rng.integers(1, 51, size=(n_agents, n_tasks)).astype(float)
    costs = 111.0 - weights
    return costs, weights


def _type_d(n_agents, n_tasks, rng):
    """
    Type D — negative correlation with noise.

    a_ij ~ U_int[1, 50]
    c_ij = 111 - a_ij + ε,  ε ~ U_int[-5, 5]
    """
    weights = rng.integers(1, 51, size=(n_agents, n_tasks)).astype(float)
    noise = rng.integers(-5, 6, size=(n_agents, n_tasks)).astype(float)
    costs = 111.0 - weights + noise
    costs = np.maximum(costs, 1.0)  # costs shouldn't go negative
    return costs, weights


def _type_e(n_agents, n_tasks, rng):
    """
    Type E — positive correlation (large-scale benchmark, Yagiura et al.).

    c_ij ~ U_int[1, 100]
    a_ij = c_ij / 100 + ε,   ε ~ U_cont[-0.2, 0.2]

    High-cost tasks consume more resources (positive correlation).
    Rescaled to integer [1, 25].
    """
    costs = rng.integers(1, 101, size=(n_agents, n_tasks)).astype(float)
    eps = rng.uniform(-0.2, 0.2, size=(n_agents, n_tasks))
    weights_raw = costs / 100.0 + eps
    # Rescale to [1, 25] integer range while preserving the positive correlation
    w_min, w_max = weights_raw.min(), weights_raw.max()
    if w_max - w_min < 1e-9:
        weights = np.full_like(weights_raw, 13.0)
    else:
        weights = 1.0 + 24.0 * (weights_raw - w_min) / (w_max - w_min)
    weights = np.round(weights)
    weights = np.clip(weights, 1, 25)
    return costs, weights


# ---------------------------------------------------------------------------
# Capacity computation
# ---------------------------------------------------------------------------

def _compute_capacities(weights, n_agents, n_tasks, gap_type):
    """
    Capacity formula based on per-task average weight.

        b_i = tightness × (n_tasks / n_agents) × avg_weight

    where avg_weight = total_weight / (n_agents × n_tasks).

    This ensures consistent tightness across different agent counts.
    tightness = 1.2 means each agent has 20% more capacity than its "fair share"
    of the total task weight. Lower = tighter = harder.
    """
    tightness = {"A": 1.30, "B": 0.50, "C": 1.30, "D": 1.30, "E": 1.30}[gap_type]
    total_weight = weights.sum()
    avg_weight = total_weight / (n_agents * n_tasks)
    fair_share = n_tasks / n_agents * avg_weight
    base_cap = int(tightness * fair_share)

    # Every task must fit in at least one agent, otherwise infeasible.
    min_w_per_task = weights.min(axis=0)   # shape (n_tasks,)
    min_feasible_cap = int(min_w_per_task.max()) + 1

    capacity = max(base_cap, min_feasible_cap)
    capacities = np.full(n_agents, capacity, dtype=float)
    return capacities
