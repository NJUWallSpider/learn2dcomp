import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import HeteroConv, TransformerConv, Linear

class SupConLoss(nn.Module):
    """Supervised Contrastive Loss"""
    def __init__(self, temperature=0.07):
        super().__init__()
        self.temperature = temperature

    def forward(self, features, labels):
        # features: [batch_size, dim]
        # labels: [batch_size]
        
        device = features.device
        
        # Normalize features
        features = F.normalize(features, dim=1)
        
        # Similarity matrix
        sim_matrix = torch.matmul(features, features.T) / self.temperature
        
        # Mask for same class
        labels = labels.unsqueeze(1)
        mask = torch.eq(labels, labels.T).float().to(device)
        
        # Remove self-contrast
        logits_mask = torch.scatter(
            torch.ones_like(mask),
            1,
            torch.arange(mask.shape[0]).view(-1, 1).to(device),
            0
        )
        mask = mask * logits_mask
        
        # Compute Log-Exp
        exp_sim = torch.exp(sim_matrix) * logits_mask
        
        # Sum of exponentials
        # Add epsilon to avoid log(0) if row sum is 0 (shouldn't happen with logits_mask logic unless single sample)
        log_prob_denom = torch.log(exp_sim.sum(dim=1, keepdim=True) + 1e-9)
        
        log_prob = sim_matrix - log_prob_denom
        
        # Mean log-likelihood per positive pair
        # Avoid division by zero
        mask_sum = mask.sum(dim=1)
        
        # We only care about rows where there is at least one positive pair
        valid_indices = mask_sum > 0
        
        if valid_indices.sum() == 0:
            return torch.tensor(0.0, device=device, requires_grad=True)
            
        # loss = - (1 / |P(i)|) * sum_{p in P(i)} log(exp(sim(i,p)) / sum(...))
        mean_log_prob_pos = (mask * log_prob).sum(dim=1) / (mask_sum + 1e-9)
        
        loss = -mean_log_prob_pos[valid_indices].mean()
        return loss

class GraphTransformer(nn.Module):
    def __init__(self, hidden_dim=128, num_layers=2, num_heads=4, pe_dim=8):
        super().__init__()
        
        self.hidden_dim = hidden_dim
        
        # Input Encoders
        # Variable: 8 features + PE
        self.var_encoder = nn.Sequential(
            Linear(8 + pe_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.ReLU()
        )
        # Constraint: 6 features + PE
        self.con_encoder = nn.Sequential(
            Linear(6 + pe_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.ReLU()
        )
        
        self.layers = nn.ModuleList()
        for _ in range(num_layers):
            conv = HeteroConv({
                ('variable', 'connected_to', 'constraint'): TransformerConv(
                    hidden_dim, hidden_dim // num_heads, heads=num_heads, 
                    edge_dim=3, dropout=0.1
                ),
                ('constraint', 'rev_connected_to', 'variable'): TransformerConv(
                    hidden_dim, hidden_dim // num_heads, heads=num_heads, 
                    edge_dim=3, dropout=0.1
                )
            }, aggr='sum')
            self.layers.append(conv)
            
        self.projector = nn.Sequential(
            Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            Linear(hidden_dim, hidden_dim)
        )
        
    def forward(self, data):
        # Construct x_dict manually to include PE
        v_x = data['variable'].x
        v_pe = data['variable'].pe
        
        c_x = data['constraint'].x
        c_pe = data['constraint'].pe
        
        x_dict = {
            'variable': self.var_encoder(torch.cat([v_x, v_pe], dim=-1)),
            'constraint': self.con_encoder(torch.cat([c_x, c_pe], dim=-1))
        }
        
        edge_index_dict = data.edge_index_dict
        edge_attr_dict = data.edge_attr_dict
        
        for conv in self.layers:
            x_dict = conv(x_dict, edge_index_dict, edge_attr_dict=edge_attr_dict)
            x_dict = {key: F.relu(x) for key, x in x_dict.items()}
            
        out = self.projector(x_dict['variable'])
        return out
