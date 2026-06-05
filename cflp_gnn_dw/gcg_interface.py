"""
Interface to GCG solver for automatic Dantzig-Wolfe decomposition detection.

Uses PyGCGOpt to run GCG's detection on GAP instances, producing .dec files
that serve as ground-truth labels for GNN training.
"""
import re
from pathlib import Path
from typing import Optional


def detect_decomposition(lp_path: Path, dec_dir: Path,
                          time_limit: int = 120) -> Optional[Path]:
    """
    Run GCG detection on an LP file, write .dec to dec_dir.

    Returns path to the best .dec file, or None on failure.
    """
    from pygcgopt import Model

    try:
        model = Model()
        model.hideOutput()
        model.readProblem(str(lp_path))
        model.setRealParam("limits/time", time_limit)
        model.optimize()

        # The detection happens during solve. Write all decompositions.
        dec_dir.mkdir(parents=True, exist_ok=True)
        model.writeAllDecomps(str(dec_dir))

        # Pick the decomposition that was actually used (the "best" one).
        # GCG names them by type; we pick the one with most blocks
        best = None
        best_blocks = 0
        for f in sorted(dec_dir.glob("*.dec")):
            content = f.read_text()
            n_blocks = content.count("BLOCK ")
            if n_blocks > best_blocks:
                best_blocks = n_blocks
                best = f

        # Clean up: keep only best .dec
        for f in dec_dir.glob("*.dec"):
            if f != best:
                f.unlink()

        return best

    except Exception as e:
        print(f"  GCG detection failed: {e}")
        return None


def parse_dec(dec_path: Path) -> dict:
    """
    Parse a GCG .dec file into constraint-to-block assignments.

    Returns:
        dict with:
          'n_blocks': int,
          'master_conss': list of constraint name strings,
          'block_conss': dict {block_id (int): [constraint names]},
          'con_label': dict {constraint_name: label}
              where label = -2 for master, or block_id for subproblem
    """
    if not dec_path.exists():
        raise FileNotFoundError(f".dec not found: {dec_path}")

    text = dec_path.read_text()
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    n_blocks = 0
    master_conss = []
    block_conss = {}
    current_block = None
    in_master = False

    for line in lines:
        if line.startswith("\\"):  # comment
            continue
        if line == "NBLOCKS":
            continue
        if line.isdigit() and not in_master and current_block is None:
            n_blocks = int(line)
            continue
        if line.startswith("BLOCK "):
            current_block = int(line.split()[1])
            block_conss[current_block] = []
            continue
        if line == "MASTERCONSS":
            in_master = True
            current_block = None
            continue
        if in_master:
            master_conss.append(line)
        elif current_block is not None:
            block_conss[current_block].append(line)

    # Build per-constraint label dict
    con_label = {}
    for name in master_conss:
        con_label[name] = -2   # LINKING
    for bid, names in block_conss.items():
        for name in names:
            con_label[name] = bid  # block ID

    return {
        'n_blocks': n_blocks,
        'master_conss': master_conss,
        'block_conss': block_conss,
        'con_label': con_label,
    }
