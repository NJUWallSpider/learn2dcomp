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
from data_process import MILPDataset, add_laplacian_pe

def visualize_embeddings():
    # Setup
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    # Get Test Files
    test_dir = config.PROCESSED_DATA_DIR / config.TRAIN_PARAMS['problem'] / "test"
    test_files = sorted(list(test_dir.glob("*.pt")))

    if not test_files:
        print(f"No test files found in {test_dir}")
        return

    # Load Dataset (First instance only)
    dataset = MILPDataset(test_files, transform=add_laplacian_pe)
    loader = DataLoader(dataset, batch_size=1, shuffle=False)

    # Load Model
    model_path = config.MODELS_DIR / 'best_model.pth'
    if not model_path.exists():
        print("Model not found.")
        return

    # Initialize Model (Same params as training)
    sample_data = dataset[0]
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

    # Get Data
    data = next(iter(loader))
    data = data.to(device)

    # Inference
    with torch.no_grad():
        var_emb, _, _, _ = model(data)
        embeddings = var_emb.cpu().numpy()
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
    visualize_embeddings()
