import torch
from torch_geometric.loader import DataLoader
import numpy as np
from sklearn.cluster import DBSCAN
import config
from data_process import MILPDataset, add_laplacian_pe
from gnn_model import GraphTransformer
import utilities
from tqdm import tqdm
import json
from pathlib import Path
import collections
import os
import argparse


def derive_assignment_from_clusters(final_labels, valid_var_names, embeddings):
    """
    Derive job->machine assignment from GNN variable clustering.

    Parses variable names like 'x_0_1' (job_0, machine_1) and maps each
    cluster to the dominant machine, then produces a concrete assignment.

    Returns dict: {job_id: machine_id, ...}
    """
    # Parse variable names
    var_info = []  # [(job_idx, machine_idx), ...]
    for name in valid_var_names:
        parts = name.split('_')
        if len(parts) >= 3 and parts[0] == 'x':
            var_info.append((int(parts[1]), int(parts[2])))
        else:
            var_info.append(None)

    # Map cluster -> dominant machine
    cluster_machine_votes = collections.defaultdict(lambda: collections.Counter())
    for idx, label in enumerate(final_labels):
        if label >= 0 and var_info[idx] is not None:
            _i, j = var_info[idx]
            cluster_machine_votes[label][j] += 1

    cluster_to_machine = {}
    for cluster_id, votes in cluster_machine_votes.items():
        if votes:
            cluster_to_machine[cluster_id] = votes.most_common(1)[0][0]

    # Determine n_jobs and n_machines from variable names
    valid_infos = [vi for vi in var_info if vi is not None]
    if not valid_infos:
        return {}
    n_jobs = max(vi[0] for vi in valid_infos) + 1

    # For each job, find consistent machine assignment
    assignment = {}
    for i in range(n_jobs):
        candidates = {}  # machine -> score (negated distance to cluster center)
        for idx, label in enumerate(final_labels):
            if label >= 0 and var_info[idx] is not None:
                vi, j = var_info[idx]
                if vi == i and label in cluster_to_machine:
                    if cluster_to_machine[label] == j:
                        # Variable is consistent: its cluster maps to its machine
                        dist = np.linalg.norm(embeddings[idx] - np.mean(
                            embeddings[final_labels == label], axis=0))
                        candidates[j] = -dist  # closer = higher score

        if candidates:
            assignment[i] = max(candidates, key=candidates.get)

    return assignment


