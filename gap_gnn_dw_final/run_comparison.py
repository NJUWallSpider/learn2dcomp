"""
Unified GAP solver comparison: SCIP Direct vs GCG GNN vs GCG Auto.

Runs 3 modes on each instance and outputs a comparison CSV.

Usage:
    python run_comparison.py --instance-dir data/raw/gap/test
                             [--warmstart-dir results/decomposition_output]
                             [--modes direct,gcg_gnn,gcg_auto]
                             [--time-limit 600]
                             [--output-csv results/comparison.csv]

Also supports single instance: --instance data/raw/gap/test/1.txt
"""
import sys
import time
import json
import csv
import argparse
from pathlib import Path
from typing import Optional, Dict, List

sys.path.insert(0, str(Path(__file__).parent))

from gap_model import GAPInstance
from gcg_solver import GCGSolver


def _load_instance(inst_path):
    """Load GAP instance from .txt or .lp file."""
    import tempfile, os
    inst_name = Path(inst_path).stem
    if inst_path.endswith('.lp'):
        from gap_generator import lp_to_txt, parse_lp_dims
        from gap_model import GAPInstance
        lp_text = Path(inst_path).read_text()
        na, nt = parse_lp_dims(lp_text)
        with tempfile.NamedTemporaryFile(suffix='.txt', mode='w', delete=False) as tf:
            lp_to_txt(lp_text, tf.name)
            inst = GAPInstance(tf.name)
        os.unlink(tf.name)
        return inst_name, inst.n_jobs, inst.n_machines, inst
    else:
        inst = GAPInstance(inst_path)
        return inst_name, inst.n_jobs, inst.n_machines, inst


def solve_one_instance(inst_path: str, modes: List[str],
                       warmstart_json: Optional[str] = None,
                       time_limit: float = 600,
                       mip_gap: float = 1e-4,
                       verbose: bool = True) -> Dict:
    """Solve one instance with all specified modes. Returns merged dict."""
    inst_name, n_jobs, n_machines, inst = _load_instance(inst_path)

    if verbose:
        print(f"\n{'='*60}")
        print(f"Instance: {inst_name} ({inst.n_jobs}x{inst.n_machines})")
        print(f"{'='*60}")

    result = {
        "instance": inst_name,
        "n_jobs": n_jobs,
        "n_machines": n_machines,
    }

    # Load decomposition JSON once if needed
    decomp_json = None
    if "gcg_gnn" in modes and warmstart_json:
        json_path = Path(warmstart_json)
        if json_path.exists():
            with open(json_path) as f:
                decomp_json = json.load(f)
        elif verbose:
            print(f"  Warning: warmstart JSON not found: {warmstart_json}")

    for mode in modes:
        if verbose:
            print(f"\n--- {mode.upper()} ---")

        try:
            solver = GCGSolver(
                mode=mode,
                time_limit=time_limit,
                mip_gap=mip_gap,
                verbose=verbose,
            )
            res = solver.solve(inst, decomposition_json=decomp_json)

            # Prefix keys with mode name
            for k, v in res.items():
                result[f"{mode}_{k}"] = v

            if verbose:
                print(f"  Status: {res['status']}, "
                      f"Obj: {res['obj_val']}, "
                      f"Time: {res['solve_time']:.2f}s")

        except ImportError as e:
            if verbose:
                print(f"  ImportError: {e} — skipping {mode}")
            result[f"{mode}_status"] = "import_error"
            result[f"{mode}_error"] = str(e)
        except Exception as e:
            if verbose:
                print(f"  Error in {mode}: {e}")
                import traceback
                traceback.print_exc()
            result[f"{mode}_status"] = "error"
            result[f"{mode}_error"] = str(e)

    return result


# ---------------------------------------------------------------------------
# Summary helpers
# ---------------------------------------------------------------------------

def _print_summary(results: List[Dict], modes: List[str]) -> None:
    print(f"\n{'='*60}")
    print(f"Summary ({len(results)} instances)")
    print(f"{'='*60}")

    for mode in modes:
        stat_key = f"{mode}_status"
        time_key = f"{mode}_solve_time"
        obj_key  = f"{mode}_obj_val"

        solved = [r for r in results if r.get(stat_key) == "optimal"]
        times = [r[time_key] for r in solved if time_key in r]
        objs  = [r[obj_key] for r in solved if obj_key in r]

        n_solved = len(solved)
        n_total  = len(results)
        avg_time = sum(times) / len(times) if times else float("nan")
        avg_obj  = sum(objs) / len(objs) if objs else float("nan")

        print(f"  {mode:12s}  solved={n_solved}/{n_total}  "
              f"avg_time={avg_time:.1f}s  avg_obj={avg_obj:.2f}")

    # Cross-mode obj consistency
    common = [
        r for r in results
        if all(r.get(f"{m}_status") == "optimal" for m in modes)
    ]
    if common:
        print(f"\n  All {len(modes)} modes optimal on {len(common)} instances")
        for i, m1 in enumerate(modes):
            for m2 in modes[i+1:]:
                diffs = [
                    abs(r[f"{m1}_obj_val"] - r[f"{m2}_obj_val"])
                    for r in common
                    if f"{m1}_obj_val" in r and f"{m2}_obj_val" in r
                ]
                max_diff = max(diffs) if diffs else 0
                print(f"  Max obj diff {m1} vs {m2}: {max_diff:.6f}")


