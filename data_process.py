import torch
import numpy as np
import networkx as nx
from torch.utils.data import Dataset, DataLoader

def collate_fn_for_supcon(batch):
    """
    Custom collate function to handle label offsetting for supervised contrastive loss.
    The batching of graph data is handled by PyG's DataLoader.
    
    Logic:
    - Label 0 (Master): Preserved across batch (Global Class). All Master vars are pulled together.
    - Label > 0 (Subproblems): Offset per graph. Subproblem k of Graph i is distinct from Subproblem k of Graph j.
    """
    batched_graph = batch
    # Use variable labels
    labels = batched_graph['variable'].y
    
    # --- Label Offsetting ---
    
    running_offset = 0
    
    for i in range(batched_graph.num_graphs):
        # Mask for nodes belonging to graph i
        mask = (batched_graph['variable'].batch == i)
        
        if mask.any():
            # Get indices where mask is True
            graph_indices = torch.nonzero(mask, as_tuple=True)[0]
            
            # Get values to check > 0
            current_labels = labels[graph_indices]
            sub_mask = current_labels > 0
            
            if sub_mask.any():
                # Indices to update
                update_indices = graph_indices[sub_mask]
                
                # Update running offset
                max_sub_val = current_labels[sub_mask].max().item()
                
                # Apply offset to the tensor in-place
                labels[update_indices] += running_offset
                
                running_offset += max_sub_val
    
    batched_graph['variable'].y = labels
    return batched_graph

def add_laplacian_pe(data, k=8):
    """
    Computes Laplacian Positional Encodings for a HeteroData object (Bipartite Graph).
    Adds 'pe' attribute to 'variable' and 'constraint' nodes.
    """
    import scipy.sparse as sp
    import scipy.sparse.linalg as spla
    
    num_vars = data['variable'].num_nodes
    num_cons = data['constraint'].num_nodes
    num_nodes = num_vars + num_cons
    
    # Build Adjacency Matrix
    # Edges: variable -> constraint
    edge_index = data['variable', 'connected_to', 'constraint'].edge_index
    row = edge_index[0].numpy()
    col = edge_index[1].numpy() + num_vars
    
    # Undirected: add (v->c) and (c->v)
    data_ones = np.ones(len(row))
    adj = sp.coo_matrix((data_ones, (row, col)), shape=(num_nodes, num_nodes))
    adj = adj + adj.T
    
    # Normalized Laplacian: L = I - D^-1/2 A D^-1/2
    deg = np.array(adj.sum(axis=1)).flatten()
    with np.errstate(divide='ignore'):
        deg_inv_sqrt = np.power(deg, -0.5)
    deg_inv_sqrt[np.isinf(deg_inv_sqrt)] = 0.0
    
    D_inv_sqrt = sp.diags(deg_inv_sqrt)
    L = sp.eye(num_nodes) - D_inv_sqrt @ adj @ D_inv_sqrt
    
    # Eigen decomposition
    # Smallest k+1 eigenvectors (first is trivial const)
    # Use eigsh
    try:
        eig_vals, eig_vecs = spla.eigsh(L, k=k+1, which='SM')
    except Exception:
        # Fallback for small graphs or convergence issues; pad with zeros
        eig_vals = np.zeros(k + 1)
        eig_vecs = np.zeros((num_nodes, k + 1))

    # Sort just in case (eigsh usually sorts, but 'SM' magnitude...)
    idx = eig_vals.argsort()
    eig_vecs = eig_vecs[:, idx]
    
    # Remove first trivial eigenvector (associated with eigenvalue 0)
    pe = eig_vecs[:, 1:k+1]
    
    # If we didn't get enough vectors (e.g. graph too small), pad
    if pe.shape[1] < k:
        pad_size = k - pe.shape[1]
        pe = np.pad(pe, ((0,0), (0, pad_size)), mode='constant')
        
    pe = torch.tensor(pe, dtype=torch.float)
    
    # Assign back
    data['variable'].pe = pe[:num_vars]
    data['constraint'].pe = pe[num_vars:]
    
    return data

def add_block_pe(data, k=8):
    """
    Compute Block-Structure Positional Encoding via Louvain community detection
    on the bipartite constraint-variable graph.
    """
    import numpy as np
    from networkx.algorithms.community import louvain_communities

    num_vars = data['variable'].num_nodes
    num_cons = data['constraint'].num_nodes
    num_nodes = num_vars + num_cons

    edge_index = data['variable', 'connected_to', 'constraint'].edge_index

    # Build NetworkX bipartite graph
    G = nx.Graph()
    G.add_nodes_from(range(num_vars), bipartite=0)
    G.add_nodes_from(range(num_vars, num_nodes), bipartite=1)
    edges = [(int(edge_index[0, i]), int(edge_index[1, i] + num_vars))
             for i in range(edge_index.shape[1])]
    G.add_edges_from(edges)

    # Louvain community detection
    try:
        communities = louvain_communities(G, seed=42)
    except Exception:
        communities = [{i} for i in range(num_nodes)]

    comm_id = np.zeros(num_nodes, dtype=np.int64)
    for cid, comm in enumerate(communities):
        for node in comm:
            comm_id[node] = cid

    n_communities = len(communities)
    comm_sizes = np.array([len(c) for c in communities])
    comm_size_ratio = comm_sizes / num_nodes

    # Boundary detection
    is_boundary = np.zeros(num_nodes, dtype=np.float32)
    for i in range(edge_index.shape[1]):
        v = int(edge_index[0, i])
        c = int(edge_index[1, i]) + num_vars
        if comm_id[v] != comm_id[c]:
            is_boundary[v] = 1.0
            is_boundary[c] = 1.0

    # Build PE matrix [num_nodes, k]
    pe = np.zeros((num_nodes, k), dtype=np.float32)
    for node in range(num_nodes):
        cid = comm_id[node]
        pe[node, 0] = comm_size_ratio[cid]
        pe[node, 1] = is_boundary[node]
        if k > 2:
            for d in range(2, k):
                if d % 2 == 0:
                    pe[node, d] = np.sin(cid / (10000 ** ((d - 2) / max(k - 2, 1))))
                else:
                    pe[node, d] = np.cos(cid / (10000 ** ((d - 3) / max(k - 2, 1))))

    pe = torch.tensor(pe, dtype=torch.float)
    data['variable'].block_pe = pe[:num_vars]
    data['constraint'].block_pe = pe[num_vars:]
    return data


class MILPDataset(torch.utils.data.Dataset):
    """A simple dataset class for loading .pt files."""
    def __init__(self, sample_files, transform=None):
        self.sample_files = sample_files
        self.transform = transform

    def __len__(self):
        return len(self.sample_files)

    def __getitem__(self, idx):
        # Return both the data and the filepath for use in the evaluation loop
        data = torch.load(self.sample_files[idx], weights_only=False)
        if self.transform:
            data = self.transform(data)
        return data

def simple_collate(batch):
    """
    A simple collate function for use when batch_size is 1.
    """
    assert len(batch) == 1, "This collate function is designed for batch_size=1 only."
    return batch[0]
