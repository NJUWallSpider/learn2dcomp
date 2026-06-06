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
#
# Chu & Beasley (1997) Types A–E with cross-scale random sizes.
#   Type A: independent [5,25]×[1,25], tightness 1.30
#   Type B: independent [1,100]×[1,100], tightness 0.50 (HARD)
#   Type C: negative correlation c=111-w, tightness 1.30 (HARD)
#   Type D: negative correlation + noise, tightness 1.30
#   Type E: positive correlation, tightness 1.30
#
# Test uses agent counts OUTSIDE training range for generalization.
GAP_GEN = {
    'train': {
        'n_instances': 1000,
        'n_agents_min': 5,  'n_agents_max': 12,
        'n_tasks_min': 40,  'n_tasks_max': 100,
        'types': ["A", "B", "C", "D", "E"],
        'overwrite': False,
    },
    'valid': {
        'n_instances': 100,
        'n_agents_min': 5,  'n_agents_max': 12,
        'n_tasks_min': 40,  'n_tasks_max': 100,
        'types': ["A", "B", "C", "D", "E"],
        'overwrite': False,
    },
    'test': {
        'n_instances': 100,
        'n_agents_min': 13, 'n_agents_max': 16,  # unseen agent counts!
        'n_tasks_min': 40,  'n_tasks_max': 100,
        'types': ["A", "B", "C", "D", "E"],
        'overwrite': False,
    },
}

# --- GNN Model Parameters ---
MODEL_PARAMS = {
    'emb_size': 128,
    'pe_dim': 8,
    'block_pe_dim': 8,
    'num_layers': 2,
    'num_heads': 4,
    'max_con_blocks': 128,
}

# --- Training Hyperparameters ---
TRAIN_PARAMS = {
    'problem': 'gap',
    'seed': 42,
    'max_epochs': 50,
    'batch_size': 8,
    'lr': 0.001,
    'patience': 15,
    'early_stopping': 30,
    'temperature': 0.3,
    'num_workers': 4,           # O4: reduced for stability
    'enable_vis': True,
    'boundary_weight': 2.0,     # T-004: extra weight for boundary variables
    'con_block_weight': 0.5,
    'con_linking_weight': 0.3,
    # O4: Curriculum learning — switch to hard types after stage 1
    'curriculum_switch_epoch': 10,      # switch to B+C at epoch 10
    'curriculum_hard_types': ['_typeB_', '_typeC_'],  # hard types for stage 2
}

# --- Test Parameters ---
TEST_FOLDERS = ["test", "large"]

# --- Evaluation Parameters ---
EVAL_FOLDERS = ["test"]

EVAL_PARAMS = {
    'test_batch_size': 1,
    'dbscan_min_samples_frac': 0.05,  # adaptive: frac * n_vars
}

# --- GCG Solver Configuration ---
GCG_CONFIG = {
    # All available comparison modes
    'available_modes': ['direct', 'gcg_gnn', 'gcg_auto'],

    # Default mode override (used by gcg_solver.py when mode not specified)
    'default_mode': 'gcg_gnn',

    # Solver limits
    'solver': {
        'time_limit': 600,         # seconds per instance
        'mip_gap': 1e-4,
        'verbose': False,
    },

    # GCG-specific parameters (applied to GCG modes only)
    'gcg_params': {
        'presolving/maxrounds': 20,
        'propagating/maxrounds': 100,
        'separating/maxrounds': 100,
    },
}

# --- Comparison Output ---
COMPARISON_RESULTS_DIR = RESULTS_DIR / "comparison"