def _save_csv_incremental(row: Dict, csv_path: str, write_header: bool) -> None:
    """Append one row to CSV immediately after each instance completes."""
    Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
    mode = "w" if write_header else "a"
    with open(csv_path, mode, newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def _save_csv(results: List[Dict], modes: List[str],
              csv_path: Optional[str]) -> None:
    if not csv_path or not results:
        return

    output_path = Path(csv_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Build fieldnames from the union of keys present in results
    fieldnames = ["instance", "n_jobs", "n_machines"]
    for mode in modes:
        fieldnames += [
            f"{mode}_status",
            f"{mode}_obj_val",
            f"{mode}_solve_time",
            f"{mode}_gap",
            f"{mode}_n_nodes",
            f"{mode}_n_iterations",
        ]

    # Only include fields that actually exist
    existing = set()
    for r in results:
        existing.update(r.keys())
    fieldnames = [f for f in fieldnames if f in existing]

    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)

    print(f"\nResults saved to {output_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="GAP solver comparison: SCIP Direct vs GCG GNN vs GCG Auto"
    )
    parser.add_argument("--instance", type=str, default=None,
                        help="Path to single .txt instance")
    parser.add_argument("--instance-dir", type=str, default=None,
                        help="Directory of .txt instances")
    parser.add_argument("--warmstart-dir", type=str, default=None,
                        help="Directory of GNN decomposition JSON files")
    parser.add_argument("--modes", type=str, default="direct,gcg_gnn,gcg_auto",
                        help="Comma-separated modes")
    parser.add_argument("--output-csv", type=str, default=None,
                        help="Path to output CSV")
    parser.add_argument("--time-limit", type=float, default=600,
                        help="Solver time limit per instance (seconds)")
    parser.add_argument("--mip-gap", type=float, default=1e-4,
                        help="MIP optimality gap tolerance")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress per-instance output")
    args = parser.parse_args()

    modes = [m.strip() for m in args.modes.split(",")]

    # --- Collect instances ---
    if args.instance:
        instances = [args.instance]
    elif args.instance_dir:
        instances = sorted(str(p) for p in Path(args.instance_dir).glob("*.lp"))
        if not instances:
            instances = sorted(str(p) for p in Path(args.instance_dir).glob("*.txt"))
    else:
        test_dir = Path(__file__).parent / "data" / "raw" / "gap" / "test"
        instances = sorted(str(p) for p in test_dir.glob("*.txt"))

    if not instances:
        print("No instances found.")
        return

    warmstart_dir = Path(args.warmstart_dir) if args.warmstart_dir else None
    verbose = not args.quiet

    # --- Resume: skip already-completed instances ---
    completed = set()
    csv_path = args.output_csv
    if csv_path and Path(csv_path).exists():
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                completed.add(row.get("instance", ""))
        print(f"Resuming: {len(completed)} instances already in {csv_path}")

    results = []
    first_write = (not csv_path) or (not Path(csv_path).exists())

    for i, inst_path in enumerate(instances):
        inst_name = Path(inst_path).stem
        if inst_name in completed:
            print(f"\n[{i+1}/{len(instances)}] {inst_name} — SKIP (done)")
            continue

        print(f"\n[{i+1}/{len(instances)}] {inst_name}")

        ws_json = None
        if warmstart_dir:
            p = warmstart_dir / f"{inst_name}_decomposition.json"
            if p.exists():
                ws_json = str(p)
            elif verbose:
                print(f"  (no decomposition JSON for {inst_name})")

        try:
            result = solve_one_instance(
                inst_path, modes,
                warmstart_json=ws_json,
                time_limit=args.time_limit,
                mip_gap=args.mip_gap,
                verbose=verbose,
            )
            results.append(result)

            # Save immediately after each instance
            if csv_path:
                _save_csv_incremental(result, csv_path, first_write)
                first_write = False

        except Exception as e:
            print(f"  FATAL: {e}")
            import traceback
            traceback.print_exc()
            # Save error entry
            if csv_path:
                err_row = {"instance": inst_name, "error": str(e)}
                _save_csv_incremental(err_row, csv_path, first_write)
                first_write = False

    # --- Summarize ---
    if results:
        _print_summary(results, modes)
        _save_csv(results, modes, args.output_csv)


if __name__ == "__main__":
    main()
