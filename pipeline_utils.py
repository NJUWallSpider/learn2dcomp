import re
import json
import numpy as np
import gurobipy as gp
from pathlib import Path

class CFLPInstance:
    """
    Efficient container for CFLP instance data using NumPy.
    Replaces the file reading logic scattered across scripts.
    """
    def __init__(self, file_path):
        self.file_path = file_path
        self.n_facilities = 0
        self.n_customers = 0
        self.fixed_costs = None    # Array of shape (n_facilities,)
        self.capacities = None     # Array of shape (n_facilities,)
        self.demands = None        # Array of shape (n_customers,)
        self.transport_costs = None # Matrix of shape (n_facilities, n_customers) or Sparse
        self.valid_pairs = []      # List of tuples (i, j) 0-based

        self._load_data()

    def _load_data(self):
        with open(self.file_path, 'r') as f:
            lines = f.readlines()

        # Metadata
        meta = lines[3].strip().split()
        self.n_facilities = int(meta[0])
        self.n_customers = int(meta[1])

        # Facilities (Lines 5 to 5+M)
        self.fixed_costs = np.zeros(self.n_facilities)
        self.capacities = np.zeros(self.n_facilities)
        
        start_fac = 5
        for i in range(self.n_facilities):
            parts = lines[start_fac + i].strip().split()
            self.fixed_costs[i] = float(parts[0])
            self.capacities[i] = float(parts[1])

        # Demands & Costs
        # Locate "Demand & Transportation Cost"
        start_idx = 0
        for idx, line in enumerate(lines):
            if "Demand & Transportation Cost" in line:
                start_idx = idx + 1
                break
        
        self.demands = np.zeros(self.n_customers)
        # Initialize costs with infinity or a high number
        self.transport_costs = np.full((self.n_facilities, self.n_customers), np.inf)

        # Read interleaved lines (Demand line, Cost line, Demand line...)
        # Data block usually has 2 * n_customers lines
        data_lines = [l.strip().split() for l in lines[start_idx : start_idx + self.n_customers * 2]]
        
        demand_lines = data_lines[0::2]
        cost_lines = data_lines[1::2]

        for j in range(self.n_customers):
            # 0-based index for internal logic
            self.demands[j] = float(demand_lines[j][1])
            
            costs = np.array(cost_lines[j], dtype=float)
            # Store valid costs
            valid_indices = np.where(costs < 1e9)[0] # Assuming < 1e9 is valid
            self.transport_costs[valid_indices, j] = costs[valid_indices]
            
            for i in valid_indices:
                self.valid_pairs.append((i, j))


class DecompositionParser:
    """
    Parses the GNN JSON output and converts string variable names 
    into Integer Sets for facilities and customers.
    """
    def __init__(self):
        # Pre-compile regex for performance
        # Matches: master_y_12 -> 12
        self.re_fac = re.compile(r"master_y_(\d+)")
        # Matches: subproblem_5_x_12_5 -> Facility 12, Customer 5
        # Based on CFLP.py: x[i, j].VarName = f"subproblem_{j}_x_{i}_{j}"
        self.re_assign = re.compile(r"subproblem_(\d+)_x_(\d+)_(\d+)")

    def parse_json(self, json_path):
        with open(json_path, 'r') as f:
            data = json.load(f)
        
        clusters = data.get("clusters", {})
        parsed_clusters = {}

        for cluster_id, var_names in clusters.items():
            facilities = set()
            customers = set()

            for name in var_names:
                # Check for Facility (y)
                m_fac = self.re_fac.search(name)
                if m_fac:
                    # Convert 1-based to 0-based
                    facilities.add(int(m_fac.group(1)) - 1)
                    continue

                # Check for Assignment (x)
                m_x = self.re_assign.search(name)
                if m_x:
                    # groups: (customer_label, facility_idx, customer_idx)
                    # All are 1-based in the file name
                    f_idx = int(m_x.group(2)) - 1
                    c_idx = int(m_x.group(3)) - 1
                    facilities.add(f_idx)
                    customers.add(c_idx)

            parsed_clusters[int(cluster_id)] = {
                "facilities": sorted(list(facilities)),
                "customers": sorted(list(customers))
            }
        
        return parsed_clusters
