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
        log_prob_denom = torch.log(exp_sim.sum(dim=1, keepdim=True) + 1e-9)

        log_prob = sim_matrix - log_prob_denom

        # Mean log-likelihood per positive pair
        mask_sum = mask.sum(dim=1)

        valid_indices = mask_sum > 0

        if valid_indices.sum() == 0:
            return torch.tensor(0.0, device=device, requires_grad=True)

        mean_log_prob_pos = (mask * log_prob).sum(dim=1) / (mask_sum + 1e-9)

        loss = -mean_log_prob_pos[valid_indices].mean()
        return loss


class EnhancedSupConLoss(SupConLoss):
    """SupConLoss with boundary variable weighting.

    Boundary vars (co-constrained by multiple blocks) get loss × boundary_weight.
    """
    def __init__(self, temperature=0.3, boundary_weight=2.0):
        super().__init__(temperature=temperature)
        self.boundary_weight = boundary_weight

    def _detect_boundary_vars(self, edge_index, labels, num_vars, num_cons):
        device = edge_index.device
        vi = edge_index[0].long()
        ci = edge_index[1].long()
        adj = torch.sparse_coo_tensor(
            torch.stack([vi, ci]),
            torch.ones(vi.shape[0], device=device),
            (num_vars, num_cons),
        ).coalesce()
        co_var = torch.sparse.mm(adj, adj.t()).coalesce()
        row, col = co_var.indices()
        neighbor_labels = labels[col]
        sorted_idx = row.argsort()
        sr = row[sorted_idx]
        snl = neighbor_labels[sorted_idx]
        rd = torch.cat([torch.tensor([1], device=device),
                        (sr[1:] != sr[:-1]).int()])
        row_starts = rd.nonzero().squeeze(-1)
        is_boundary = torch.zeros(num_vars, dtype=torch.bool, device=device)
        for i in range(len(row_starts)):
            r = sr[row_starts[i]]
            end = row_starts[i + 1] if i + 1 < len(row_starts) else len(sr)
            seg = snl[row_starts[i]:end]
            valid = seg >= 0
            if valid.sum() > 0 and seg[valid].unique().numel() > 1:
                is_boundary[r] = True
        return is_boundary

    def forward(self, features, labels, batch_idx, edge_index=None,
                num_vars=None, num_cons=None):
        device = features.device
        features = F.normalize(features, dim=1)
        if edge_index is not None and num_vars is not None and num_cons is not None:
            is_boundary = self._detect_boundary_vars(edge_index, labels, num_vars, num_cons)
        else:
            is_boundary = torch.zeros(labels.shape[0], dtype=torch.bool, device=device)
        total_loss = 0.0
        count = 0
        for g in batch_idx.unique():
            g_mask = batch_idx == g
            f = features[g_mask]
            l = labels[g_mask]
            b = is_boundary[g_mask]
            if f.shape[0] < 2:
                continue
            sim = torch.matmul(f, f.T) / self.temperature
            label_eq = torch.eq(l.unsqueeze(1), l.unsqueeze(0)).float()
            diag_mask = 1.0 - torch.eye(f.shape[0], device=device)
            pos_mask = label_eq * diag_mask
            exp_sim = torch.exp(sim) * diag_mask
            denom = exp_sim.sum(dim=1, keepdim=True).clamp(min=1e-9)
            log_prob = sim - torch.log(denom)
            pos_sum = pos_mask.sum(dim=1)
            valid = pos_sum > 0
            if not valid.any():
                continue
            mean_pos = (pos_mask * log_prob).sum(dim=1)[valid] / pos_sum[valid].clamp(min=1e-9)
            per_sample = -mean_pos
            weights = torch.where(b[valid], self.boundary_weight, torch.tensor(1.0, device=device))
            total_loss += (per_sample * weights).mean()
            count += 1
        if count == 0:
            return torch.tensor(0.0, device=device, requires_grad=True)
        return total_loss / count


class GraphTransformer(nn.Module):
    def __init__(self, hidden_dim=128, num_layers=2, num_heads=4, pe_dim=8,
                 block_pe_dim=8, max_con_blocks=128):
        super().__init__()

        self.hidden_dim = hidden_dim
        self.pe_dim = pe_dim
        self.block_pe_dim = block_pe_dim

        # Input Encoders (24 var + PE + BlockPE / 18 con + PE + BlockPE)
        var_in = 24 + pe_dim + block_pe_dim
        con_in = 18 + pe_dim + block_pe_dim
        self.var_encoder = nn.Sequential(
            Linear(var_in, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.ReLU()
        )
        self.con_encoder = nn.Sequential(
            Linear(con_in, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.ReLU()
        )

        self.layers = nn.ModuleList()
        for _ in range(num_layers):
            conv = HeteroConv({
                ('variable', 'connected_to', 'constraint'): TransformerConv(
                    hidden_dim, hidden_dim // num_heads, heads=num_heads,
                    edge_dim=6, dropout=0.1
                ),
                ('constraint', 'rev_connected_to', 'variable'): TransformerConv(
                    hidden_dim, hidden_dim // num_heads, heads=num_heads,
                    edge_dim=6, dropout=0.1
                )
            }, aggr='sum')
            self.layers.append(conv)

        # Variable projection head (for SupCon)
        self.var_projector = nn.Sequential(
            Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            Linear(hidden_dim, hidden_dim)
        )

        # Constraint projection head (for auxiliary tasks)
        self.con_projector = nn.Sequential(
            Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            Linear(hidden_dim, hidden_dim)
        )

        # Constraint block classifier: predicts which block a constraint belongs to
        # Class 0 = master block, Class 1..K = subproblem blocks
        self.con_block_classifier = nn.Linear(hidden_dim, max_con_blocks)

        # Constraint linking classifier: binary — is this a linking constraint?
        self.con_linking_classifier = nn.Linear(hidden_dim, 1)

    def forward(self, data):
        # Construct x_dict manually to include PE + BlockPE
        v_x = data['variable'].x
        v_pe = data['variable'].pe
        v_bpe = data['variable'].block_pe if hasattr(data['variable'], 'block_pe') else torch.zeros(v_x.shape[0], self.block_pe_dim, device=v_x.device)

        c_x = data['constraint'].x
        c_pe = data['constraint'].pe
        c_bpe = data['constraint'].block_pe if hasattr(data['constraint'], 'block_pe') else torch.zeros(c_x.shape[0], self.block_pe_dim, device=c_x.device)

        x_dict = {
            'variable': self.var_encoder(torch.cat([v_x, v_pe, v_bpe], dim=-1)),
            'constraint': self.con_encoder(torch.cat([c_x, c_pe, c_bpe], dim=-1))
        }

        edge_index_dict = data.edge_index_dict
        edge_attr_dict = data.edge_attr_dict

        for conv in self.layers:
            x_dict = conv(x_dict, edge_index_dict, edge_attr_dict=edge_attr_dict)
            x_dict = {key: F.relu(x) for key, x in x_dict.items()}

        var_emb = self.var_projector(x_dict['variable'])
        con_emb = self.con_projector(x_dict['constraint'])
        con_block_logits = self.con_block_classifier(con_emb)
        con_linking_logits = self.con_linking_classifier(con_emb)

        return var_emb, con_emb, con_block_logits, con_linking_logits
