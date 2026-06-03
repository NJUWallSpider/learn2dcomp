"""
Interface to the GCG solver for automatic Dantzig-Wolfe decomposition detection.

Runs GCG as a subprocess, parses the .dec decomposition file to extract
constraint-to-block assignments, which serve as ground-truth labels for GNN training.
"""

import subprocess
import re
import time
from pathlib import Path


def run_gcg(
    mps_path: Path,
    dec_path: Path,
    gcg_binary: str = "gcg",
    time_limit: int = 60,
) -> bool:
    """
    Run GCG on an MPS file to detect decomposition, write the .dec file.

    Returns True on success, False on failure.
    """
    # GCG does not allow mixing -f with -c; pipe commands via stdin instead.
    dec_path.parent.mkdir(parents=True, exist_ok=True)
    commands = (
        f"read {mps_path}\n"
        f"detect\n"
        f"write problem {dec_path}\n"
        "quit\n"
    )
    try:
        result = subprocess.run(
            [gcg_binary, "-q"],
            input=commands,
            capture_output=True,
            text=True,
            timeout=time_limit + 30,
        )
        if dec_path.exists() and dec_path.stat().st_size > 0:
            return True
        # GCG may fail if the problem is too small or trivial;
        # check stderr for hints
        if result.returncode != 0:
            print(f"  GCG returned non-zero: {result.returncode}")
            if result.stderr:
                # print last few lines
                stderr_tail = result.stderr.strip().split("\n")[-5:]
                print("  stderr tail:", "\n".join(stderr_tail))
        return False
    except subprocess.TimeoutExpired:
        print(f"  GCG timed out on {mps_path}")
        return False
    except FileNotFoundError:
        print(f"  GCG binary '{gcg_binary}' not found. Is GCG installed and on PATH?")
        return False


def parse_dec(dec_path: Path) -> dict:
    """
    Parse a GCG .dec file.

    Returns
    -------
    dict with keys:
        'n_blocks': int
        'master_conss': list of constraint name strings
        'block_conss': dict {block_id (int): [constraint names]}
    """
    if not dec_path.exists():
        raise FileNotFoundError(f".dec file not found: {dec_path}")

    text = dec_path.read_text()

    n_blocks = 0
    master_conss = []
    block_conss = {}

    # Strip comments (lines starting with backslash)
    lines = [line.strip() for line in text.splitlines()
             if line.strip() and not line.strip().startswith("\\")]

    i = 0
    while i < len(lines):
        line = lines[i]

        if line.upper() == "PRESOLVED":
            i += 1
            continue

        if line.upper() == "NBLOCKS":
            i += 1
            if i < len(lines):
                n_blocks = int(lines[i])
            i += 1
            continue

        if line.upper() in ("MASTERCONSS", "MASTERCONS"):
            i += 1
            while i < len(lines) and not _is_section_keyword(lines[i]):
                master_conss.append(lines[i])
                i += 1
            continue

        if line.upper() in ("MASTERVARS", "MASTERVAR", "LINKINGVARS", "LINKINGVAR"):
            i += 1
            while i < len(lines) and not _is_section_keyword(lines[i]):
                i += 1
            continue

        if line.upper() in ("BLOCKCONSS", "BLOCKCONS"):
            # Alternative format: BLOCKCONSS N on same line
            i += 1
            while i < len(lines) and not _is_section_keyword(lines[i]):
                i += 1
            continue

        # BLOCK N or BLOCK  N
        block_match = re.match(r"^BLOCK\s+(\d+)$", line, re.IGNORECASE)
        if block_match:
            block_id = int(block_match.group(1))
            block_conss.setdefault(block_id, [])
            i += 1
            while i < len(lines) and not _is_section_keyword(lines[i]):
                block_conss[block_id].append(lines[i])
                i += 1
            continue

        i += 1

    return {
        'n_blocks': n_blocks,
        'master_conss': master_conss,
        'block_conss': block_conss,
    }


# ---------------------------------------------------------------------------
# GNN decomposition → GCG .dec format
# ---------------------------------------------------------------------------

