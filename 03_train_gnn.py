import argparse
import torch
from torch_geometric.loader import DataLoader
import config
from data_process import MILPDataset, collate_fn_for_supcon
from gnn_model import GraphTransformer, EnhancedSupConLoss
import os
from training_visualizer import TrainingVisualizer


def train(problem=None):
    params = config.TRAIN_PARAMS
    if problem is None:
        problem = params['problem']
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Using device: {device}")
    print(f"Problem: {problem}")

    train_dir = config.PROCESSED_DATA_DIR / problem / 'train'
    valid_dir = config.PROCESSED_DATA_DIR / problem / 'valid'

    train_files = sorted([str(f) for f in train_dir.glob("*.pt")])
    valid_files = sorted([str(f) for f in valid_dir.glob("*.pt")])

    if not train_files:
        print(f"No training files found in {train_dir}")
        return

    train_dataset = MILPDataset(train_files, transform=None)
    valid_dataset = MILPDataset(valid_files, transform=None)

    train_loader = DataLoader(
        train_dataset, batch_size=params['batch_size'], shuffle=True,
        num_workers=params['num_workers'],
    )
    valid_loader = DataLoader(
        valid_dataset, batch_size=params['batch_size'], shuffle=False,
        num_workers=params['num_workers'],
    )

    p0 = config.P0_HOMOPHILIC_PARAMS
    model = GraphTransformer(
        hidden_dim=config.MODEL_PARAMS['emb_size'], num_layers=3,
        pe_dim=config.MODEL_PARAMS.get('pe_dim', 8),
        block_pe_dim=config.MODEL_PARAMS.get('block_pe_dim', 8),
        homophilic_conv_layers=p0.get('homophilic_conv_layers', 0),
        homophilic_conv_heads=p0.get('homophilic_conv_heads', 4),
    ).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=params['lr'])
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode='min', factor=0.5, patience=5, min_lr=1e-6,
    )
    criterion = EnhancedSupConLoss(
        temperature=params['temperature'],
        boundary_weight=params.get('boundary_weight', 2.0),
    )
    scaler = torch.amp.GradScaler('cuda') if device.type == 'cuda' else None

    best_loss = float('inf')
    patience = params['patience']
    patience_counter = 0

    visualizer = None
    if params.get('enable_vis', False):
        visualizer = TrainingVisualizer(save_dir=config.RESULTS_DIR / 'training_plots')

    print("Starting training...")

    for epoch in range(params['max_epochs']):
        model.train()
        total_loss = 0
        count = 0

        for batch in train_loader:
            batch = batch.to(device)
            batch = collate_fn_for_supcon(batch)

            optimizer.zero_grad()

            if scaler is not None:
                with torch.amp.autocast('cuda'):
                    embeddings = model(batch)
                    labels = batch['variable'].y
                    batch_idx = batch['variable'].batch
                    mask = labels >= 0

                if mask.sum() > 0:
                    with torch.amp.autocast('cuda'):
                        loss = criterion(
                            embeddings[mask], labels[mask], batch_idx[mask],
                            edge_index=batch.edge_index_dict[('variable','connected_to','constraint')],
                            num_vars=batch['variable'].x.shape[0],
                            num_cons=batch['constraint'].x.shape[0],
                        )
                    scaler.scale(loss).backward()
                    scaler.unscale_(optimizer)
                    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                    scaler.step(optimizer)
                    scaler.update()
                    total_loss += loss.item()
                    count += 1
            else:
                embeddings = model(batch)
                labels = batch['variable'].y
                batch_idx = batch['variable'].batch
                mask = labels >= 0

                if mask.sum() > 0:
                    loss = criterion(embeddings[mask], labels[mask], batch_idx[mask],
                        edge_index=batch.edge_index_dict[('variable','connected_to','constraint')],
                        num_vars=batch['variable'].x.shape[0],
                        num_cons=batch['constraint'].x.shape[0])
                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                    optimizer.step()
                    total_loss += loss.item()
                    count += 1

        avg_loss = total_loss / count if count > 0 else 0

        model.eval()
        val_loss = 0
        val_count = 0
        with torch.no_grad():
            for batch in valid_loader:
                batch = batch.to(device)
                batch = collate_fn_for_supcon(batch)
                embeddings = model(batch)
                labels = batch['variable'].y
                batch_idx = batch['variable'].batch
                mask = labels >= 0
                if mask.sum() > 0:
                    loss = criterion(embeddings[mask], labels[mask], batch_idx[mask],
                        edge_index=batch.edge_index_dict[('variable','connected_to','constraint')],
                        num_vars=batch['variable'].x.shape[0],
                        num_cons=batch['constraint'].x.shape[0])
                    val_loss += loss.item()
                    val_count += 1

        avg_val_loss = val_loss / val_count if val_count > 0 else 0
        scheduler.step(avg_val_loss)

        print(f"Epoch {epoch+1}/{params['max_epochs']}: "
              f"Train Loss {avg_loss:.4f}, Val Loss {avg_val_loss:.4f}")

        if visualizer:
            visualizer.update(epoch + 1, avg_loss, avg_val_loss)

        if avg_val_loss < best_loss:
            best_loss = avg_val_loss
            patience_counter = 0
            os.makedirs(config.MODELS_DIR, exist_ok=True)
            checkpoint = {
                'model_state_dict': model.state_dict(),
                'arch': {
                    'block_pe_dim': config.MODEL_PARAMS.get('block_pe_dim', 8),
                    'pe_dim': config.MODEL_PARAMS.get('pe_dim', 8),
                    'emb_size': config.MODEL_PARAMS['emb_size'],
                    'homophilic_conv_layers': config.P0_HOMOPHILIC_PARAMS.get('homophilic_conv_layers', 0),
                    'homophilic_conv_heads': config.P0_HOMOPHILIC_PARAMS.get('homophilic_conv_heads', 4),
                },
            }
            torch.save(
                checkpoint,
                config.MODELS_DIR / f"best_model_{problem}.pth",
            )
        else:
            patience_counter += 1
            if patience_counter >= patience:
                print("Early stopping triggered.")
                break


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--problem', type=str, default=None,
                        help=f"Problem name (default: {config.TRAIN_PARAMS['problem']}). "
                             f"Known: {config.get_registered_problems()}")
    args = parser.parse_args()
    train(problem=args.problem)
