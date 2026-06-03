
import argparse
import torch
import numpy as np
import matplotlib.pyplot as plt
from sklearn.manifold import TSNE
import config
from gnn_model import GraphTransformer
from data_process import MILPDataset
from torch_geometric.loader import DataLoader
import os
from pathlib import Path

def visualize_embeddings(problem=None):
    # Setup
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    # Get Test Files
    if problem is None:
        problem = config.TRAIN_PARAMS['problem']
    test_dir = config.PROCESSED_DATA_DIR / problem / "test"
    test_files = sorted(list(test_dir.glob("*.pt")))
    
    if not test_files:
        print(f"No test files found in {test_dir}")
        return

    # Load Dataset (First instance only)
    dataset = MILPDataset(test_files, transform=None)
    loader = DataLoader(dataset, batch_size=1, shuffle=False)
    
    # Load Model
    model_path = config.MODELS_DIR / f'best_model_{problem}.pth'
    if not model_path.exists():
        print("Model not found.")
        return

    # Initialize Model (Same params as training)
    sample_data = dataset[0]
    model = GraphTransformer(
        hidden_dim=config.MODEL_PARAMS['emb_size'],
        pe_dim=config.MODEL_PARAMS.get('pe_dim', 8),
        block_pe_dim=config.MODEL_PARAMS.get('block_pe_dim', 8),
    ).to(device)
    
    model.load_state_dict(torch.load(model_path, map_location=device))
    model.eval()
    
    # Get Data
    data = next(iter(loader))
    data = data.to(device)
    
    # Inference
    with torch.no_grad():
        embeddings = model(data)
        embeddings = embeddings.cpu().numpy()
        labels = data['variable'].y.cpu().numpy()

    # Filter valid labels
    mask = labels >= 0
    val_embeddings = embeddings[mask]
    val_labels = labels[mask]
    
    # t-SNE
    print("Running t-SNE...")
    tsne = TSNE(n_components=2, random_state=42, perplexity=30)
    embeddings_2d = tsne.fit_transform(val_embeddings)
    
    # Plotting
    plt.figure(figsize=(12, 10))
    
    # Color map handling
    unique_labels = np.unique(val_labels)
    # Master is usually 0, Subproblems > 0
    
    # Separate Master and Subproblems for distinct styling if needed
    master_mask = val_labels == 0
    sub_mask = val_labels > 0
    
    # Plot Subproblems with colormap
    scatter = plt.scatter(
        embeddings_2d[sub_mask, 0], 
        embeddings_2d[sub_mask, 1], 
        c=val_labels[sub_mask], 
        cmap='tab20', 
        s=50, 
        alpha=0.7,
        label='Subproblems'
    )
    
    # Plot Master (Black stars)
    plt.scatter(
        embeddings_2d[master_mask, 0], 
        embeddings_2d[master_mask, 1], 
        c='black', 
        marker='*', 
        s=200, 
        label='Master Variables',
        edgecolors='white'
    )

    plt.title(f"t-SNE Visualization of Learned Embeddings\nInstance: {dataset.sample_files[0].stem}")
    plt.legend(loc='best')
    plt.axis('off')
    
    output_path = config.MODELS_DIR / "tsne_visualization.png"
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Visualization saved to {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--problem', type=str, default=None,
                        help=f"Problem name (default: {config.TRAIN_PARAMS['problem']})")
    args = parser.parse_args()
    visualize_embeddings(problem=args.problem)
