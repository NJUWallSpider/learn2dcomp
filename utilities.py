# 在多个文件中调用的函数
import datetime
import numpy as np
import scipy.sparse as sp
import pyscipopt as scip
import argparse
from sklearn.neighbors import NearestNeighbors
from sklearn.cluster import DBSCAN
import gurobipy as gp
from gurobipy import GRB


def valid_seed(seed):
    """Check whether seed is a valid random seed or not."""
    seed = int(seed)
    if seed < 0 or seed > 2**32 - 1:
        raise argparse.ArgumentTypeError(
                "seed must be any integer between 0 and 2**32 - 1 inclusive")
    return seed

def log(str, logfile=None):
    str = f'[{datetime.datetime.now()}] {str}'
    print(str)
    if logfile is not None:
        with open(logfile, mode='a') as f:
            print(str, file=f)

def hierarchical_dbscan(embeddings, min_samples, start_scale=0.2, step_scale=0.2, max_scale=4.0):
    """
    Performs hierarchical DBSCAN by running it iteratively with increasing eps until no noise points are left.
    It starts with a scale factor `start_scale` and increases it by `step_scale` in each iteration.
    Points clustered in one round are excluded from subsequent rounds. The process stops when all points
    are clustered or `max_scale` is reached.
    """
    base_eps = find_dbscan_eps(embeddings, min_samples, scaling_factor=1.0) # Get the raw knee point
    if base_eps == 0:
        base_eps = 0.1
 
    remaining_indices = np.arange(len(embeddings))
    final_labels = np.full(len(embeddings), -1, dtype=int)
    cluster_offset = 0
    eps_values = []
 
    scale_factor = start_scale
    while len(remaining_indices) > 0 and scale_factor <= max_scale:
        eps = base_eps * scale_factor
        eps_values.append(eps)
 
        if len(remaining_indices) < min_samples:
            break
 
        current_embeddings = embeddings[remaining_indices]
        dbscan = DBSCAN(eps=eps, min_samples=min_samples)
        predicted_labels = dbscan.fit_predict(current_embeddings)
 
        clustered_mask = predicted_labels != -1
        if np.any(clustered_mask):
            newly_clustered_original_indices = remaining_indices[clustered_mask]
            new_labels = predicted_labels[clustered_mask] + cluster_offset
            final_labels[newly_clustered_original_indices] = new_labels
 
            cluster_offset = new_labels.max() + 1
            remaining_indices = remaining_indices[~clustered_mask]
 
        scale_factor += step_scale
 
    return final_labels, eps_values

def find_dbscan_eps(embeddings, min_samples, scaling_factor = 1.0):
    """
    使用k-distance图的方法自动为DBSCAN寻找一个合适的eps值。
    它寻找距离图中斜率变化最剧烈的“拐点”。
    """
    # 1. 计算每个点到其k-th最近邻的距离 (k = min_samples - 1)
    k = min_samples - 1
    if k <= 0: # Handle case where min_samples is 1 or less, though for DBSCAN min_samples >= 2 is typical
        return 0.1 * scaling_factor # A small default eps if k is not meaningful for distance calculation

    neighbors = NearestNeighbors(n_neighbors=k + 1)
    neighbors_fit = neighbors.fit(embeddings)
    distances, _ = neighbors_fit.kneighbors(embeddings)
    
    # 获取到第k个邻居的距离并排序
    k_distances = np.sort(distances[:, k], axis=0)
    
    # 2. 找到“拐点”
    # "拐点"是曲线上离连接首末两点的直线最远的点。
    n_points = len(k_distances)
    all_coords = np.vstack((range(n_points), k_distances)).T
    
    first_point = all_coords[0]
    last_point = all_coords[-1]
    line_vec = last_point - first_point
    line_vec_norm = line_vec / np.sqrt(np.sum(line_vec**2))
    vec_from_first = all_coords - first_point
    scalar_product = np.sum(vec_from_first * np.tile(line_vec_norm, (n_points, 1)), axis=1)
    vec_from_first_parallel = np.outer(scalar_product, line_vec_norm)
    vec_to_line = vec_from_first - vec_from_first_parallel
    dist_to_line = np.sqrt(np.sum(vec_to_line ** 2, axis=1))
    
    # 找到最大距离对应的点，其y坐标（即k-distance）就是最佳eps
    best_eps_index = np.argmax(dist_to_line)
    best_eps = k_distances[best_eps_index]
    
    # 启发式方法找到的eps有时会偏大，导致簇被合并。
    # 乘以一个小于1的因子可以收紧邻域，帮助分离靠得近的簇。
    # 0.75是一个经验值，可以根据实验效果调整。
    return best_eps * scaling_factor

