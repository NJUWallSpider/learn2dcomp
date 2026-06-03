"""
Solve problem instances with GCG/SCIP across three branches (no Gurobi solving):

  1. SCIP direct     — solve original MIP without decomposition (baseline)
  2. GCG (auto)      — GCG auto-detects decomposition structure (baseline)
  3. GCG (GNN)       — GCG with GNN-predicted decomposition (our method)

All solving goes through SCIP/GCG. Gurobi is only used for data processing
(gnn_to_dec reads MPS to infer constraint-to-block assignments).

Output: CSV with instance name, objective, gap, time, nodes, blocks, LP iters.

Usage:
    python 07_solve_decomposition.py --problem gap --split test --time_limit 300
    python 07_solve_decomposition.py --problem rmf --split test --time_limit 300
"""

import os
import sys
import argparse
import csv
import tempfile
from pathlib import Path

import numpy as np

sys.path.append(str(Path(__file__).parent))
import config
from gcg_interface import run_scip_direct, run_gcg_solve, gnn_to_dec


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_gcg_fields(row, prefix, result):
    """Populate row dict with GCG result fields under the given prefix."""
    row[f'{prefix}_Status'] = result['status']
    row[f'{prefix}_Obj'] = result['obj_val']
    row[f'{prefix}_DualBound'] = result['dual_bound']
    row[f'{prefix}_Gap'] = result['gap']
    row[f'{prefix}_Time'] = result['total_time']
    row[f'{prefix}_Nodes'] = result['nodes']
    row[f'{prefix}_MasterLPIters'] = result['master_lp_iters']
    row[f'{prefix}_Blocks'] = result['blocks']
    row[f'{prefix}_Solutions'] = result['solutions_found']