def gnn_to_dec(gnn_json_path: Path, mps_path: Path) -> str:
    """
    Convert GNN variable-level decomposition JSON to GCG constraint-level .dec format.

    Problem-agnostic: reads the GNN decomposition (variable → subproblem mapping),
    loads the MPS model via Gurobi, and infers constraint-to-block assignments:
      - If all variables of a constraint belong to the same subproblem →
        the constraint goes in that block.
      - If variables span multiple subproblems →
        the constraint goes in the master.
    """
    import json
    import gurobipy as gp

    with open(gnn_json_path) as f:
        data = json.load(f)

    subproblems = data.get("subproblems", {})
    master_vars = set(data.get("master_problem", []))

    # Build variable → subproblem_id mapping (as string keys for lookup)
    var_to_sub: dict[str, int] = {}
    for sub_id_str, var_names in subproblems.items():
        sid = int(sub_id_str)
        for name in var_names:
            var_to_sub[name] = sid

    # Load model to inspect constraint-variable relationships
    model = gp.read(str(mps_path))
    model.Params.OutputFlag = 0
    model.update()

    # For each constraint, determine which subproblem(s) it touches
    con_sub_map: dict[str, set[int]] = {}  # constraint name → set of subproblem ids
    for c in model.getConstrs():
        cname = c.ConstrName
        row = model.getRow(c)
        sub_ids: set[int] = set()
        for i in range(row.size()):
            vname = row.getVar(i).VarName
            if vname in var_to_sub:
                sub_ids.add(var_to_sub[vname])
        con_sub_map[cname] = sub_ids

    # Assign constraints to blocks or master
    block_conss: dict[int, list[str]] = {}
    master_conss: list[str] = []

    for cname, sub_ids in con_sub_map.items():
        if len(sub_ids) == 1:
            sid = next(iter(sub_ids))
            block_conss.setdefault(sid, []).append(cname)
        else:
            # No variables in decomposition, OR spans multiple subproblems → master
            master_conss.append(cname)

    # Also handle master variables: their incident constraints go to master
    # (already handled by the else branch above since master_vars aren't in var_to_sub)

    model.dispose()

    sorted_subs = sorted(block_conss.keys())
    n_blocks = len(sorted_subs)

    lines = [
        "\\ GNN-predicted decomposition",
        "\\ auto-generated from GNN variable clustering",
        "PRESOLVED",
        "0",
        "NBLOCKS",
        str(n_blocks),
    ]
    for sub_id in sorted_subs:
        lines.append(f"BLOCK {sub_id}")
        for cname in sorted(block_conss[sub_id]):
            lines.append(cname)

    if master_conss:
        lines.append("MASTERCONSS")
        for cname in sorted(master_conss):
            lines.append(cname)

    return "\n".join(lines) + "\n"


def _gnn_to_dec_gap(gnn_json_path: Path, n_agents: int, n_tasks: int) -> str:
    """GAP-specific .dec conversion (original logic, preserved for backward compat).

    Maps each GNN subproblem's variables to the agent capacity constraints
    (cap_i) that belong in the corresponding GCG block. Assignment constraints
    (assign_j) always go to the master.
    """
    import json

    with open(gnn_json_path) as f:
        data = json.load(f)

    subproblems = data.get("subproblems", {})

    agent_sub_counts = {}
    for sub_id_str, var_names in subproblems.items():
        sub_id = int(sub_id_str)
        for name in var_names:
            m = re.match(r"x_(\d+)_(\d+)", name)
            if m:
                i = int(m.group(1))
                agent_sub_counts.setdefault(i, {})
                agent_sub_counts[i][sub_id] = agent_sub_counts[i].get(sub_id, 0) + 1

    agent_sub = {}
    for i, counts in agent_sub_counts.items():
        agent_sub[i] = max(counts, key=counts.get)

    sub_agents = {}
    for i in range(n_agents):
        sid = agent_sub.get(i)
        if sid is None:
            sid = i + 1
        sub_agents.setdefault(sid, set()).add(i)

    sorted_subs = sorted(sub_agents.keys())

    lines = [
        "\\ GNN-predicted decomposition",
        "\\ auto-generated from GNN variable clustering",
        "PRESOLVED",
        "0",
        "NBLOCKS",
        str(len(sorted_subs)),
    ]
    for sub_id in sorted_subs:
        lines.append(f"BLOCK {sub_id}")
        for i in sorted(sub_agents[sub_id]):
            lines.append(f"cap_{i}")

    lines.append("MASTERCONSS")
    for j in range(n_tasks):
        lines.append(f"assign_{j}")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# GCG solve wrapper