def reassign_noise_points(embeddings, pred_labels):
    """
    Reassigns noise points (label -1) to the nearest cluster centroid.
    """
    # Ensure numpy array
    pred_labels = np.array(pred_labels)
    
    unique_labels = np.unique(pred_labels)
    valid_labels = unique_labels[unique_labels != -1]
    
    if len(valid_labels) == 0:
        return pred_labels
        
    noise_mask = (pred_labels == -1)
    if not np.any(noise_mask):
        return pred_labels
        
    # Calculate centroids
    centroids = []
    label_map = [] # To map index back to label
    
    for label in valid_labels:
        cluster_mask = (pred_labels == label)
        cluster_points = embeddings[cluster_mask]
        centroid = np.mean(cluster_points, axis=0)
        centroids.append(centroid)
        label_map.append(label)
        
    centroids = np.array(centroids)
    label_map = np.array(label_map)
    
    # Assign noise points
    noise_points = embeddings[noise_mask]
    
    # Compute distances: [num_noise, num_clusters]
    # Expand dims for broadcasting or use cdist
    from scipy.spatial.distance import cdist
    dists = cdist(noise_points, centroids, metric='euclidean')
    
    nearest_cluster_indices = np.argmin(dists, axis=1)
    new_labels = label_map[nearest_cluster_indices]
    
    # Update labels
    pred_labels[noise_mask] = new_labels
    
    return pred_labels