def _write_scip_fields(row, result):
    """Populate row dict with SCIP direct result fields."""
    row['SCIP_Status'] = result['status']
    row['SCIP_Obj'] = result['obj_val']
    row['SCIP_DualBound'] = result['dual_bound']
    row['SCIP_Gap'] = result['gap']
    row['SCIP_Time'] = result['total_time']
    row['SCIP_Nodes'] = result['nodes']
    row['SCIP_Solutions'] = result['solutions_found']


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    known = config.get_registered_problems()
    parser = argparse.ArgumentParser(
        description="3-branch GCG/SCIP comparison: SCIP / GCG(auto) / GCG(GNN)"
    )
    parser.add_argument('--problem', type=str, default='gap', choices=known,
                        help=f"Problem name. Known: {known}")
    parser.add_argument('--split', type=str, default='test')
    parser.add_argument('--time_limit', type=int, default=300)
    parser.add_argument('--output', type=str, default=None)
    parser.add_argument('--decomp_dir', type=str, default=None)
    parser.add_argument('--max_instances', type=int, default=None)
    args = parser.parse_args()

    time_limit = args.time_limit
    mps_dir = config.MPS_DATA_DIR / args.problem / args.split
    json_dir = Path(args.decomp_dir) if args.decomp_dir else config.DECOMP_OUTPUT_DIR
    output_csv = args.output or str(
        config.RESULTS_DIR / f"{args.problem}_dw_results.csv"
    )

    if not mps_dir.exists():
        print(f"MPS directory not found: {mps_dir}")
        return

    mps_files = sorted(mps_dir.glob("*.mps"))
    if not mps_files:
        print(f"No .mps files found in {mps_dir}")
        return

    if args.max_instances:
        mps_files = mps_files[:args.max_instances]

    os.makedirs(config.RESULTS_DIR, exist_ok=True)

    fieldnames = [
        'Instance',
        # Branch 1: SCIP direct (no decomposition)
        'SCIP_Status', 'SCIP_Obj', 'SCIP_DualBound', 'SCIP_Gap',
        'SCIP_Time', 'SCIP_Nodes', 'SCIP_Solutions',
        # Branch 2: GCG auto-detect
        'GCG_Auto_Status', 'GCG_Auto_Obj', 'GCG_Auto_DualBound', 'GCG_Auto_Gap',
        'GCG_Auto_Time', 'GCG_Auto_Nodes', 'GCG_Auto_MasterLPIters',
        'GCG_Auto_Blocks', 'GCG_Auto_Solutions',
        # Branch 3: GCG (GNN decomposition — our method)
        'GCG_GNN_Status', 'GCG_GNN_Obj', 'GCG_GNN_DualBound', 'GCG_GNN_Gap',
        'GCG_GNN_Time', 'GCG_GNN_Nodes', 'GCG_GNN_MasterLPIters',
        'GCG_GNN_Blocks', 'GCG_GNN_Solutions',
    ]

    with open(output_csv, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

    results = []

    for idx, mps_file in enumerate(mps_files):
        instance_name = mps_file.stem
        json_file = json_dir / f"{instance_name}_decomposition.json"

        print(f"\n{'='*60}")
        print(f"[{idx+1}/{len(mps_files)}] {instance_name}")
        print(f"{'='*60}")

        row = {'Instance': instance_name}

        # ---- Branch 1: SCIP direct ----
        print("  [1/3] SCIP direct ...")
        try:
            scip_result = run_scip_direct(mps_file, time_limit=time_limit)
            _write_scip_fields(row, scip_result)
            print(f"    Obj={scip_result['obj_val']}, Gap={scip_result['gap']}%, "
                  f"Time={scip_result['total_time']:.1f}s")
        except Exception as e:
            print(f"    SCIP failed: {e}")

        # ---- Branch 2: GCG auto-detect ----
        print("  [2/3] GCG (auto detect) ...")
        try:
            auto_result = run_gcg_solve(mps_file, dec_path=None,
                                        time_limit=time_limit)
            _write_gcg_fields(row, 'GCG_Auto', auto_result)
            print(f"    Obj={auto_result['obj_val']}, Gap={auto_result['gap']}%, "
                  f"Time={auto_result['total_time']:.1f}s, "
                  f"Blocks={auto_result['blocks']}")
        except Exception as e:
            print(f"    GCG auto failed: {e}")

        # ---- Branch 3: GCG (GNN decomposition) ----
        if json_file.exists():
            print("  [3/3] GCG (GNN) ...")
            try:
                dec_content = gnn_to_dec(json_file, mps_file)
                with tempfile.NamedTemporaryFile(
                    mode='w', suffix='.dec', prefix='gnn_', delete=False
                ) as f:
                    f.write(dec_content)
                    gnn_dec_path = Path(f.name)

                gnn_result = run_gcg_solve(mps_file, dec_path=gnn_dec_path,
                                           time_limit=time_limit)
                gnn_dec_path.unlink(missing_ok=True)

                _write_gcg_fields(row, 'GCG_GNN', gnn_result)
                print(f"    Obj={gnn_result['obj_val']}, Gap={gnn_result['gap']}%, "
                      f"Time={gnn_result['total_time']:.1f}s, "
                      f"Blocks={gnn_result['blocks']}")
            except Exception as e:
                print(f"    GCG GNN failed: {e}")
        else:
            print("  [3/3] GCG (GNN) — no decomposition JSON, skipping.")

        results.append(row)

        # Incremental write — survive crashes
        with open(output_csv, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writerow(row)

    # ---- Summary ----
    if results:
        print(f"\n{'='*60}")
        print(f"Results saved to {output_csv}")
        print(f"{'='*60}")

        def sm(values):
            vals = [v for v in values if v is not None]
            return np.mean(vals) if vals else float('nan')

        print(f"\n--- Summary ({len(results)} instances) ---")

        scip_objs = [r['SCIP_Obj'] for r in results if r.get('SCIP_Obj') is not None]
        scip_times = [r['SCIP_Time'] for r in results if r.get('SCIP_Time') is not None]
        print(f"  SCIP direct  — {len(scip_objs)} solved, "
              f"avg obj: {sm(scip_objs):.1f}, avg time: {sm(scip_times):.1f}s")

        auto_objs = [r['GCG_Auto_Obj'] for r in results if r.get('GCG_Auto_Obj') is not None]
        auto_times = [r['GCG_Auto_Time'] for r in results if r.get('GCG_Auto_Time') is not None]
        auto_blocks = [r['GCG_Auto_Blocks'] for r in results if r.get('GCG_Auto_Blocks') is not None]
        auto_lp = [r['GCG_Auto_MasterLPIters'] for r in results if r.get('GCG_Auto_MasterLPIters') is not None]
        if auto_objs:
            print(f"  GCG auto     — {len(auto_objs)} solved, "
                  f"avg obj: {sm(auto_objs):.1f}, avg time: {sm(auto_times):.1f}s, "
                  f"avg blocks: {sm(auto_blocks):.1f}, "
                  f"avg LP iters: {sm(auto_lp):.0f}")

        gnn_objs = [r['GCG_GNN_Obj'] for r in results if r.get('GCG_GNN_Obj') is not None]
        gnn_times = [r['GCG_GNN_Time'] for r in results if r.get('GCG_GNN_Time') is not None]
        gnn_blocks = [r['GCG_GNN_Blocks'] for r in results if r.get('GCG_GNN_Blocks') is not None]
        gnn_lp = [r['GCG_GNN_MasterLPIters'] for r in results if r.get('GCG_GNN_MasterLPIters') is not None]
        if gnn_objs:
            print(f"  GCG GNN      — {len(gnn_objs)} solved, "
                  f"avg obj: {sm(gnn_objs):.1f}, avg time: {sm(gnn_times):.1f}s, "
                  f"avg blocks: {sm(gnn_blocks):.1f}, "
                  f"avg LP iters: {sm(gnn_lp):.0f}")


if __name__ == "__main__":
    main()
