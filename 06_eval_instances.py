import torch
from torch_geometric.loader import DataLoader
import numpy as np
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
            max_con_blocks=mp.get('max_con_blocks', 128),
        ).to(device)
        model.load_state_dict(torch.load(model_path, map_location=device))
        model.eval()
    except Exception as e:
        print(f"Failed to load model: {e}")
        return

    # Determine input files
    if input_dir is None:
        # Default to test folder defined in config
        # Taking the first folder from TEST_FOLDERS as default source
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
        # Parent of file is the input dir context
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
    dataset = MILPDataset(files, transform=add_laplacian_pe)
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
            
            # Retrieve constraint names (needed for voting logic inside utilities if enabled, but here mostly for completeness)
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
                var_emb, con_block_logits, con_linking_logits = model(data)
            except Exception as e:
                print(f"Error processing {instance_name}: {e}")
                continue

            embeddings = var_emb.cpu().numpy()
            labels = data['variable'].y.cpu().numpy() # We use this mask to identify valid variables vs padding/dummies

            # Mask for valid variables (usually labels >= 0 or similar logic if labels exist)
            # If labels are all -1 (inference mode without ground truth), we might need another way.
            # Assuming labels are present as -1 for noise or valid class integers.
            # If this is pure inference without ground truth labels in .pt, we assume all nodes are valid or use a mask if provided.
            # Based on 04_test.py, it uses `mask = labels >= 0`. 
            # If the dataset is for evaluation and has no ground truth, this might be risky if `y` is not set or -1.
            # However, typically MILPDataset ensures `y` exists.
            
            # Let's assume we want to cluster ALL variables that are part of the problem.
            # In 04_test, `mask = labels >= 0` implies we ignore variables labeled -1 (maybe auxiliary/dummy?).
            # For decomposition, we likely want to decompose the original problem variables.
            # Let's stick to the 04_test logic for consistency, assuming -1 labels in input are 'ignore'.
            
            mask = labels >= 0
            if mask.sum() == 0:
                # If no labels >= 0, maybe it's an unlabeled instance?
                # In that case, use all variables.
                mask = np.ones(len(labels), dtype=bool)

            val_embeddings = embeddings[mask]
            
            # Handle Variable Names
            valid_var_names = []
            if var_names:
                if len(var_names) == len(labels):
                     valid_var_names = np.array(var_names)[mask].tolist()
                else:
                     # Fallback if length mismatch
                     valid_var_names = [f"var_{idx}" for idx in np.where(mask)[0]]
            else:
                valid_var_names = [f"var_{idx}" for idx in np.where(mask)[0]]

            # 1. Hierarchical DBSCAN
            min_samples = config.EVAL_PARAMS.get('dbscan_min_samples', 2)
            pred_labels, _ = utilities.hierarchical_dbscan(val_embeddings, min_samples=min_samples)

            # Determine Master Label Logic (Mirroring utilities.py)
            # utilities.graph_voting_reassignment uses: master_label = np.max(valid_labels) + 1
            # We need to know what this value is BEFORE voting modifies it, or infer it after.
            # Actually, `utilities.graph_voting_reassignment` calculates it internally.
            # We can calculate it here to identify which ID becomes the master.
            
            current_valid_labels = pred_labels[pred_labels >= 0]
            if len(current_valid_labels) > 0:
                master_label_id = int(np.max(current_valid_labels) + 1)
            else:
                master_label_id = 0

            # 2. Graph Voting Reassignment
            # We need full graph labels for voting
            num_vars = data['variable'].num_nodes
            full_pred_labels = np.full(num_vars, -1, dtype=int)
            full_pred_labels[mask] = pred_labels
            
            edge_index = data['variable', 'connected_to', 'constraint'].edge_index
            num_conss = data['constraint'].num_nodes

            full_pred_labels = utilities.graph_voting_reassignment(
                full_pred_labels, 
                edge_index, 
                num_vars, 
                num_conss, 
                embeddings=embeddings
            )
            
            final_labels = full_pred_labels[mask]

            # 3. Organize Output
            # Master Problem: Variables with label == master_label_id
            # Subproblems: Variables with other non-negative labels
            # Noise (if any remains): Could be treated as Master or separate. Usually Voting handles this.
            
            subproblems = collections.defaultdict(list)
            master_problem = []
            
            for idx, label in enumerate(final_labels):
                v_name = valid_var_names[idx]
                if label == master_label_id:
                    master_problem.append(v_name)
                elif label == -1:
                    # Treat remaining noise as Master (conservative approach) or keep separate?
                    # "Unassigned" usually go to Master in decomposition.
                    master_problem.append(v_name)
                else:
                    subproblems[int(label)].append(v_name)

            # Re-key subproblems to be 1, 2, 3... sequentially for clean output
            sorted_sub_keys = sorted(subproblems.keys())
            ordered_subproblems = {}
            for new_id, old_id in enumerate(sorted_sub_keys, start=1):
                ordered_subproblems[str(new_id)] = sorted(subproblems[old_id])

            # Constraint classification predictions (for DW decomposition)
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
                "master_problem": sorted(master_problem),
                "subproblems": ordered_subproblems,
                "constraint_decomposition": con_pred,
                "stats": {
                    "num_subproblems": len(ordered_subproblems),
                    "num_master_vars": len(master_problem),
                    "total_vars": len(final_labels)
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