def graph_voting_reassignment(pred_labels, edge_index, num_vars, num_conss, embeddings=None, threshold=0.5, var_names=None, con_names=None):
    """
    Reassigns noise points (-1) using "Local-Priority Propagation".
    
    Step 1: Constraint Typing
    - Unique neighbor label k -> LOCAL_k (k)
    - Multiple neighbor labels -> LINKING (-2)
    - Empty neighbors -> UNDETERMINED (-3)
    
    Step 2: Variable Assignment (Priority Rules)
    - Rule 1 (Local Priority): If connected to any LOCAL_k constraint -> Assign to Cluster k.
      (If connected to multiple DISTINCT Local constraints -> Master/Bridge).
    - Rule 2 (Master Default): If NOT connected to any LOCAL constraint -> Assign to Master.
    """
    import torch
    from collections import defaultdict
    import os
    
    # Constants
    LINKING = -2
    UNDETERMINED = -3
    
    pred_labels = np.array(pred_labels)
    noise_mask = (pred_labels == -1)
    
    if not np.any(noise_mask):
        return pred_labels

    # Determine Logging
    enable_logging = (var_names is not None)
    log_file = None
    if enable_logging:
        log_file = open("graph_voting_debug.txt", "w")
        log_file.write(f"\n--- Local-Priority Propagation Start ---\n")
        log_file.write(f"Total Vars: {num_vars}, Total Cons: {num_conss}, Noise Vars: {np.sum(noise_mask)}\n")

    # Determine Master Label
    valid_labels = pred_labels[pred_labels >= 0]
    if len(valid_labels) > 0:
        master_label = np.max(valid_labels) + 1 
    else:
        master_label = 0
    
    if enable_logging:
        log_file.write(f"Master Label determined as: {master_label}\n")

    # Prepare Graph
    if torch.is_tensor(edge_index):
        edge_index = edge_index.cpu().numpy()
    row, col = edge_index # row=vars, col=conss

    # --- Step 1: Constraint Typing ---
    if enable_logging:
        log_file.write("--- Step 1: Constraint Typing ---\n")
        
    con_neighbors = defaultdict(set)
    for v, c in zip(row, col):
        if pred_labels[v] != -1: # Only non-noise variables determine type
            con_neighbors[c].add(pred_labels[v])
            
    con_tags = {}
    stats_con = {"UNDETERMINED": 0, "LOCAL": 0, "LINKING": 0}
    
    for c in range(num_conss):
        S = con_neighbors.get(c, set())
        
        c_name = str(c)
        if con_names and c < len(con_names):
            c_name = con_names[c]
            
        if len(S) == 0:
            con_tags[c] = UNDETERMINED
            stats_con["UNDETERMINED"] += 1
            # if enable_logging: log_file.write(f"Con {c_name}: Neighbors={{}} -> UNDETERMINED\n")
        elif len(S) == 1:
            tag = list(S)[0]
            con_tags[c] = tag # LOCAL_k
            stats_con["LOCAL"] += 1
            # if enable_logging: log_file.write(f"Con {c_name}: Neighbors={S} -> LOCAL_{tag}\n")
        else:
            con_tags[c] = LINKING
            stats_con["LINKING"] += 1
            if enable_logging:
                log_file.write(f"Con {c_name}: Neighbors={S} -> LINKING\n")
            
    if enable_logging:
        log_file.write(f"Constraint Stats: {stats_con}\n")
    
    # --- Step 2: Variable Assignment ---
    if enable_logging:
        log_file.write("--- Step 2: Variable Assignment ---\n")
        
    stats_var = {"Merged (Local)": 0, "Master (No Local)": 0, "Master (Conflicting Locals)": 0, "Unchanged": 0}
    
    # Group constraints by variable
    var_to_cons = defaultdict(list)
    for v, c in zip(row, col):
        if pred_labels[v] == -1: # Only care about noise vars
            var_to_cons[v].append(c)
            
    for v, cons in var_to_cons.items():
        local_clusters = set()
        has_linking = False
        has_undetermined = False
        
        v_name = str(v)
        if var_names and v < len(var_names):
            v_name = var_names[v]
        
        cons_details = []
        
        for c in cons:
            tag = con_tags.get(c, UNDETERMINED) 
            
            c_name = str(c)
            if con_names and c < len(con_names):
                c_name = con_names[c]
            
            tag_str = "UNDET" if tag == UNDETERMINED else ("LINK" if tag == LINKING else f"LOCAL_{tag}")
            cons_details.append(f"{c_name}({tag_str})")
            
            if tag == LINKING:
                has_linking = True
            elif tag == UNDETERMINED:
                has_undetermined = True
            else:
                # LOCAL tag (>= 0)
                local_clusters.add(tag)
        
        decision = "Unchanged"
        
        # Priority Logic
        if len(local_clusters) > 0:
            # Rule 1: Local Priority
            if len(local_clusters) == 1:
                # Unique Local Cluster -> Merge
                k = list(local_clusters)[0]
                pred_labels[v] = k
                stats_var["Merged (Local)"] += 1
                decision = f"Merged to Cluster {k} (Local Priority)"
            else:
                # Conflicting Locals -> Master/Bridge
                pred_labels[v] = master_label
                stats_var["Master (Conflicting Locals)"] += 1
                decision = f"Master (Conflicting Locals: {local_clusters})"
        else:
            # Rule 2: Master Default (Only Linking or Undetermined)
            if has_linking or has_undetermined:
                pred_labels[v] = master_label
                stats_var["Master (No Local)"] += 1
                decision = f"Master (No Local Constraints)"
            else:
                # Isolated completely? (Empty cons list?)
                stats_var["Unchanged"] += 1
                decision = "Unchanged"
            
        if enable_logging:
            log_file.write(f"Var {v_name}: Cons=[{', '.join(cons_details)}] -> {decision}\n")
            
    if enable_logging:
        log_file.write(f"Variable Stats: {stats_var}\n")
        log_file.close()
    
    return pred_labels
