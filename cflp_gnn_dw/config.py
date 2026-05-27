# GNN + DW decomposition project — configuration center
import os
from pathlib import Path

# --- Project Root ---
PROJECT_ROOT = Path(__file__).resolve().parent

# --- Base Directories ---
DATA_DIR = PROJECT_ROOT / "data"
MODELS_DIR = PROJECT_ROOT / "models"
RESULTS_DIR = PROJECT_ROOT / "results"

# --- Data Subdirectories ---
RAW_DATA_DIR = DATA_DIR / "raw"
MPS_DATA_DIR = DATA_DIR / "mps"
PROCESSED_DATA_DIR = DATA_DIR / "processed"

# --- GAP Instance Generation Parameters ---
# capacity_ratio: total_capacity / total_weight, controls feasibility tightness.
# cost_range / weight_range: uniform random ranges for c_{i,j} and w_{i,j}.
GAP_GEN = {
    'train': {
        'n_instances': 1000,
        'n_jobs': 20,
        'n_machines': 5,
        'cost_range': (1, 50),
        'weight_range': (1, 20),
        'capacity_ratio': 0.6,
        'overwrite': False,
    },
    'valid': {
        'n_instances': 100,
        'n_jobs': 20,
        'n_machines': 5,
        'cost_range': (1, 50),
        'weight_range': (1, 20),
        'capacity_ratio': 0.6,
        'overwrite': False,
    },
    'test': {
        'n_instances': 100,
        'n_jobs': 20,
        'n_machines': 5,
        'cost_range': (1, 50),
        'weight_range': (1, 20),
        'capacity_ratio': 0.6,
        'overwrite': False,
    },
    'large': {
        'n_instances': 50,
        'n_jobs': 60,
        'n_machines': 10,
        'cost_range': (1, 50),
        'weight_range': (1, 20),
        'capacity_ratio': 0.6,
        'overwrite': False,
    },
}

# --- GNN Model Parameters ---
MODEL_PARAMS = {
    'emb_size': 128,
    'pe_dim': 8,
    'num_layers': 2,
    'num_heads': 4,
    'max_con_blocks': 128,
}

# --- Training Hyperparameters ---
TRAIN_PARAMS = {
    'problem': 'gap',
    'seed': 42,
    'max_epochs': 30,
    'batch_size': 8,
    'lr': 0.0005,
    'patience': 10,
    'early_stopping': 20,
    'temperature': 0.1,
    'num_workers': 8,
    'enable_vis': True,
    'con_block_weight': 0.3,
    'con_linking_weight': 0.2,
}

# --- Test Parameters ---
TEST_FOLDERS = ["test", "large"]

# --- Evaluation Parameters ---
EVAL_FOLDERS = ["test"]

EVAL_PARAMS = {
    'test_batch_size': 1,
    'dbscan_min_samples': 5,
}
