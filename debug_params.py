import gurobipy as gp
try:
    m = gp.Model()
    m.setParam("MIPGap", 0.1)
    print("MIPGap set successfully.")
except Exception as e:
    print(f"MIPGap failed: {e}")
