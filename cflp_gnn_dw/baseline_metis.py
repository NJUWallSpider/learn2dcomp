import argparse
import gurobipy as gp
import networkx as nx
import json
import os
from pathlib import Path
import collections
import time
import sys
import numpy as np

# Dependencies
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

from tqdm import tqdm

def calculate_perfect_cluster_ratio(val_labels, pred_labels):
    """
    Calculates the ratio of true clusters that are perfectly recovered.
    (Copied from 04_test.py)
    """
    true_clusters = {}
    for idx, label in enumerate(val_labels):
        if label not in true_clusters:
            true_clusters[label] = set()
        true_clusters[label].add(idx)

    pred_clusters = {}
    for idx, label in enumerate(pred_labels):
        if label == -1: # Noise
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
        
        # Pick a representative to find the corresponding predicted cluster
        sample_idx = next(iter(t_indices))
        pred_label = pred_labels[sample_idx]
        
        if pred_label != -1:
            # Check if the predicted cluster is exactly the same set of indices
            p_indices = pred_clusters.get(pred_label)
            if p_indices == t_indices:
                perfect_matches += 1
                
    return perfect_matches / total_true

def build_vig(model):
    """
    Build Variable Intersection Graph (VIG) from Gurobi model.
    Nodes: Variables
    Edges: Two variables are connected if they appear in the same constraint.
    """
    G = nx.Graph()
    vars_list = model.getVars()
    var_names = [v.VarName for v in vars_list]
    name_to_idx = {name: i for i, name in enumerate(var_names)}
    
    # Add nodes
    G.add_nodes_from(range(len(vars_list)))
    
    # Add edges based on constraints
    constrs = model.getConstrs()
    # print(f"  Constructing VIG from {len(vars_list)} vars and {len(constrs)} constrs...")
    
    for constr in constrs:
        row = model.getRow(constr)
        row_var_indices = []
        for i in range(row.size()):
            v = row.getVar(i)
            row_var_indices.append(name_to_idx[v.VarName])
        
        count = len(row_var_indices)
        if count < 2:
            continue
            
        for i in range(count):
            u = row_var_indices[i]
            for j in range(i + 1, count):
                v = row_var_indices[j]
                if G.has_edge(u, v):
                    G[u][v]['weight'] += 1
                else:
                    G.add_edge(u, v, weight=1)
                    
    return G, var_names

