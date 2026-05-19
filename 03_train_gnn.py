import torch
from torch_geometric.loader import DataLoader
import config
from data_process import MILPDataset, collate_fn_for_supcon, add_laplacian_pe
from gnn_model import GraphTransformer, SupConLoss
import os
from training_visualizer import TrainingVisualizer

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

    # Use add_laplacian_pe as transform
    # Note: k=8 default matches model pe_dim=8 default
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
    model = GraphTransformer(hidden_dim=config.MODEL_PARAMS['emb_size']).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=params['lr'])
    criterion = SupConLoss(temperature=params['temperature'])
    
    # 4. Training Loop
    best_loss = float('inf')
    patience = params['patience']
    patience_counter = 0
    
    # Initialize Visualizer
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
            
            # Apply label offset for SupCon
            # We assume batch is a HeteroDataBatch object from PyG DataLoader
            batch = collate_fn_for_supcon(batch)
            
            optimizer.zero_grad()
            
            # Forward
            embeddings = model(batch)
            
            # Loss
            labels = batch['variable'].y
            mask = labels >= 0
            
            if mask.sum() > 0:
                loss = criterion(embeddings[mask], labels[mask])
                loss.backward()
                optimizer.step()
                total_loss += loss.item()
                count += 1
                
        avg_loss = total_loss / count if count > 0 else 0
        
        # Validation
        model.eval()
        val_loss = 0
        val_count = 0
        with torch.no_grad():
            for batch in valid_loader:
                batch = batch.to(device)
                batch = collate_fn_for_supcon(batch)
                embeddings = model(batch)
                labels = batch['variable'].y
                mask = labels >= 0
                if mask.sum() > 0:
                    loss = criterion(embeddings[mask], labels[mask])
                    val_loss += loss.item()
                    val_count += 1
        
        avg_val_loss = val_loss / val_count if val_count > 0 else 0
        
        print(f"Epoch {epoch+1}/{params['max_epochs']}: Train Loss {avg_loss:.4f}, Val Loss {avg_val_loss:.4f}")
        
        if visualizer:
            visualizer.update(epoch + 1, avg_loss, avg_val_loss)

        # Early Stopping
        if avg_val_loss < best_loss:
            best_loss = avg_val_loss
            patience_counter = 0
            # Save model
            os.makedirs(config.MODELS_DIR, exist_ok=True)
            torch.save(model.state_dict(), config.MODELS_DIR / "best_model.pth")
            # print("  Model saved.")
        else:
            patience_counter += 1
            if patience_counter >= patience:
                print("Early stopping triggered.")
                break

if __name__ == "__main__":
    train()
