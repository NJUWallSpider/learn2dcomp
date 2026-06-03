"""
RMF (Multi-commodity Flow) instance generator.

Parses GAMS .gms data files and builds node-arc MCF linear programs,
writing them as .lp files for the pipeline.

The GMS files define:
  - Bandwidth parameters d(i,j) forming an undirected graph with edge capacities
  - Traffic demands tr(k,v) defining commodities (origin, destination, volume)

LP formulation:
  Variables: f_{i}_{j}_{k} >= 0  — flow of commodity k on directed arc (i,j)
  Flow balance: outflow - inflow = demand(source), -demand(sink), 0(transit)
  Capacity: sum_k (f_{i}_{j}_{k} + f_{j}_{i}_{k}) <= bandwidth_{i,j}
  Objective: minimize total flow
"""

import re
from pathlib import Path

import gurobipy as gp
from gurobipy import GRB


def parse_gms(filepath: Path) -> tuple:
    """Parse a GAMS .gms data file.

    Returns (edges, commodities) where:
      edges: dict (i, j) -> capacity (undirected, i < j)
      commodities: list of (source, sink, demand)
    """
    content = filepath.read_text()

    edges = {}
    for m in re.finditer(r"d\('(\d+)','(\d+)'\)\s*=\s*([\d.eE+\-]+);", content):
        i, j, val = int(m.group(1)), int(m.group(2)), float(m.group(3))
        if i < j:
            edges[(i, j)] = val

    commodities = []
    for m in re.finditer(r"tr\('(\d+)','(\d+)'\)\s*=\s*([\d.eE+\-]+);", content):
        s, t, val = int(m.group(1)), int(m.group(2)), float(m.group(3))
        if val > 0:
            commodities.append((s, t, val))

    return edges, commodities


def build_mcf_model(edges: dict, commodities: list, name: str = "rmf") -> gp.Model:
    """Build a node-arc multi-commodity flow LP.

    Undirected capacity: sum_k (f_{i,j,k} + f_{j,i,k}) <= u_{ij}
    Objective: minimize sum of all flows.
    """
    model = gp.Model(name)

    nodes = set()
    for i, j in edges:
        nodes.add(i)
        nodes.add(j)

    adj = {v: set() for v in nodes}
    for i, j in edges:
        adj[i].add(j)
        adj[j].add(i)

    K = len(commodities)

    flow = {}
    for k_idx in range(K):
        for i in nodes:
            for j in adj[i]:
                flow[(i, j, k_idx)] = model.addVar(
                    lb=0.0, name=f"f_{i}_{j}_{k_idx}"
                )

    model.update()

    for k_idx, (s, t, d) in enumerate(commodities):
        for v in nodes:
            outflow = gp.quicksum(flow[(v, j, k_idx)] for j in adj[v])
            inflow = gp.quicksum(flow[(i, v, k_idx)] for i in adj[v])
            rhs = d if v == s else (-d if v == t else 0.0)
            model.addConstr(outflow - inflow == rhs, name=f"bal_{v}_{k_idx}")

    for (i, j), u in edges.items():
        cap = gp.quicksum(
            flow[(i, j, k)] + flow[(j, i, k)] for k in range(K)
        )
        model.addConstr(cap <= u, name=f"cap_{i}_{j}")

    model.setObjective(gp.quicksum(flow.values()), GRB.MINIMIZE)
    model.update()
    return model


def generate_rmf_instances(grid_dir: Path, out_dir: Path, file_list: list[str]):
    """Generate LP files for the given RMF GMS files.

    Args:
        grid_dir: directory containing .gms files
        out_dir: output directory for .lp files
        file_list: list of .gms filenames to process
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    for fname in file_list:
        gms_path = grid_dir / fname
        if not gms_path.exists():
            print(f"  WARNING: {fname} not found in {grid_dir}, skipping")
            continue

        lp_name = gms_path.stem
        lp_path = out_dir / f"{lp_name}.lp"
        if lp_path.exists():
            print(f"  [{out_dir.parent.name}/{out_dir.name}] {lp_name} — LP exists, skip")
            continue

        edges, commodities = parse_gms(gms_path)
        print(f"  building {lp_name} ({len(edges)} edges, "
              f"{len(commodities)} commodities)...", end=" ", flush=True)

        model = build_mcf_model(edges, commodities, name=lp_name)
        model.write(str(lp_path))
        n_vars = model.NumVars
        n_constrs = model.NumConstrs
        model.dispose()
        print(f"done ({n_vars} vars, {n_constrs} constrs)")
