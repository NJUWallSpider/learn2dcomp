"""
Baseline: METIS partitioning on Variable Intersection Graph (VIG) for GAP.

Builds VIG directly from .pt graph data (no solver needed), partitions with
METIS, identifies master variables via greedy vertex cover on cut edges, and
outputs decomposition + job->machine assignment.

Usage:
    python baseline_metis.py --pt_dir data/processed/gap/test
                             --output_dir results/metis_output
                             --k 5
"""
import argparse
import json
import os
import collections
import time
import sys
import numpy as np
import networkx as nx
from pathlib import Path
from tqdm import tqdm

try:
    import pymetis
except ImportError:
    pymetis = None

try:
    import torch
    from sklearn.metrics import adjusted_rand_score, v_measure_score, normalized_mutual_info_score
    HAS_METRICS_DEPS = True
except ImportError:
    HAS_METRICS_DEPS = False


def calculate_perfect_cluster_ratio(val_labels, pred_labels):
    true_clusters = {}
    for idx, label in enumerate(val_labels):
        if label not in true_clusters:
            true_clusters[label] = set()
        true_clusters[label].add(idx)

    pred_clusters = {}
    for idx, label in enumerate(pred_labels):
        if label == -1:
            continue
        if label not in pred_clusters:
            pred_clusters[label] = set()
        pred_clusters[label].add(idx)

    perfect_matches = 0
    total_true = len(true_clusters)
    if total_true == 0:
        return 0.0

    for t_label, t_indices in true_clusters.items():
        if not t_indices:
            continue
        sample_idx = next(iter(t_indices))
        pred_label = pred_labels[sample_idx]
        if pred_label != -1:
            p_indices = pred_clusters.get(pred_label)
            if p_indices == t_indices:
                perfect_matches += 1
    return perfect_matches / total_true


def build_vig_from_pt(pt_file):
    """
    Build Variable Intersection Graph from GAP .pt file.

    For GAP, the VIG has two clique types:
      - For each job i: variables x_{i,*} form a clique (assignment constraint)
      - For each machine j: variables x_{*,j} form a clique (capacity constraint)

    We infer n_jobs, n_machines from the .pt file's constraint names.
    """
    data = torch.load(str(pt_file), weights_only=False)
    var_names = data.var_names if hasattr(data, 'var_names') else None
    con_names = data.con_names if hasattr(data, 'con_names') else None

    n_vars = data['variable'].num_nodes

    # Infer dimensions from constraint names
    n_jobs = sum(1 for c in con_names if c.startswith('assign_'))
    n_machines = sum(1 for c in con_names if c.startswith('cap_'))

    if n_jobs * n_machines != n_vars:
        # Fallback: extract from variable names
        if var_names:
            max_i = max_j = 0
            for name in var_names:
                parts = name.split('_')
                if len(parts) >= 3 and parts[0] == 'x':
                    max_i = max(max_i, int(parts[1]))
                    max_j = max(max_j, int(parts[2]))
            n_jobs = max_i + 1
            n_machines = max_j + 1

    # Only generate var_names if not present
    if var_names is None or len(var_names) != n_vars:
        var_names = [f"x_{i}_{j}" for i in range(n_jobs) for j in range(n_machines)]

    G = nx.Graph()
    G.add_nodes_from(range(n_vars))

    # Build cliques efficiently
    # Assignment cliques: for each job i, edges between all x_{i,j} pairs
    for i in range(n_jobs):
        indices = [i * n_machines + j for j in range(n_machines)]
        for a in range(len(indices)):
            for b in range(a + 1, len(indices)):
                u, v = indices[a], indices[b]
                if G.has_edge(u, v):
                    G[u][v]['weight'] += 1
                else:
                    G.add_edge(u, v, weight=1)

    # Capacity cliques: for each machine j, edges between all x_{i,j} pairs
    for j in range(n_machines):
        indices = [i * n_machines + j for i in range(n_jobs)]
        for a in range(len(indices)):
            for b in range(a + 1, len(indices)):
                u, v = indices[a], indices[b]
                if G.has_edge(u, v):
                    G[u][v]['weight'] += 1
                else:
                    G.add_edge(u, v, weight=1)

    return G, var_names, n_jobs, n_machines