# ---------------------------------------------------------------------------

def run_gcg_solve(mps_path: Path, dec_path: Path | None = None,
                   time_limit: int = 300, gcg_binary: str = "gcg") -> dict:
    """
    Run GCG to solve a problem, optionally with a pre-specified decomposition.

    Parameters
    ----------
    mps_path : Path
        Path to the MPS problem file.
    dec_path : Path or None
        Path to a .dec decomposition file. If None, GCG runs auto-detection.
    time_limit : int
        Time limit in seconds (passed via 'set limits time').
    gcg_binary : str
        Path to the GCG binary.

    Returns
    -------
    dict with keys: obj_val, dual_bound, gap, nodes, master_lp_iters,
    blocks, solutions_found, detect_time, total_time, status, raw_output
    """
    mps_path = Path(mps_path)

    commands = f"read {mps_path}\n"
    if dec_path is not None:
        commands += f"read decomp {Path(dec_path)}\n"
    else:
        commands += "detect\n"
    commands += f"set limits time {time_limit}\n"
    commands += "optimize\n"
    commands += "display statistics\n"
    commands += "quit\n"

    t0 = time.time()
    try:
        result = subprocess.run(
            [gcg_binary],
            input=commands,
            capture_output=True, text=True,
            timeout=time_limit + 60,
        )
    except subprocess.TimeoutExpired:
        return {
            'obj_val': None, 'dual_bound': None, 'gap': None,
            'nodes': None, 'master_lp_iters': None, 'blocks': None,
            'solutions_found': None, 'detect_time': None,
            'total_time': time_limit, 'status': 'TIMEOUT',
            'raw_output': '',
        }
    except FileNotFoundError:
        return {
            'obj_val': None, 'dual_bound': None, 'gap': None,
            'nodes': None, 'master_lp_iters': None, 'blocks': None,
            'solutions_found': None, 'detect_time': None,
            'total_time': 0, 'status': 'GCG_NOT_FOUND',
            'raw_output': '',
        }

    wall_time = time.time() - t0
    stdout = result.stdout

    def _parse_float(pattern, text, default=None):
        m = re.search(pattern, text)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                return default
        return default

    def _parse_int(pattern, text, default=None):
        m = re.search(pattern, text)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                return default
        return default

    obj_val = _parse_float(r'Primal Bound\s*:\s*([+\-]\S+)', stdout)
    dual_bound = _parse_float(r'Dual Bound\s*:\s*([+\-]\S+)', stdout)
    gap = _parse_float(r'Gap\s*:\s*(\S+)', stdout)
    nodes = _parse_int(r'nodes\s*:\s*(\d+)', stdout)
    master_lp_iters = _parse_int(r'Master LP\s*:\s*(\d+)', stdout)
    solutions_found = _parse_int(r'Solutions found\s*:\s*(\d+)', stdout)
    # "aggr. blocks" or "blocks" — pick the first match after "Decomp statistics"
    blocks_match = re.search(r'Decomp statistics.*?blocks\s*:\s*(\d+)',
                              stdout, re.DOTALL)
    blocks = int(blocks_match.group(1)) if blocks_match else None

    # Detect time: look for "Detector statistics" → total time
    detect_time = _parse_float(r'Total Time\s*:\s*(\S+)', stdout, 0.0)

    # Determine status
    if obj_val is not None and gap is not None and gap < 1e-4:
        status = "OPTIMAL"
    elif obj_val is not None:
        status = "TIME_LIMIT"
    else:
        status = "UNKNOWN"

    return {
        'obj_val': obj_val,
        'dual_bound': dual_bound,
        'gap': gap,
        'nodes': nodes,
        'master_lp_iters': master_lp_iters,
        'blocks': blocks,
        'solutions_found': solutions_found,
        'detect_time': detect_time,
        'total_time': wall_time,
        'status': status,
        'raw_output': stdout,
    }