def evaluate_instances(input_dir=None, output_dir=None, model_path=None):
    # 1. Configuration & Setup
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Using device: {device}")

    if model_path is None:
        model_path = config.MODELS_DIR / "best_model.pth"
    else:
        model_path = Path(model_path)

    if not model_path.exists():
        print(f"Error: Model file not found at {model_path}")
        return

    print(f"Loading model from {model_path}...")
    try:
        mp = config.MODEL_PARAMS
        model = GraphTransformer(
            hidden_dim=mp['emb_size'],
            num_layers=mp.get('num_layers', 2),
            num_heads=mp.get('num_heads', 4),
            pe_dim=mp.get('pe_dim', 8),
            block_pe_dim=mp.get('block_pe_dim', 8),
            max_con_blocks=mp.get('max_con_blocks', 128),
        ).to(device)
        model.load_state_dict(torch.load(model_path, map_location=device))
        model.eval()
    except Exception as e:
        print(f"Failed to load model: {e}")
        return

    # Determine input files
    if input_dir is None:
        folder_name = config.TEST_FOLDERS[0]
        input_dir = config.PROCESSED_DATA_DIR / config.TRAIN_PARAMS['problem'] / folder_name
    else:
        input_dir = Path(input_dir)

    if not input_dir.exists():
        print(f"Input directory not found: {input_dir}")
        return

    # Collect .pt files
    if input_dir.is_file() and input_dir.suffix == '.pt':
        files = [str(input_dir)]
        input_dir = input_dir.parent
    else:
        files = sorted([str(f) for f in input_dir.glob("*.pt")])

    if not files:
        print(f"No .pt files found in {input_dir}")
        return

    # Setup Output Directory
    if output_dir is None:
        output_dir = config.RESULTS_DIR / "decomposition_output"
    else:
        output_dir = Path(output_dir)

    os.makedirs(output_dir, exist_ok=True)
    print(f"Output directory: {output_dir}")

    # Dataset & Loader
    dataset = MILPDataset(files)  # PE already in .pt
    loader = DataLoader(
        dataset,
        batch_size=1,
        shuffle=False,
        num_workers=config.TRAIN_PARAMS['num_workers']
    )

    print(f"Processing {len(dataset)} instances...")

    with torch.no_grad():
        for i, data in enumerate(tqdm(loader)):
            # Retrieve variable names
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

            pt_path = Path(dataset.sample_files[i])
            instance_name = pt_path.stem

            data = data.to(device)

            # Model Inference
            try:
                var_emb, con_emb, con_block_logits, con_linking_logits = model(data)
            except Exception as e:
                print(f"Error processing {instance_name}: {e}")
                continue

            embeddings = var_emb.cpu().numpy()
            labels = data['variable'].y.cpu().numpy()

            mask = labels >= 0
            if mask.sum() == 0:
                mask = np.ones(len(labels), dtype=bool)

            val_embeddings = embeddings[mask]

            # Handle Variable Names
            valid_var_names = []
            if var_names:
                if len(var_names) == len(labels):
                    valid_var_names = np.array(var_names)[mask].tolist()
                else:
                    valid_var_names = [f"var_{idx}" for idx in np.where(mask)[0]]
            else:
                valid_var_names = [f"var_{idx}" for idx in np.where(mask)[0]]

            # ================================================================
            # Variable DBSCAN → primary decomposition
            # ================================================================
            frac = config.EVAL_PARAMS.get('dbscan_min_samples_frac', 0.05)
            min_samples = max(2, int(len(val_embeddings) * frac))
            pred_labels, eps_values = utilities.hierarchical_dbscan(
                val_embeddings,
                min_samples=min_samples,
                start_scale=0.2,
                step_scale=0.2,
                max_scale=4.0,
            )
            pred_labels = utilities.reassign_noise_points(val_embeddings, pred_labels)

            # ================================================================
            # Derive constraint decomposition from variable clusters
            # (same logic as reference: if a constraint's variables all in
            #  the same block → block, else → master/linking)
            # ================================================================
            num_vars = data['variable'].num_nodes
            full_pred_labels = np.full(num_vars, -1, dtype=int)
            full_pred_labels[mask] = pred_labels

            edge_index = data['variable', 'connected_to', 'constraint'].edge_index
            num_conss = data['constraint'].num_nodes
            ei = edge_index.cpu().numpy()

            # Build variable→cluster mapping
            var_cluster = full_pred_labels  # full graph, with cluster IDs
            con_linking_pred = []
            con_block_pred = {}
            for c in range(num_conss):
                cname = con_names[c] if con_names and c < len(con_names) else str(c)
                v_indices = ei[0, ei[1] == c]
                if len(v_indices) == 0:
                    con_linking_pred.append(cname)
                    continue
                clusters = set(var_cluster[v] for v in v_indices if var_cluster[v] >= 0)
                if len(clusters) == 1:
                    con_block_pred[cname] = int(list(clusters)[0])
                else:
                    con_linking_pred.append(cname)

            # Derive job->machine assignment from variable clusters
            assignment = derive_assignment_from_clusters(
                pred_labels, valid_var_names, val_embeddings
            )

            # GNN classifier predictions (for reference)
            con_pred = {}
            if con_linking_logits is not None:
                linking_pred = (torch.sigmoid(con_linking_logits).cpu().numpy() > 0.5).flatten()
                block_pred = con_block_logits.argmax(dim=1).cpu().numpy()
                con_pred = {
                    "linking_constraints": [
                        con_names[idx] if con_names and idx < len(con_names) else str(idx)
                        for idx in np.where(linking_pred)[0]
                    ],
                    "block_assignments": {
                        (con_names[idx] if con_names and idx < len(con_names) else str(idx)): int(block_pred[idx])
                        for idx in range(len(block_pred)) if not linking_pred[idx]
                    }
                }

            output_data = {
                "instance_name": instance_name,
                "assignment": {str(k): v for k, v in assignment.items()},
                "constraint_decomposition": {
                    "linking_constraints": con_linking_pred,
                    "block_assignments": con_block_pred,
                },
                "classifier_prediction": con_pred,
                "stats": {
                    "num_con_blocks": len(set(v for v in con_block_pred.values())),
                    "num_con_linking": len(con_linking_pred),
                    "total_vars": len(pred_labels),
                    "num_assigned_jobs": len(assignment),
                }
            }

            # Save to JSON
            out_file = output_dir / f"{instance_name}_decomposition.json"
            with open(out_file, 'w') as f:
                json.dump(output_data, f, indent=4)

    print(f"Decomposition results saved to {output_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate instances and generate decomposition clusters.")
    parser.add_argument('--input', type=str, help="Path to input .pt file or directory.")
    parser.add_argument('--output', type=str, help="Directory to save output JSON files.")
    parser.add_argument('--model', type=str, help="Path to trained model .pth file.")

    args = parser.parse_args()

    evaluate_instances(args.input, args.output, args.model)
