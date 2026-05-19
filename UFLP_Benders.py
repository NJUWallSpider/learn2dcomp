import gurobipy as gp
from gurobipy import GRB
from generic_benders import GenericBenders
from CFLP import DataLoader
import os

class UFLPBenders(GenericBenders):
    def __init__(self, n_facilities, n_customers, fixed_costs, transport_costs):
        probs = [1.0] * n_customers
        super().__init__(n_scenarios=n_customers, probabilities=probs, name="UFLP", eta_lb=0.0)
        
        self.n_facilities = n_facilities
        self.n_customers = n_customers
        self.fixed_costs = fixed_costs
        self.transport_costs = transport_costs # dict (i, j) -> cost
        
        # Map: scenario_id -> {facility_id: constraint}
        self.sub_constrs = {}

    def build_master(self, model):
        # Variables y_i: Open facility i
        facilities = range(1, self.n_facilities + 1)
        y = model.addVars(facilities, vtype=GRB.BINARY, name="y")
        return y

    def get_master_cost(self, master_vars):
        # Cost = sum(fixed_cost * y)
        cost_expr = gp.LinExpr()
        for i in range(1, self.n_facilities + 1):
            cost_expr += self.fixed_costs[i] * master_vars[i]
        return cost_expr

    def build_subproblem(self, model, scenario_id):
        # Scenario ID is 0-based index of customer. 
        # Customer ID in data is 1-based: scenario_id + 1
        customer_id = scenario_id + 1
        facilities = range(1, self.n_facilities + 1)
        
        # Variables x_i: fraction of customer demand served by facility i
        x = model.addVars(facilities, lb=0.0, ub=1.0, name="x")
        
        # Objective: sum(c_ij * x_i)
        obj = gp.LinExpr()
        # Use a safer Big-M value to avoid numerical instability
        BIG_M = 1e4
        for i in facilities:
            # transport_costs key is (facility, customer)
            cost = self.transport_costs.get((i, customer_id), BIG_M) 
            obj += cost * x[i]
        model.setObjective(obj, GRB.MINIMIZE)
        
        # Constraint 1: Demand satisfaction sum(x_i) == 1
        model.addConstr(x.sum() == 1, name="Demand")
        
        # Constraint 2: Linking x_i <= y_i
        # Initial RHS is 0.0 (will be updated via linking map)
        model._link_constrs = {}
        for i in facilities:
            c = model.addConstr(x[i] <= 0.0, name=f"Link_{i}")
            model._link_constrs[i] = c
            
    def get_linking_map(self, sub_model, scenario_id, master_vars):
        link_map = {}
        facilities = range(1, self.n_facilities + 1)
        
        for i in facilities:
            constr = sub_model._link_constrs[i]
            rhs_expr = master_vars[i]
            link_map[constr] = rhs_expr
            
        return link_map

if __name__ == "__main__":
    base_dir = 'data/raw/facilities/scale_50_200'
    if os.path.exists(base_dir):
        files = sorted(os.listdir(base_dir))
        data_path = os.path.join(base_dir, files[0])
        print(f"Using data file: {data_path}")
    
    if os.path.exists(data_path):
        loader = DataLoader(data_path)
        n_fac, n_cust, fixed_costs, caps = loader.read_metadata()
        demands, trans_costs = loader.read_data()
        
        benders = UFLPBenders(n_fac, n_cust, fixed_costs, trans_costs)
        benders.solve()
        
        status = benders.master.Status
        if status == GRB.OPTIMAL:
            print("\nOptimal Solution Found:")
            print(f"Objective Value: {benders.master.ObjVal}")
            
            # Print open facilities
            y_vals = []
            master_vars = benders.master_vars
            # master_vars is a tupledict from addVars, indexed by facility id
            for i in range(1, n_fac + 1):
                if master_vars[i].X > 0.5:
                    y_vals.append(i)
            print(f"Open Facilities: {y_vals}")
        else:
            print(f"\nOptimization ended with status: {status}")
            if status == GRB.UNBOUNDED:
                print("Model is Unbounded. Check constraints/bounds.")
            elif status == GRB.INFEASIBLE:
                print("Model is Infeasible.")
    else:
        print("Data file not found.")