# ---------------------------------------------------------------------------
# SCIP direct solve (no decomposition)
# ---------------------------------------------------------------------------

def run_scip_direct(mps_path: Path, time_limit: int = 300,
                     scip_binary: str = "scip") -> dict:
    """
    Solve original MIP with SCIP directly — no decomposition.

    Returns same dict format as run_gcg_solve() for fair comparison.
    """
    mps_path = Path(mps_path)
    commands = (
        f"read {mps_path}\n"
        f"set limits time {time_limit}\n"
        f"optimize\n"
        f"display statistics\n"
        f"quit\n"
    )

    t0 = time.time()
    try:
        result = subprocess.run(
            [scip_binary],  # no -q — need output for parsing
            input=commands,
            capture_output=True, text=True,
            timeout=time_limit + 60,
        )
    except subprocess.TimeoutExpired:
        return {
            'obj_val': None, 'dual_bound': None, 'gap': None,
            'nodes': None, 'master_lp_iters': None, 'blocks': None,
            'solutions_found': None, 'detect_time': None,
            'total_time': time_limit, 'status': 'TIMEOUT', 'raw_output': '',
        }
    except FileNotFoundError:
        return {
            'obj_val': None, 'dual_bound': None, 'gap': None,
            'nodes': None, 'master_lp_iters': None, 'blocks': None,
            'solutions_found': None, 'detect_time': None,
            'total_time': 0, 'status': 'SCIP_NOT_FOUND', 'raw_output': '',
        }

    wall_time = time.time() - t0
    stdout = result.stdout

    def _pf(pattern, text, default=None):
        m = re.search(pattern, text)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                return default
        return default

    def _pi(pattern, text, default=None):
        m = re.search(pattern, text)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                return default
        return default

    # SCIP output: "Primal Bound       : +3.934e+03 (28 solutions)"
    obj_val = _pf(r'Primal Bound\s*:\s*([+\-]\S+)', stdout)
    dual_bound = _pf(r'Dual Bound\s*:\s*([+\-]\S+)', stdout)
    # Gap line: "Gap                : 0.23 %" — return as percentage number
    gap = _pf(r'Gap\s*:\s*(\S+)\s*%', stdout)
    # "nodes (total)    :       3567 (3401 internal, ...)"
    nodes = _pi(r'nodes\s*\(total\)\s*:\s*(\d+)', stdout)
    if nodes is None:
        nodes = _pi(r'nodes\s*:\s*(\d+)', stdout)
    # "Solutions found  :         28 (8 improvements)"
    solutions_found = _pi(r'Solutions found\s*:\s*(\d+)', stdout)

    if obj_val is not None and gap is not None and gap < 1e-4:
        status = "OPTIMAL"
    elif obj_val is not None:
        status = "TIME_LIMIT"
    else:
        status = "UNKNOWN"

    return {
        'obj_val': obj_val,
        'dual_bound': dual_bound,
        'gap': gap,
        'nodes': nodes,
        'master_lp_iters': None,   # SCIP doesn't have DW master LP
        'blocks': None,             # no decomposition
        'solutions_found': solutions_found,
        'detect_time': 0.0,
        'total_time': wall_time,
        'status': status,
        'raw_output': stdout,
    }


def _is_section_keyword(line: str) -> bool:
    """Check if a line is a .dec section keyword."""
    kw = line.upper()
    return kw in (
        "PRESOLVED", "NBLOCKS",
        "MASTERCONSS", "MASTERCONS",
        "MASTERVARS", "MASTERVAR",
        "LINKINGVARS", "LINKINGVAR",
        "BLOCKCONSS", "BLOCKCONS",
        "CONSDEFAULTMASTER",
    ) or re.match(r"^BLOCK\s+\d+$", line, re.IGNORECASE) is not None