def derive_assignment_from_membership(membership, master_indices, var_names, n_jobs, n_machines):
    """
    Derive job->machine assignment from METIS partition membership.

    Each partition roughly corresponds to a machine block.
    Map partition -> dominant machine, then produce assignment.
    """
    # Parse variable names
    var_info = []
    for name in var_names:
        parts = name.split('_')
        if len(parts) >= 3 and parts[0] == 'x':
            var_info.append((int(parts[1]), int(parts[2])))
        else:
            var_info.append(None)

    # Map partition -> dominant machine
    part_machine_votes = collections.defaultdict(lambda: collections.Counter())
    for idx, part in enumerate(membership):
        if idx not in master_indices and var_info[idx] is not None:
            _i, j = var_info[idx]
            part_machine_votes[part][j] += 1

    part_to_machine = {}
    for part, votes in part_machine_votes.items():
        if votes:
            part_to_machine[part] = votes.most_common(1)[0][0]

    # Build assignment
    assignment = {}
    for i in range(n_jobs):
        candidates = {}
        for j in range(n_machines):
            idx = i * n_machines + j
            if idx in master_indices:
                continue
            part = membership[idx]
            if part in part_to_machine and part_to_machine[part] == j:
                candidates[j] = 0  # could use tie-breaking

        if len(candidates) == 1:
            assignment[i] = list(candidates.keys())[0]
        elif len(candidates) > 1:
            # Pick machine with min cost (not available here, pick first)
            assignment[i] = list(candidates.keys())[0]

    return assignment


def solve_metis(pt_file, k, output_dir):
    instance_name = pt_file.stem

    t0 = time.time()
    G, var_names, n_jobs, n_machines = build_vig_from_pt(pt_file)
    build_time = time.time() - t0

    if pymetis is None:
        print("Error: 'pymetis' is not installed.")
        sys.exit(1)

    # Build adjacency for METIS
    n_vars = G.number_of_nodes()
    adj_list = [[] for _ in range(n_vars)]
    for u in G.nodes():
        adj_list[u] = sorted(list(G.neighbors(u)))

    t_part_start = time.time()
    n_cuts, membership = pymetis.part_graph(k, adjacency=adj_list)
    part_time = time.time() - t_part_start

    # Identify Master Variables (Greedy Vertex Cover on Cut Edges)
    cut_adj = collections.defaultdict(set)
    num_cut_edges = 0

    for u in G.nodes():
        u_part = membership[u]
        for v in G.neighbors(u):
            if membership[v] != u_part:
                cut_adj[u].add(v)
                num_cut_edges += 1
    num_cut_edges //= 2

    master_vars_indices = set()
    current_degrees = {node: len(neighbors) for node, neighbors in cut_adj.items()}

    while num_cut_edges > 0:
        if not current_degrees:
            break
        best_node = max(current_degrees, key=current_degrees.get)
        max_deg = current_degrees[best_node]
        if max_deg == 0:
            break

        master_vars_indices.add(best_node)

        neighbors = cut_adj[best_node]
        for v in neighbors:
            if best_node in cut_adj[v]:
                cut_adj[v].remove(best_node)
                current_degrees[v] -= 1
                num_cut_edges -= 1

        del current_degrees[best_node]
        del cut_adj[best_node]

    # Organize output
    master_problem = []
    subproblems = collections.defaultdict(list)

    pred_labels = np.array(membership) + 1  # 1-based partitions
    n_vars_total = len(var_names)

    for idx in range(n_vars_total):
        name = var_names[idx] if idx < len(var_names) else f"x_{idx}"
        if idx in master_vars_indices:
            master_problem.append(name)
            pred_labels[idx] = 0  # Master label
        else:
            part_id = membership[idx]
            subproblems[part_id].append(name)

    # Derive job->machine assignment
    assignment = derive_assignment_from_membership(
        membership, master_vars_indices, var_names, n_jobs, n_machines
    )

    # Metrics vs ground truth from .pt file
    metrics_res = {}
    if HAS_METRICS_DEPS:
        try:
            data = torch.load(str(pt_file), weights_only=False)
            true_labels = data['variable'].y.numpy()
            if len(true_labels) == len(pred_labels):
                mask = true_labels >= 0
                if mask.sum() > 0:
                    val_true = true_labels[mask]
                    val_pred = pred_labels[mask]
                    metrics_res['ari'] = adjusted_rand_score(val_true, val_pred)
                    metrics_res['nmi'] = normalized_mutual_info_score(val_true, val_pred)
                    metrics_res['v_measure'] = v_measure_score(val_true, val_pred)
                    metrics_res['pcr'] = calculate_perfect_cluster_ratio(val_true, val_pred)
                    metrics_res['true_n_clusters'] = len(np.unique(val_true))
        except Exception as e:
            print(f"  Warning: Failed to compute metrics for {instance_name}: {e}")

    # Save output
    sorted_parts = sorted(subproblems.keys())
    final_subproblems = {}
    for new_id, old_id in enumerate(sorted_parts, start=1):
        final_subproblems[str(new_id)] = sorted(subproblems[old_id])

    output_data = {
        "instance_name": instance_name,
        "assignment": {str(k): v for k, v in assignment.items()},
        "master_problem": sorted(master_problem),
        "subproblems": final_subproblems,
        "stats": {
            "num_subproblems": len(final_subproblems),
            "num_master_vars": len(master_problem),
            "total_vars": n_vars_total,
            "vig_build_time": build_time,
            "metis_time": part_time,
            "n_cuts": n_cuts,
        },
        "metrics": metrics_res,
    }

    out_file = output_dir / f"{instance_name}_decomposition.json"
    with open(out_file, 'w') as f:
        json.dump(output_data, f, indent=4)

    return metrics_res


