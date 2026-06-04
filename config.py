import os
from dataclasses import dataclass, field
from typing import Callable, Any
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
DECOMP_DIR = DATA_DIR / "decompositions"       # GCG .dec output files
DECOMP_OUTPUT_DIR = RESULTS_DIR / "decomposition_output"

# --- Problem: GAP (Generalized Assignment Problem) ---
# Types: "A" through "E" matching Chu & Beasley (1997) OR-Library benchmark.
# Each split divides n_instances evenly across all listed types.
# Cross-scale: each split draws random n_agents ∈ [n_agents_min, n_agents_max]
# and n_tasks ∈ [n_tasks_min, n_tasks_max] per instance.
# Test uses agent counts OUTSIDE the training range to measure generalization.
GAP_GEN = {
    'train':    {'n_instances': 1000,
                 'n_agents_min': 5,  'n_agents_max': 12,
                 'n_tasks_min': 40, 'n_tasks_max': 100,
                 'types': ["A","B","C","D","E"]},
    'valid':     {'n_instances': 100,
                  'n_agents_min': 5,  'n_agents_max': 12,
                  'n_tasks_min': 40, 'n_tasks_max': 100,
                  'types': ["A","B","C","D","E"]},
    'test':      {'n_instances': 100,
                  'n_agents_min': 13, 'n_agents_max': 16,   # unseen agent counts!
                  'n_tasks_min': 40, 'n_tasks_max': 100,
                  'types': ["A","B","C","D","E"]},
}

# --- Problem: RMF (Rooted Min-cut Forest / Multi-commodity Flow) ---
# Instances come from GAMS .gms data files in grid/.
# Each defines bandwidths on a grid graph and traffic demands (commodities).
# Train uses smaller graphs (d-6-2, d-6-4), test uses larger (d-6-8).
RMF_GEN = {
    'train':    {'files': ['rmfgen.lam-060.d-6-2-15.gms',
                           'rmfgen.lam-100.d-6-2-15.gms',
                           'rmfgen.lam-060.d-6-4-15.gms',
                           'rmfgen.lam-100.d-6-4-15.gms']},
    'valid':    {'files': ['rmfgen.lam-060.d-6-6-15.gms',
                           'rmfgen.lam-100.d-6-6-15.gms']},
    'test':     {'files': ['rmfgen.lam-060.d-6-8-15.gms',
                           'rmfgen.lam-100.d-6-8-15.gms']},
}

# --- GCG Solver Settings ---
GCG_BINARY = "gcg"          # or full path on your server
GCG_TIME_LIMIT = 60         # seconds per instance for decomposition detection

# --- Feature Extraction Parameters ---
FEATURE_EXTRACTION = {
    'n_anchors': 256,
}
OSIF_EPSILON = 50

# --- GNN Model Parameters ---
MODEL_PARAMS = {
    'emb_size': 128,
    'pe_dim': 8,
    'block_pe_dim': 8,  # T-007 P0+PE: re-enabled for combined experiment
}

BLOCK_PE_PARAMS = {
    'louvain_resolution': 1.0,
    'block_pe_method': 'louvain',
}

P0_HOMOPHILIC_PARAMS = {
    'homophilic_conv_layers': 2,
    'homophilic_conv_heads': 4,
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
    'num_workers': 16,
    'enable_vis': True,
    'boundary_weight': 2.0,        # T-004: loss multiplier for boundary variables
}

# --- Test Parameters ---
TEST_FOLDERS = ["test"]

# --- Evaluation Parameters ---
EVAL_FOLDERS = ["test"]

EVAL_PARAMS = {
    'test_batch_size': 1,
    'hdbscan_min_cluster_size_frac': 0.05,  # min_cluster_size = frac * n_vars (adaptive)
    'hdbscan_min_samples_frac': 0.02,       # min_samples = frac * n_vars (conservative)
}

