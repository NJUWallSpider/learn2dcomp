# 生成算例原始格式的数据，储存在data/raw中
# 使用方法：python 01_generate_instance.py [problem]（现在只有facilities）
import os
import argparse
import numpy as np
import utilities
import shutil
import config

def generate_capacited_facility_location(rng, filename, n_facilities, n_customers, ratio=5, keep_ratio=1.0, perturbation=0.0):
    """
    Generate a Capacited Facility Location problem following
        Cornuejols G, Sridharan R, Thizy J-M (1991)
        A Comparison of Heuristics and Relaxations for the Capacitated Plant Location Problem.
        European Journal of Operations Research 50:280-297.

    Saves it as a CPLEX LP file.

    Parameters
    ----------
    random : numpy.random.RandomState
        A random number generator.
    filename : str
        Path to the file to save.
    n_customers: int
        The desired number of customers.
    n_facilities: int
        The desired number of facilities.
    ratio: float
        The desired capacity / demand ratio.
    keep_ratio: float
        The ratio of nearest facilities to keep for each customer (between 0 and 1).
    perturbation : float, optional
        A factor to perturb the number of facilities and customers. Each dimension `d`
        will be randomly chosen from the range `[d * (1 - p), d * (1 + p)]`.
        Defaults to 0.0 (no perturbation).
    """
    # Apply perturbation to n_facilities and n_customers
    if perturbation > 0:
        n_facilities_min = max(1, int(n_facilities * (1 - perturbation)))
        n_facilities_max = int(n_facilities * (1 + perturbation))
        n_facilities = rng.integers(n_facilities_min, n_facilities_max + 1)

        n_customers_min = max(1, int(n_customers * (1 - perturbation)))
        n_customers_max = int(n_customers * (1 + perturbation))
        n_customers = rng.integers(n_customers_min, n_customers_max + 1)

    c_x = rng.random(n_customers)
    c_y = rng.random(n_customers)

    f_x = rng.random(n_facilities)
    f_y = rng.random(n_facilities)

    demands = rng.integers(5, 35+1, size=n_customers)
    capacities = rng.integers(10, 160+1, size=n_facilities)
    fixed_costs = rng.integers(100, 110+1, size=n_facilities) * np.sqrt(capacities) \
            + rng.integers(90+1, size=n_facilities)
    fixed_costs = fixed_costs.astype(int)

    total_demand = demands.sum()
    total_capacity = capacities.sum()

    # adjust capacities according to ratio
    capacities = capacities * ratio * total_demand / total_capacity
    capacities = capacities.astype(int)
    total_capacity = capacities.sum()

    # transportation costs
    trans_costs = np.sqrt(
            (c_x.reshape((-1, 1)) - f_x.reshape((1, -1))) ** 2 \
            + (c_y.reshape((-1, 1)) - f_y.reshape((1, -1))) ** 2) * 10 * demands.reshape((-1, 1))
    
    trans_costs = trans_costs.T

    # For each customer, only allow the nearest `keep_ratio` percent of facilities
    if keep_ratio < 1.0:
        num_to_keep = max(1, int(n_facilities * keep_ratio))
        # A large number to represent infinite cost for disallowed connections
        large_cost = 1e9 

        # Find the indices of the facilities to discard for each customer
        indices_to_discard = np.argsort(trans_costs, axis=0)[num_to_keep:, :]
        
        # Use advanced indexing to set costs to a large value
        np.put_along_axis(trans_costs, indices_to_discard, large_cost, axis=0)

    # 8. Write the complete problem to the file.
    with open(filename, 'w') as file:
        file.write("\nCode\n")
        file.write("Facilities\tCustomers\n")
        file.write(f"{n_facilities}\t{n_customers}\n")
        file.write("Fixed Cost\tCapacity\n")
        for i in range(n_facilities):
            file.write(f"{fixed_costs[i]}\t{capacities[i]}\n")
        
        file.write("Demand & Transportation Cost\n")
        for j in range(n_customers):
            file.write(f"{j}\t{demands[j]}\n")
            for i in range(n_facilities):
                file.write(f"{trans_costs[i, j]}\t")
            file.write("\n")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'problem',
        help='MILP instance type to process.',
        choices=['facilities', 'osif', 'bpp'],
    )
    parser.add_argument(
        '-s', '--seed',
        help='Random generator seed (default 0).',
        type=utilities.valid_seed,
        default=0,
    )
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)

    # 从配置文件加载实例生成参数
    generation_specs = config.INSTANCE_GEN.get(args.problem, {})
    base_dir = config.RAW_DATA_DIR / args.problem

    print(f"Generating instances for problem: {args.problem}")

    for name, specs in generation_specs.items():
        
        n_instances = specs['n_instances']
        if n_instances == 0:
            continue

        dir_name = name

        lp_dir = base_dir / dir_name

        print(f"{n_instances} instances in {lp_dir}")

        if not specs.get('overwrite', False) and lp_dir.exists():
            print(f"  skipping, directory already exists and overwrite is False.")
            continue

        if lp_dir.exists():
            shutil.rmtree(lp_dir)
        os.makedirs(lp_dir, exist_ok=True)

        for i in range(n_instances):
            print(f"  generating instance {i+1}/{n_instances}...")
            if args.problem == 'facilities':
                filename = lp_dir / f'{i+1}.txt'
                generate_capacited_facility_location(rng, str(filename), specs['num_facilities'], specs['num_customers'], ratio=specs['ratio'], keep_ratio=specs.get('keep_ratio', 1.0), perturbation=specs.get('perturbation', 0.0))
    print("done.")