def main():
    parser = argparse.ArgumentParser(
        description="Baseline: GAP VIG + METIS decomposition"
    )
    parser.add_argument('--pt_dir', type=str, default="data/processed/gap/test",
                        help="Directory containing .pt files")
    parser.add_argument('--output_dir', type=str,
                        default="results/metis_output",
                        help="Output directory for decomposition JSONs")
    parser.add_argument('--k', type=int, default=5,
                        help="Number of METIS partitions")

    args = parser.parse_args()

    pt_dir = Path(args.pt_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Running METIS Baseline on {pt_dir}")
    print(f"Target K={args.k}")

    pt_files = sorted(list(pt_dir.glob("*.pt")))

    if not pt_files:
        # Try default GAP test path
        default_pt = Path("data/processed/gap/test")
        if default_pt.exists():
            pt_files = sorted(list(default_pt.glob("*.pt")))
            pt_dir = default_pt

    if not pt_files:
        print(f"No .pt files found in {pt_dir}")
        return

    all_metrics = collections.defaultdict(list)

    for f in tqdm(pt_files, desc="Processing Instances"):
        res = solve_metis(f, args.k, output_dir)
        if res:
            for k, v in res.items():
                all_metrics[k].append(v)

    # Summary
    print("\n--- METIS Baseline Clustering Metrics (vs Ground Truth) ---")
    if all_metrics:
        count = len(all_metrics['ari'])
        print(f"Evaluated {count} instances.")
        print(f"  Avg ARI: {np.mean(all_metrics['ari']):.4f}")
        print(f"  Avg NMI: {np.mean(all_metrics['nmi']):.4f}")
        print(f"  Avg V-Measure: {np.mean(all_metrics['v_measure']):.4f}")
        print(f"  Avg Perfect Cluster Ratio: {np.mean(all_metrics['pcr']):.4f}")
    else:
        print("No metrics computed (ground truth missing or errors).")


if __name__ == "__main__":
    main()