# --- DW Solver Parameters ---
DW_PARAMS = {
    'time_limit': 300,          # total time limit for CG + MIP (seconds)
    'mip_gap': 1e-4,
    'max_cg_iterations': 100,  # B-003: unified 100 CG for fair ablation comparison
    'artificial_cost': 1e5,     # must exceed max real cost (type C up to ~5000)
}

# ---------------------------------------------------------------------------
# Problem registry — maps problem names to their specifications.
# Each problem defines:
#   - generation spec dict (train/valid/test configs)
#   - generation function: (rng, specs, out_dir) -> None
#   - optional parse function: (mps_path) -> dict (for DW evaluation)
#   - optional solve_dw function: (parsed_data, decomposition) -> dict
# ---------------------------------------------------------------------------

@dataclass
class ProblemSpec:
    """Specification for a problem type in the GNN decomposition framework."""
    name: str
    gen_spec: dict = field(default_factory=dict)
    # Callable: (np.random.Generator, dict, Path) -> None
    generate_fn: Callable[..., None] | None = None
    # Callable: (Path) -> dict  — parse MPS for DW solver data
    parse_model: Callable[[Path], dict] | None = None
    # Callable: (dict, dict | None) -> dict  — run DW solve
    solve_dw: Callable[..., dict] | None = None
    # Callable: (str) -> tuple[int, int] | None  — parse dimensions from instance name
    parse_dims: Callable[[str], tuple] | None = None


# Lazy-imported to avoid circular dependencies at module level.
def _get_gap_generate_fn():
    from solvers.gap_generator import generate_gap_instance
    import numpy as np
    import shutil

    def _generate(rng, specs, out_dir):
        if out_dir.exists():
            shutil.rmtree(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        n_instances = specs['n_instances']
        types = specs.get('types', ['A'])
        for idx in range(n_instances):
            gap_type = types[idx % len(types)]
            na = int(rng.integers(specs['n_agents_min'], specs['n_agents_max'] + 1))
            nt = int(rng.integers(specs['n_tasks_min'], specs['n_tasks_max'] + 1))
            lp_str = generate_gap_instance(n_agents=na, n_tasks=nt, rng=rng, gap_type=gap_type)
            filepath = out_dir / f"a{na}_t{nt}_type{gap_type}_{idx + 1}.lp"
            filepath.write_text(lp_str)
    return _generate


def _get_rmf_generate_fn():
    from solvers.rmf_generator import generate_rmf_instances

    def _generate(rng, specs, out_dir):
        grid_dir = PROJECT_ROOT / "grid"
        out_dir.mkdir(parents=True, exist_ok=True)
        generate_rmf_instances(grid_dir, out_dir, specs.get('files', []))
    return _generate


def _get_gap_parse_dims():
    import re
    def _parse(instance_name: str):
        m = re.match(r'a(\d+)_t(\d+)', instance_name)
        if m:
            return int(m.group(1)), int(m.group(2))
        return None
    return _parse


PROBLEM_REGISTRY: dict[str, ProblemSpec] = {
    'gap': ProblemSpec(
        name='gap',
        gen_spec=GAP_GEN,
        generate_fn=None,  # set below to avoid circular import issues
        parse_model=None,  # set below
        solve_dw=None,     # set below
        parse_dims=None,   # set below
    ),
    'rmf': ProblemSpec(
        name='rmf',
        gen_spec=RMF_GEN,
        generate_fn=None,  # set below
        parse_model=None,  # deferred (NotImplementedError)
        solve_dw=None,     # deferred (NotImplementedError)
        parse_dims=None,   # RMF instance names don't encode dimensions
    ),
}


def get_problem(name: str) -> ProblemSpec:
    """Return the ProblemSpec for the given problem name."""
    if name not in PROBLEM_REGISTRY:
        raise ValueError(f"Unknown problem: {name}. Known: {list(PROBLEM_REGISTRY)}")
    return PROBLEM_REGISTRY[name]


def get_registered_problems() -> list[str]:
    """Return list of registered problem names."""
    return list(PROBLEM_REGISTRY.keys())
