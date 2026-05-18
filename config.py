# 所有GNN相关的文件路径和参数
import os
from pathlib import Path

# --- Project Root ---
# 此配置文件位于项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent

# --- Base Directories ---
DATA_DIR = PROJECT_ROOT / "data"
MODELS_DIR = PROJECT_ROOT / "models"
RESULTS_DIR = PROJECT_ROOT / "results"

# --- Data Subdirectories ---
RAW_DATA_DIR = DATA_DIR / "raw"
MPS_DATA_DIR = DATA_DIR / "mps"
PROCESSED_DATA_DIR = DATA_DIR / "processed"

# --- Instance Generation Parameters ---
INSTANCE_GEN = {
    'facilities': {
        'train': {'n_instances': 1000, 'num_facilities': 50, 'num_customers': 50,'ratio': 5, 'keep_ratio': 0.8, 'perturbation': 0.5, 'overwrite': False}, 
        'valid': {'n_instances': 100, 'num_facilities': 50, 'num_customers': 50, 'ratio': 5, 'keep_ratio': 0.8, 'perturbation': 0.5, 'overwrite': False}, 
        'test': {'n_instances': 100, 'num_facilities': 50, 'num_customers': 50, 'ratio': 5, 'keep_ratio': 0.8, 'perturbation': 0.5, 'overwrite': False},  
        'scale_100': {'n_instances': 100, 'num_facilities': 100, 'num_customers': 100, 'ratio': 5, 'keep_ratio': 0.9, 'perturbation': 0.5, 'overwrite': False},
        'scale_50_200':{'n_instances': 100, 'num_facilities': 50, 'num_customers': 200, 'ratio': 5, 'keep_ratio': 0.9, 'perturbation': 0.5, 'overwrite': True},
    }
}

# --- Feature Extraction Parameters ---
FEATURE_EXTRACTION = {
    'n_anchors': 256,
}
OSIF_EPSILON = 50

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
    'problem': 'facilities',
    'seed': 42,
    'max_epochs': 30,
    'batch_size': 8,
    'lr': 0.0005,
    'patience': 10,
    'early_stopping': 20,
    'temperature': 0.1, # for SupervisedContrastiveLoss
    'num_workers': 8,
    'enable_vis': True,
    'con_block_weight': 0.3,  # weight for constraint block classification loss
    'con_linking_weight': 0.2,  # weight for constraint linking binary loss
}

# --- Test Parameters ---
# TEST_FOLDERS 定义了 `04_test.py` 将要运行评估的文件夹名称列表。
# TEST_CONFIG 存储了每个测试文件夹的特定配置，例如真实的簇数。
# 这里的 'true_n_clusters' 对于CFLP问题来说就是析取的数量，等于'dimension'。
TEST_FOLDERS = ["test"]

# --- Evaluation Parameters ---
EVAL_FOLDERS = ["artificial"]

EVAL_PARAMS = {
    'test_batch_size': 1,
    'dbscan_min_samples': 20,
}
