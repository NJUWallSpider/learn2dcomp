import torch
from torch_geometric.loader import DataLoader
import numpy as np
from sklearn.metrics import adjusted_rand_score, v_measure_score, normalized_mutual_info_score
from sklearn.cluster import DBSCAN
import config
from data_process import MILPDataset, add_laplacian_pe
from gnn_model import GraphTransformer
import utilities
from tqdm import tqdm
import sys
import json
from pathlib import Path
import collections
import os

def calculate_perfect_cluster_ratio(val_labels, pred_labels):
    """
    Calculates the ratio of true clusters that are perfectly recovered.
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

def test():
    # 1. Setup Device
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Using device: {device}")

    # 2. Load Model
    model_path = config.MODELS_DIR / "best_model.pth"
    if not model_path.exists():
        print(f"Error: Model file not found at {model_path}")
        print("Please run 03_train_gnn.py first.")
        return

    print(f"Loading model from {model_path}...")
    try:
        mp = config.MODEL_PARAMS
        model = GraphTransformer(
            hidden_dim=mp['emb_size'],
            num_layers=mp.get('num_layers', 2),
            num_heads=mp.get('num_heads', 4),
            pe_dim=mp.get('pe_dim', 8),
            max_con_blocks=mp.get('max_con_blocks', 128),
        ).to(device)
        model.load_state_dict(torch.load(model_path, map_location=device))
        model.eval()
    except Exception as e:
        print(f"Failed to load model: {e}")
        return

    # 3. Test Loop over configured folders
    problem = config.TRAIN_PARAMS['problem']

    for folder in config.TEST_FOLDERS:
        test_dir = config.PROCESSED_DATA_DIR / problem / folder
        if not test_dir.exists():
            print(f"Test directory not found: {test_dir}")
            continue

        print(f"\nEvaluating on dataset: {folder}")

        test_files = sorted([str(f) for f in test_dir.glob("*.pt")])
        if not test_files:
            print(f"No .pt files found in {test_dir}")
            continue

        test_dataset = MILPDataset(test_files, transform=add_laplacian_pe)

        test_loader = DataLoader(
            test_dataset,
            batch_size=config.EVAL_PARAMS.get('test_batch_size', 1),
            shuffle=False,
            num_workers=config.TRAIN_PARAMS['num_workers']
        )

        # Metrics Storage
        metrics = {
            'per_instance_true_n_clusters': [],
            'perfect_cluster_ratio': [],
            'dbscan_v_measure': [],
            'dbscan_ari': [],
            'dbscan_nmi': [],
            'num_instances_evaluated_dbscan': 0,
            'con_linking_acc': [],
            'con_block_acc': [],
        }

        perfect_instances = []
        # Output Directory for Clusters
        cluster_output_dir = config.MODELS_DIR / "cluster_outputs" / folder
        os.makedirs(cluster_output_dir, exist_ok=True)

        print(f"Processing {len(test_dataset)} instances...")

        with torch.no_grad():
            for i, data in enumerate(tqdm(test_loader)):
                # Retrieve variable names BEFORE moving to device
                var_names = []
                if hasattr(data, 'var_names'):
                    var_names = data.var_names
                    if isinstance(var_names, list) and len(var_names) > 0 and isinstance(var_names[0], list):
                        var_names = [item for sublist in var_names for item in sublist]

                # Retrieve constraint names
                con_names = []
                if hasattr(data, 'con_names'):
                    con_names = data.con_names
                    if isinstance(con_names, list) and len(con_names) > 0 and isinstance(con_names[0], list):
                        con_names = [item for sublist in con_names for item in sublist]

                # Retrieve instance name
                pt_path = Path(test_dataset.sample_files[i])
                instance_stem = pt_path.stem

                data = data.to(device)

                # Forward pass
                try:
                    var_emb, con_block_logits, con_linking_logits = model(data)
                except Exception as e:
                    print(f"Error during forward pass on instance {i}: {e}")
                    continue

                embeddings = var_emb.cpu().numpy()
                labels = data['variable'].y.cpu().numpy()

                # Evaluate constraint predictions if ground truth exists
                if hasattr(data['constraint'], 'y') and data['constraint'].y is not None:
                    con_true = data['constraint'].y.cpu().numpy()

                    # Linking accuracy
                    linking_mask = (con_true >= 0) | (con_true == -2)
                    if linking_mask.sum() > 0:
                        linking_pred = (torch.sigmoid(con_linking_logits).cpu().numpy() > 0.5).flatten()
                        linking_true = (con_true == -2).astype(float)
                        acc = (linking_pred[linking_mask] == linking_true[linking_mask]).mean()
                        metrics['con_linking_acc'].append(float(acc))

                    # Block accuracy (on LOCAL/block constraints: label >= 1)
                    local_mask = con_true >= 1
                    if local_mask.sum() > 0:
                        block_pred = con_block_logits.argmax(dim=1).cpu().numpy()
                        block_true = con_true[local_mask]
                        block_true = np.clip(block_true, 0, con_block_logits.shape[1] - 1)
                        acc = (block_pred[local_mask] == block_true).mean()
                        metrics['con_block_acc'].append(float(acc))

                # Filter valid labels
                mask = labels >= 0
                if mask.sum() == 0:
                    continue

                val_embeddings = embeddings[mask]
                val_labels = labels[mask]

                # Filter variable names
                valid_var_names = []
                if var_names:
                    if len(var_names) != len(labels):
                         print(f"Warning: Mismatch in var count for {instance_stem}. Names: {len(var_names)}, Labels: {len(labels)}")
                         valid_var_names = [f"var_{idx}" for idx in np.where(mask)[0]]
                    else:
                         valid_var_names = np.array(var_names)[mask].tolist()
                else:
                    valid_var_names = [f"var_{idx}" for idx in np.where(mask)[0]]

                # Record True Clusters Count
                metrics['per_instance_true_n_clusters'].append(len(np.unique(val_labels)))

                # Clustering
                min_samples = config.EVAL_PARAMS.get('dbscan_min_samples', 2)

                try:
                    # Simple DBSCAN with knee-point eps
                    eps = utilities.find_dbscan_eps(val_embeddings, min_samples=min_samples)
                    db = DBSCAN(eps=eps, min_samples=min_samples)
                    pred_labels = db.fit_predict(val_embeddings)
                    eps_values = [eps]

                    # --- Graph-based Voting with Index Alignment ---
                    # Expand pred_labels to full graph size for voting
                    num_vars = data['variable'].num_nodes
                    full_pred_labels = np.full(num_vars, -1, dtype=int)

                    # Map valid predictions back to full array
                    # mask is boolean array of shape (num_vars,)
                    full_pred_labels[mask] = pred_labels

                    # Extract edge_index and counts
                    edge_index = data['variable', 'connected_to', 'constraint'].edge_index
                    num_conss = data['constraint'].num_nodes

                    # Prepare Names for Logging (First instance only)
                    pass_var_names = var_names if i == 0 else None
                    pass_con_names = con_names if i == 0 else None

                    # Perform voting on the FULL graph
                    full_pred_labels = utilities.graph_voting_reassignment(
                        full_pred_labels,
                        edge_index,
                        num_vars,
                        num_conss,
                        embeddings=embeddings,
                        var_names=pass_var_names,
                        con_names=pass_con_names
                    )

                    # Extract back the valid labels for metric computation
                    pred_labels = full_pred_labels[mask]

                    # Compute Metrics
                    ari = adjusted_rand_score(val_labels, pred_labels)
                    nmi = normalized_mutual_info_score(val_labels, pred_labels)
                    v_measure = v_measure_score(val_labels, pred_labels)
                    pcr = calculate_perfect_cluster_ratio(val_labels, pred_labels)

                    metrics['dbscan_ari'].append(ari)
                    metrics['dbscan_nmi'].append(nmi)
                    metrics['dbscan_v_measure'].append(v_measure)
                    metrics['perfect_cluster_ratio'].append(pcr)
                    metrics['num_instances_evaluated_dbscan'] += 1

                    if pcr == 1.0:
                        perfect_instances.append(instance_stem)

                    # --- Map Clusters to Variable Names ---
                    clusters = collections.defaultdict(list)
                    noise_points = []
                    for idx, cluster_id in enumerate(pred_labels):
                        v_name = valid_var_names[idx]
                        if cluster_id == -1:
                            noise_points.append(v_name)
                        else:
                            clusters[int(cluster_id)].append(v_name)

                    # --- Prepare and Save Structured Data (JSON) ---
                    output_data = {
                        "instance_name": instance_stem,
                        "clustering_parameters": {
                            "algorithm": "simple_dbscan",
                            "min_samples": min_samples,
                            "eps_values_used": [float(e) for e in eps_values] if eps_values else []
                        },
                        "summary": {
                            "num_clusters": len(clusters),
                            "num_noise_points": len(noise_points),
                            "metrics": {
                                "ari": ari,
                                "nmi": nmi,
                                "v_measure": v_measure,
                                "pcr": pcr
                            }
                        },
                        "clusters": {str(k): sorted(v) for k, v in clusters.items()},
                        "noise_points": sorted(noise_points)
                    }

                    output_filepath = cluster_output_dir / f"{instance_stem}.json"
                    with open(output_filepath, 'w') as f:
                        json.dump(output_data, f, indent=4)

                except Exception as e:
                    print(f"Error during clustering/saving instance {i}: {e}")
                    import traceback
                    traceback.print_exc()

        # Aggregate and Print
        if metrics['num_instances_evaluated_dbscan'] > 0:
            avg_true_clusters = np.mean(metrics['per_instance_true_n_clusters'])
            num_eval = metrics['num_instances_evaluated_dbscan']
            avg_pcr = np.mean(metrics['perfect_cluster_ratio'])
            avg_v = np.mean(metrics['dbscan_v_measure'])
            avg_ari = np.mean(metrics['dbscan_ari'])
            avg_nmi = np.mean(metrics['dbscan_nmi'])

            # Using simple print to match the requested log format
            print(f"Result for '{folder}':")
            utilities.log(f"  Average number of true clusters per instance: {avg_true_clusters:.2f}")
            utilities.log(f"  Number of instances evaluated for DBSCAN: {num_eval}")
            utilities.log(f"  Average Perfect Cluster Recovery Rate: {avg_pcr:.4f}")
            utilities.log(f"  Average V-Measure (DBSCAN): {avg_v:.4f}")
            utilities.log(f"  Average Adjusted Rand Index (ARI) (DBSCAN): {avg_ari:.4f}")
            utilities.log(f"  Average Normalized Mutual Information (NMI) (DBSCAN): {avg_nmi:.4f}")

            if metrics.get('con_linking_acc'):
                utilities.log(f"  Constraint Linking Binary Accuracy: {np.mean(metrics['con_linking_acc']):.4f}")
            if metrics.get('con_block_acc'):
                utilities.log(f"  Constraint Block Classification Accuracy: {np.mean(metrics['con_block_acc']):.4f}")

            if perfect_instances:
                print(f"  Perfectly Clustered Instances (PCR=1.0):")
                for name in perfect_instances:
                    print(f"    - {name}")
            else:
                print("  No instances were perfectly clustered.")

            print(f"Cluster details saved to {cluster_output_dir}")

        else:
            print(f"No valid results collected for '{folder}'.")

if __name__ == "__main__":
    test()
