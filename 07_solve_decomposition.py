import gurobipy as gp
from gurobipy import GRB
import json
import os
import argparse
from pathlib import Path
import networkx as nx
import time
import pandas as pd
import config
from generic_benders import GenericBenders

class DecompositionBenders(GenericBenders):
    def __init__(self, mps_file, json_file):
        self.mps_file = mps_file
        self.json_file = json_file
        self.original_model = None
        
        # Pre-process to understand structure
        self._preprocess()
        
        # Initialize GenericBenders
        # Probabilities = [1.0, 1.0, ...] so that Objective = Master + sum(Sub_i)
        # We treat each component as an independent subproblem that contributes to the total cost.
        probs = [1.0] * self.num_components
        
        # eta_lb can be 0.0 assuming non-negative costs in subproblems
        super().__init__(n_scenarios=self.num_components, probabilities=probs, name="DecompBenders", eta_lb=0.0)

    def _preprocess(self):
        print(f"Loading original model from {self.mps_file}...")
        self.original_model = gp.read(str(self.mps_file))
        
        with open(self.json_file, 'r') as f:
            decomp_data = json.load(f)
            
        pred_master_names = set(decomp_data.get("master_problem", []))
        all_vars = self.original_model.getVars()
        self.name_to_var = {v.VarName: v for v in all_vars}
        
        # Graph Analysis for Subproblems
        # Identify variables that are NOT predicted to be in the master
        sub_candidates = [v for v in all_vars if v.VarName not in pred_master_names]
        G = nx.Graph()
        for v in sub_candidates: G.add_node(v.VarName)
        
        # Build graph edges based on shared constraints
        for constr in self.original_model.getConstrs():
            row = self.original_model.getRow(constr)
            row_sub_vars = []
            for i in range(row.size()):
                v = row.getVar(i)
                if v.VarName in G:
                    row_sub_vars.append(v.VarName)
            
            # Connect all subproblem variables in the same constraint (clique)
            if len(row_sub_vars) > 1:
                base = row_sub_vars[0]
                for other in row_sub_vars[1:]:
                    G.add_edge(base, other)
                    
        self.components = list(nx.connected_components(G))
        self.num_components = len(self.components)
        print(f"Identified {self.num_components} subproblem components.")
        
        # Map var -> component index
        self.var_to_comp = {}
        for i, comp in enumerate(self.components):
            for name in comp:
                self.var_to_comp[name] = i
                
        # Identify Real Master Variables (pred_master + orphans)
        self.master_var_names = []
        for v in all_vars:
            if v.VarName not in self.var_to_comp:
                self.master_var_names.append(v.VarName)
                
        # Store constraints data for build steps
        self.master_constrs_data = [] 
        self.sub_constrs_data = [[] for _ in range(self.num_components)] 
        
        for constr in self.original_model.getConstrs():
            row = self.original_model.getRow(constr)
            
            # Analyze involvement
            involved_comps = set()
            master_terms = {} # var_name -> coeff
            sub_terms = {} # comp_idx -> {var_name -> coeff}
            
            for i in range(row.size()):
                v = row.getVar(i)
                coeff = row.getCoeff(i)
                if v.VarName in self.master_var_names:
                    master_terms[v.VarName] = master_terms.get(v.VarName, 0) + coeff
                elif v.VarName in self.var_to_comp:
                    c_idx = self.var_to_comp[v.VarName]
                    involved_comps.add(c_idx)
                    if c_idx not in sub_terms: sub_terms[c_idx] = {}
                    sub_terms[c_idx][v.VarName] = sub_terms[c_idx].get(v.VarName, 0) + coeff
            
            data = {
                'sense': constr.Sense,
                'rhs': constr.RHS,
                'name': constr.ConstrName,
                'master_terms': master_terms,
                'sub_terms': sub_terms 
            }
            
            if len(involved_comps) == 0:
                self.master_constrs_data.append(data)
            elif len(involved_comps) == 1:
                c_idx = list(involved_comps)[0]
                self.sub_constrs_data[c_idx].append(data)
            else:
                print(f"Warning: Constraint {constr.ConstrName} links multiple subproblems: {involved_comps}. This breaks Benders structure.")

    def _add_constr(self, model, lhs, sense, rhs, name):
        """Helper to add constraints compatible with different Gurobi APIs"""
        if sense == GRB.LESS_EQUAL or sense == '<':
            return model.addConstr(lhs <= rhs, name=name)
        elif sense == GRB.GREATER_EQUAL or sense == '>':
            return model.addConstr(lhs >= rhs, name=name)
        elif sense == GRB.EQUAL or sense == '=':
            return model.addConstr(lhs == rhs, name=name)
        else:
            return model.addConstr(lhs, sense, rhs, name=name)

    def build_master(self, model):
        master_vars = {}
        # Add variables
        for name in self.master_var_names:
            orig_v = self.name_to_var[name]
            v = model.addVar(
                lb=orig_v.LB, ub=orig_v.UB, obj=0.0, # Obj added in get_master_cost
                vtype=orig_v.VType, name=name
            )
            master_vars[name] = v
            
        # Add pure master constraints
        for data in self.master_constrs_data:
            lhs = gp.LinExpr()
            for name, coeff in data['master_terms'].items():
                lhs.add(master_vars[name], coeff)
            self._add_constr(model, lhs, data['sense'], data['rhs'], data['name'])
            
        return master_vars

    def get_master_cost(self, master_vars):
        cost = gp.LinExpr()
        for name, var in master_vars.items():
            orig_obj = self.name_to_var[name].Obj
            if orig_obj != 0:
                cost.add(var, orig_obj)
        return cost

    def build_subproblem(self, model, scenario_id):
        comp_vars = self.components[scenario_id]
        local_vars = {}
        
        # Add Vars
        for name in comp_vars:
            orig_v = self.name_to_var[name]
            # Force Continuous for Benders subproblems (L-shaped method requires duals)
            v = model.addVar(
                lb=orig_v.LB, ub=orig_v.UB, obj=orig_v.Obj, 
                vtype=GRB.CONTINUOUS, name=name
            )
            local_vars[name] = v
            
        # Add Constraints
        model._linking_constrs = [] 
        
        for data in self.sub_constrs_data[scenario_id]:
            lhs = gp.LinExpr()
            # Add local terms
            for name, coeff in data['sub_terms'][scenario_id].items():
                lhs.add(local_vars[name], coeff)
                
            constr = self._add_constr(model, lhs, data['sense'], data['rhs'], data['name'])
            
            # If it has master terms, it's a linking constraint
            if data['master_terms']:
                model._linking_constrs.append({
                    'constr': constr,
                    'master_terms': data['master_terms'],
                    'orig_rhs': data['rhs']
                })

    def get_linking_map(self, sub_model, scenario_id, master_vars):
        link_map = {}
        # If no linking constraints, return empty
        if not hasattr(sub_model, '_linking_constrs'):
            return link_map
            
        for item in sub_model._linking_constrs:
            constr = item['constr']
            orig_rhs = item['orig_rhs']
            master_terms = item['master_terms']
            
            # RHS = Orig_RHS - sum(coeff * master_var)
            # We construct this expression to pass to GenericBenders
            rhs_expr = gp.LinExpr(orig_rhs)
            for name, coeff in master_terms.items():
                rhs_expr.add(master_vars[name], -coeff)
                
            link_map[constr] = rhs_expr
            
        return link_map

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mps_dir', type=str, default="data/mps/facilities/test")         
    parser.add_argument('--json_dir', type=str, default="results/decomposition_output")
    parser.add_argument('--output_csv', type=str, default="results/benders_results.csv")
    args = parser.parse_args()

    # Defaults
    mps_dir = Path(args.mps_dir) if args.mps_dir else config.MPS_DATA_DIR / "facilities" / "test"
    json_dir = Path(args.json_dir) if args.json_dir else config.RESULTS_DIR / "decomposition_output"
    
    if not mps_dir.exists():
        print(f"Error: MPS directory not found: {mps_dir}")
        return
        
    results = []
    mps_files = sorted(list(mps_dir.glob("*.mps")))
    
    if not mps_files:
        print(f"Warning: No .mps files found in {mps_dir}")

    for mps_file in mps_files:
        instance = mps_file.stem
        json_file = json_dir / f"{instance}_decomposition.json"
        
        if not json_file.exists():
            print(f"Warning: Decomposition file not found for {instance}, skipping.")
            continue
            
        print(f"Solving {instance}...")
        
        try:
            pre_solve_start = time.time()
            solver = DecompositionBenders(mps_file, json_file)
            pre_solve_end = time.time()
            
            solve_start = time.time()
            solver.solve()
            solve_end = time.time()
            
            pre_solve_time = pre_solve_end - pre_solve_start
            solve_time = solve_end - solve_start
            
            res = {
                "Instance": instance,
                "Status": solver.master.Status,
                "ObjVal": solver.master.ObjVal if solver.master.Status == GRB.OPTIMAL else None,
                "PreSolveTime": pre_solve_time,
                "SolveTime": solve_time,
                "NumSubproblems": solver.num_components
            }
            print(f"  Result: {res}")
            results.append(res)
            
        except Exception as e:
            print(f"Error: Failed to solve {instance}: {e}")
            import traceback
            traceback.print_exc()
        
        
    if results:
        # Ensure directory exists
        Path(args.output_csv).parent.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame(results)
        df.to_csv(args.output_csv, index=False)
        print(f"Results saved to {args.output_csv}")
        
        print("\n--- Timing Statistics ---")
        if len(df) > 1:
            print(f"Pre-solve Time: Mean = {df['PreSolveTime'].mean():.4f} s, Std = {df['PreSolveTime'].std():.4f} s")
            print(f"Solve Time:     Mean = {df['SolveTime'].mean():.4f} s, Std = {df['SolveTime'].std():.4f} s")
        else:
            print(f"Pre-solve Time: Mean = {df['PreSolveTime'].mean():.4f} s")
            print(f"Solve Time:     Mean = {df['SolveTime'].mean():.4f} s")
    else:
        print("No results to save.")

if __name__ == "__main__":
    main()