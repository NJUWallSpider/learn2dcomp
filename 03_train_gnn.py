import torch
import torch.nn.functional as F
from torch_geometric.loader import DataLoader
import config
from data_process import MILPDataset, collate_fn_for_supcon, add_laplacian_pe
from gnn_model import GraphTransformer, SupConLoss
import os
from training_visualizer import TrainingVisualizer

def compute_joint_loss(model_outputs, batch, criterion, params):
    """
    Joint loss: SupCon (variables) + Block CE (constraints) + Linking BCE (constraints)
    """
    var_emb, con_block_logits, con_linking_logits = model_outputs

    total_loss = torch.tensor(0.0, device=var_emb.device)
    loss_components = {}

    # 1. Variable SupCon Loss
    var_labels = batch['variable'].y
    var_mask = var_labels >= 0

    if var_mask.sum() > 0:
        supcon_loss = criterion(var_emb[var_mask], var_labels[var_mask])
        total_loss += supcon_loss
        loss_components['supcon'] = supcon_loss.item()
    else:
        loss_components['supcon'] = 0.0

    # 2. Constraint losses (if constraint labels exist)
    if hasattr(batch['constraint'], 'y') and batch['constraint'].y is not None:
        con_labels = batch['constraint'].y

        # 2a. Block classification loss (only on LOCAL constraints: label >= 0)
        local_mask = con_labels >= 0
        if local_mask.sum() > 0:
            valid_labels = con_labels[local_mask]
            # Clamp labels that exceed num_classes
            num_classes = con_block_logits.shape[1]
            valid_labels = torch.clamp(valid_labels, 0, num_classes - 1)
            block_loss = F.cross_entropy(con_block_logits[local_mask], valid_labels)
            weight = params.get('con_block_weight', 0.3)
            total_loss += weight * block_loss
            loss_components['con_block'] = block_loss.item()
        else:
            loss_components['con_block'] = 0.0

        # 2b. Linking binary classification loss (on LOCAL vs LINKING constraints)
        linking_mask = (con_labels >= 0) | (con_labels == -2)
        if linking_mask.sum() > 0:
            # Target: 1 if LINKING (-2), 0 if LOCAL (>= 0)
            linking_target = (con_labels[linking_mask] == -2).float().unsqueeze(1)
            linking_loss = F.binary_cross_entropy_with_logits(
                con_linking_logits[linking_mask], linking_target
            )
            weight = params.get('con_linking_weight', 0.2)
            total_loss += weight * linking_loss
            loss_components['con_linking'] = linking_loss.item()
        else:
            loss_components['con_linking'] = 0.0

    return total_loss, loss_components


def train():
    # 1. Config
    params = config.TRAIN_PARAMS
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Using device: {device}")

    # 2. Data Loading
    train_dir = config.PROCESSED_DATA_DIR / params['problem'] / 'train'
    valid_dir = config.PROCESSED_DATA_DIR / params['problem'] / 'valid'

    train_files = sorted([str(f) for f in train_dir.glob("*.pt")])
    valid_files = sorted([str(f) for f in valid_dir.glob("*.pt")])

    if not train_files:
        print(f"No training files found in {train_dir}")
        return

    train_dataset = MILPDataset(train_files, transform=add_laplacian_pe)
    valid_dataset = MILPDataset(valid_files, transform=add_laplacian_pe)

    train_loader = DataLoader(
        train_dataset,
        batch_size=params['batch_size'],
        shuffle=True,
        num_workers=params['num_workers']
    )

    valid_loader = DataLoader(
        valid_dataset,
        batch_size=params['batch_size'],
        shuffle=False,
        num_workers=params['num_workers']
    )

    # 3. Model
    model_params = config.MODEL_PARAMS
    model = GraphTransformer(
        hidden_dim=model_params['emb_size'],
        num_layers=model_params.get('num_layers', 2),
        num_heads=model_params.get('num_heads', 4),
        pe_dim=model_params.get('pe_dim', 8),
        max_con_blocks=model_params.get('max_con_blocks', 128),
    ).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=params['lr'])
    criterion = SupConLoss(temperature=params['temperature'])

    # 4. Training Loop
    best_loss = float('inf')
    patience = params['patience']
    patience_counter = 0

    visualizer = None
    if params.get('enable_vis', False):
        visualizer = TrainingVisualizer(save_dir=config.RESULTS_DIR / 'training_plots')

    print("Starting multi-task training (Var SupCon + Con Block + Con Linking)...")

    for epoch in range(params['max_epochs']):
        model.train()
        total_loss_sum = 0
        count = 0

        for batch in train_loader:
            batch = batch.to(device)
            batch = collate_fn_for_supcon(batch)

            optimizer.zero_grad()

            outputs = model(batch)
            loss, _ = compute_joint_loss(outputs, batch, criterion, params)

            if loss.item() > 0:
                loss.backward()
                optimizer.step()
                total_loss_sum += loss.item()
                count += 1

        avg_loss = total_loss_sum / count if count > 0 else 0

        # Validation
        model.eval()
        val_loss_sum = 0
        val_count = 0
        with torch.no_grad():
            for batch in valid_loader:
                batch = batch.to(device)
                batch = collate_fn_for_supcon(batch)
                outputs = model(batch)
                loss, _ = compute_joint_loss(outputs, batch, criterion, params)
                if loss.item() > 0:
                    val_loss_sum += loss.item()
                    val_count += 1

        avg_val_loss = val_loss_sum / val_count if val_count > 0 else 0

        print(f"Epoch {epoch+1}/{params['max_epochs']}: Train Loss {avg_loss:.4f}, Val Loss {avg_val_loss:.4f}")

        if visualizer:
            visualizer.update(epoch + 1, avg_loss, avg_val_loss)

        # Early Stopping
        if avg_val_loss < best_loss:
            best_loss = avg_val_loss
            patience_counter = 0
            os.makedirs(config.MODELS_DIR, exist_ok=True)
            torch.save(model.state_dict(), config.MODELS_DIR / "best_model.pth")
        else:
            patience_counter += 1
            if patience_counter >= patience:
                print("Early stopping triggered.")
                break

    print("Training complete.")

if __name__ == "__main__":
    train()
