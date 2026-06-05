import csv
import torch
import torch.nn.functional as F
from torch_geometric.loader import DataLoader
import config
from data_process import MILPDataset, collate_fn_for_supcon, add_laplacian_pe
from gnn_model import GraphTransformer, EnhancedSupConLoss
import os
try:
    from training_visualizer import TrainingVisualizer
except ImportError:
    TrainingVisualizer = None


def _log_epoch(csv_path, epoch, train_loss, val_loss):
    """Append one epoch to training log CSV (incremental crash-safe)."""
    write_header = not os.path.exists(csv_path)
    with open(csv_path, 'a', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['epoch', 'train_loss', 'val_loss'])
        if write_header:
            w.writeheader()
        w.writerow({'epoch': epoch, 'train_loss': train_loss, 'val_loss': val_loss})

def compute_joint_loss(model_outputs, batch, criterion, params):
    """
    Joint loss: SupCon (variables) + Block CE (constraints) + Linking BCE (constraints)
    """
    var_emb, con_emb, con_block_logits, con_linking_logits = model_outputs

    total_loss = torch.tensor(0.0, device=var_emb.device)
    loss_components = {}

    # 1. Variable SupCon Loss (with boundary weighting)
    var_labels = batch['variable'].y
    var_mask = var_labels >= 0

    if var_mask.sum() > 0:
        batch_idx = batch['variable'].batch[var_mask]
        edge_key = ('variable', 'connected_to', 'constraint')
        if hasattr(criterion, 'boundary_weight') and edge_key in batch.edge_index_dict:
            ei = batch.edge_index_dict[edge_key]
            nv = batch['variable'].x.shape[0]
            nc = batch['constraint'].x.shape[0]
            supcon_loss = criterion(var_emb[var_mask], var_labels[var_mask],
                                     batch_idx,
                                     edge_index=ei, num_vars=nv, num_cons=nc)
        else:
            supcon_loss = criterion(var_emb[var_mask], var_labels[var_mask],
                                     batch_idx)
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

    train_dataset = MILPDataset(train_files)  # PE already in .pt
    valid_dataset = MILPDataset(valid_files)  # PE already in .pt

    # O4: Curriculum learning — filter hard types for stage 2
    switch_epoch = params.get('curriculum_switch_epoch', 0)
    hard_patterns = params.get('curriculum_hard_types', [])
    if switch_epoch > 0 and hard_patterns:
        hard_files = [f for f in train_files if any(p in f for p in hard_patterns)]
        if hard_files:
            print(f"Curriculum: {len(hard_files)}/{len(train_files)} hard instances for stage 2 "
                  f"(epoch {switch_epoch}+)")
        else:
            print("Warning: no hard instances found, disabling curriculum")
            switch_epoch = 0

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
        block_pe_dim=model_params.get('block_pe_dim', 8),
        max_con_blocks=model_params.get('max_con_blocks', 128),
    ).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=params['lr'])
    criterion = EnhancedSupConLoss(temperature=params['temperature'],
                                    boundary_weight=params.get('boundary_weight', 2.0))

    # Resume from latest checkpoint if available
    start_epoch = 0
    best_loss = float('inf')
    ckpt_dir = config.MODELS_DIR
    os.makedirs(ckpt_dir, exist_ok=True)
    ckpts = sorted(ckpt_dir.glob("checkpoint_epoch*.pth"))
    log_csv = ckpt_dir / "training_log.csv"
    if ckpts:
        latest = ckpts[-1]
        model.load_state_dict(torch.load(latest, map_location=device))
        start_epoch = int(latest.stem.split("epoch")[-1])
        # Read best loss from log
        if log_csv.exists():
            with open(log_csv, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    vl = float(row.get('val_loss', 'inf'))
                    if vl < best_loss:
                        best_loss = vl
        print(f"Resumed from {latest} (epoch {start_epoch}, best_val={best_loss:.4f})")
    else:
        print("No checkpoint found, training from scratch.")

    # 4. Training Loop
    patience = params['patience']
    patience_counter = 0

    visualizer = None
    if params.get('enable_vis', False) and TrainingVisualizer is not None:
        visualizer = TrainingVisualizer(save_dir=config.RESULTS_DIR / 'training_plots')

    grad_accum = params.get('grad_accum', 1)
    os.makedirs(config.MODELS_DIR, exist_ok=True)
    log_csv = config.MODELS_DIR / "training_log.csv"
    print(f"Starting multi-task training (Var SupCon + Con Block + Con Linking)...")
    print(f"  grad_accum={grad_accum}, effective_batch={params['batch_size'] * grad_accum}")
    print(f"  Log: {log_csv}")

    for epoch in range(start_epoch, params['max_epochs']):
        # O4: Curriculum switch — swap to hard instances for stage 2
        if switch_epoch > 0 and hard_files and epoch == switch_epoch:
            hard_dataset = MILPDataset(hard_files)
            train_loader = DataLoader(
                hard_dataset,
                batch_size=params['batch_size'],
                shuffle=True,
                num_workers=params['num_workers']
            )
            print(f"Curriculum: switched to {len(hard_files)} hard instances (Type B+C)")
        model.train()
        total_loss_sum = 0
        count = 0
        optimizer.zero_grad()

        for step, batch in enumerate(train_loader):
            batch = batch.to(device)
            batch = collate_fn_for_supcon(batch)

            outputs = model(batch)
            loss, _ = compute_joint_loss(outputs, batch, criterion, params)

            if loss.item() > 0:
                loss = loss / grad_accum
                loss.backward()
                total_loss_sum += loss.item() * grad_accum
                count += 1

                if (step + 1) % grad_accum == 0:
                    optimizer.step()
                    optimizer.zero_grad()

        # Flush remaining gradients
        if count % grad_accum != 0:
            optimizer.step()
            optimizer.zero_grad()

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

        # Incremental CSV log
        _log_epoch(log_csv, epoch + 1, avg_loss, avg_val_loss)

        if visualizer:
            visualizer.update(epoch + 1, avg_loss, avg_val_loss)

        # Checkpoint every 20 epochs (crash recovery)
        if (epoch + 1) % 20 == 0:
            torch.save(model.state_dict(),
                       config.MODELS_DIR / f"checkpoint_epoch{epoch+1}.pth")
            print(f"  [checkpoint saved at epoch {epoch+1}]")

        # Early Stopping
        if avg_val_loss < best_loss:
            best_loss = avg_val_loss
            patience_counter = 0
            torch.save(model.state_dict(), config.MODELS_DIR / "best_model.pth")
        else:
            patience_counter += 1
            if patience_counter >= patience:
                print("Early stopping triggered.")
                break

    print("Training complete.")

if __name__ == "__main__":
    train()
