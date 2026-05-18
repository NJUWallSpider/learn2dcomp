from CFLP import DataLoader
import sys

try:
    path = 'data/raw/facilities/scale_50_200/1.txt'
    loader = DataLoader(path)
    print(f"Total lines: {len(loader.lines)}")
    print(f"Line 0: {repr(loader.lines[0])}")
    print(f"Line 1: {repr(loader.lines[1])}")
    print(f"Line 2: {repr(loader.lines[2])}")
    print(f"Line 3: {repr(loader.lines[3])}")
    print(f"Line 4: {repr(loader.lines[4])}")

    n_fac, n_cust, fixed, cap = loader.read_metadata()
    print(f"Facilities: {n_fac}, Customers: {n_cust}")
    
    demands, costs = loader.read_data()
    print(f"Num Demands: {len(demands)}")
    print(f"Num Cost Entries: {len(costs)}")
    
    # Check Facility 55
    # Facility ID 55.
    if 55 in fixed:
        print(f"Facility 55 Fixed Cost: {fixed[55]}")
    else:
        print("Facility 55 not found in fixed costs")

    # Check Costs for Facility 55
    # Print first 5 costs for Fac 55
    count = 0
    zeros = 0
    for j in range(1, n_cust + 1):
        if (55, j) in costs:
            c = costs[55, j]
            if c == 0:
                zeros += 1
            if count < 5:
                print(f"Cost Fac 55 -> Cust {j}: {c}")
                count += 1
    print(f"Total Zero Costs for Fac 55: {zeros}")

except Exception as e:
    print(f"Error: {e}")