def solve_metis(mps_file, k, output_dir, processed_dir=None):
    instance_name = mps_file.stem
    
    # Load Model
    env = gp.Env(empty=True)
    env.setParam("OutputFlag", 0)
    env.start()
    model = gp.read(str(mps_file), env=env)
    
    # Build VIG
    t0 = time.time()
    G, var_names = build_vig(model)
    build_time = time.time() - t0
    
    if pymetis is None:
        print("Error: 'pymetis' is not installed. Please install it via 'pip install pymetis'.")
        sys.exit(1)
        
    # Prepare for METIS
    adj_list = [[] for _ in range(G.number_of_nodes())]
    for u in G.nodes():
        adj_list[u] = sorted(list(G.neighbors(u)))
        
    t_part_start = time.time()
    # Run METIS
    n_cuts, membership = pymetis.part_graph(k, adjacency=adj_list)
    part_time = time.time() - t_part_start
    
    # Identify Master Variables (Greedy Vertex Cover on Cut Edges)
    # 1. Build Adjacency of Cut Edges
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
    
    # 2. Greedy Loop
    while num_cut_edges > 0:
        # Find node with max cut degree
        best_node = max(current_degrees, key=current_degrees.get)
        max_deg = current_degrees[best_node]
        
        if max_deg == 0:
            break
            
        master_vars_indices.add(best_node)
        
        # Remove
        neighbors = cut_adj[best_node]
        for v in neighbors:
            if best_node in cut_adj[v]:
                cut_adj[v].remove(best_node)
                current_degrees[v] -= 1
                num_cut_edges -= 1
        
        del current_degrees[best_node]
        del cut_adj[best_node]
            
    # Organize Output
    master_problem = []
    subproblems = collections.defaultdict(list)
    
    # Construct Prediction Labels for Metrics (Master=0, Subs=1..K)
    # Initialize with 1-based partitions (membership is 0..K-1)
    pred_labels = np.array(membership) + 1 
    
    for idx, name in enumerate(var_names):
        if idx in master_vars_indices:
            master_problem.append(name)
            pred_labels[idx] = 0 # Master Label
        else:
            part_id = membership[idx]
            subproblems[part_id].append(name)
            
    # Metrics Calculation
    metrics_res = {}
    if HAS_METRICS_DEPS and processed_dir:
        pt_file = processed_dir / f"{instance_name}.pt"
        if pt_file.exists():
            try:
                # Load Ground Truth
                # We need weights_only=False because PyG objects use custom pickling
                data = torch.load(pt_file, weights_only=False)
                true_labels = data['variable'].y.numpy() # Assuming y exists
                
                # Check alignment
                if len(true_labels) == len(pred_labels):
                    # Filter valid labels (ignore -1 in GT)
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
        else:
             # print(f"  Warning: .pt file not found for {instance_name}, skipping metrics.")
             pass

    # Save Output
    sorted_parts = sorted(subproblems.keys())
    final_subproblems = {}
    for new_id, old_id in enumerate(sorted_parts, start=1):
        final_subproblems[str(new_id)] = sorted(subproblems[old_id])
        
    output_data = {
        "instance_name": instance_name,
        "master_problem": sorted(list(master_problem)),
        "subproblems": final_subproblems,
        "stats": {
            "num_subproblems": len(final_subproblems),
            "num_master_vars": len(master_problem),
            "total_vars": len(var_names),
            "vig_build_time": build_time,
            "metis_time": part_time,
            "n_cuts": n_cuts
        },
        "metrics": metrics_res # Add metrics to JSON
    }
    
    out_file = output_dir / f"{instance_name}_decomposition.json"
    with open(out_file, 'w') as f:
        json.dump(output_data, f, indent=4)
        
    return metrics_res

def main():
    parser = argparse.ArgumentParser(description="Baseline: Decomposition via VIG + METIS + Greedy Vertex Cover.")
    parser.add_argument('--mps_dir', type=str, default="data/mps/facilities/test", help="Directory containing .mps files")
    parser.add_argument('--output_dir', type=str, default="results/decomposition_output_metis", help="Output directory for JSONs")
    parser.add_argument('--k', type=int, default=50, help="Number of partitions (K) for METIS.")
    parser.add_argument('--processed_dir', type=str, default="data/processed/facilities/test", help="Directory containing .pt files for Ground Truth metrics")
    
    args = parser.parse_args()
    
    mps_dir = Path(args.mps_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    processed_dir = Path(args.processed_dir) if args.processed_dir else None
    
    print(f"Running METIS Baseline on {mps_dir}")
    print(f"Target K={args.k}")
    if processed_dir:
        print(f"Comparing against Ground Truth in {processed_dir}")
    
    mps_files = sorted(list(mps_dir.glob("*.mps")))
    
    if not mps_files:
        print(f"No .mps files found in {mps_dir}")
        return
        
    all_metrics = collections.defaultdict(list)
    
    for f in tqdm(mps_files, desc="Processing Instances"):
        res = solve_metis(f, args.k, output_dir, processed_dir)
        if res:
            for k, v in res.items():
                all_metrics[k].append(v)
                
    # Print Summary
    print("\n--- Baseline Clustering Metrics (vs Ground Truth) ---")
    if all_metrics:
        count = len(all_metrics['ari'])
        print(f"Evaluated {count} instances.")
        print(f"  Avg ARI: {np.mean(all_metrics['ari']):.4f}")
        print(f"  Avg NMI: {np.mean(all_metrics['nmi']):.4f}")
        print(f"  Avg V-Measure: {np.mean(all_metrics['v_measure']):.4f}")
        print(f"  Avg Perfect Cluster Ratio: {np.mean(all_metrics['pcr']):.4f}")
    else:
        print("No metrics computed (Ground Truth missing or errors).")

if __name__ == "__main__":
    main()