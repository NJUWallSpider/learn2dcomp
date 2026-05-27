"""
Pipeline utilities for GAP decomposition workflow.
"""
import re
import json
from pathlib import Path


def parse_gap_decomposition(json_path):
    """
    Parse GAP decomposition JSON output from 06_eval_instances.py.

    Expected format:
        {"assignment": {job_id: machine_id, ...}, "subproblems": {...}, ...}

    Returns:
        assignment: dict[int, int] — {job_id: machine_id}
    """
    with open(json_path, 'r') as f:
        data = json.load(f)

    assignment_raw = data.get("assignment", {})
    assignment = {int(k): int(v) for k, v in assignment_raw.items()}
    return assignment
