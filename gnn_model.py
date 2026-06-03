import torch
import torch.nn as nn
import torch.nn.functional as F
from torch_geometric.nn import HeteroConv, TransformerConv, Linear


class SupConLoss(nn.Module):
    """Supervised Contrastive Loss — per-instance within a batched graph."""
    def __init__(self, temperature=0.3):
        super().__init__()
        self.temperature = temperature

    def forward(self, features, labels, batch_idx):
        """
        features: [N, dim] — all variable node embeddings in the batch
        labels:   [N]      — decomposition labels (offset already applied)
        batch_idx:[N]      — graph index for each variable
        """
        device = features.device
        features = F.normalize(features, dim=1)
        total_loss = 0.0
        count = 0

        for g in batch_idx.unique():
            g_mask = batch_idx == g
            f = features[g_mask]
            l = labels[g_mask]

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

            mean_pos_log_prob = (pos_mask * log_prob).sum(dim=1)[valid] / pos_sum[valid].clamp(min=1e-9)
            total_loss += -mean_pos_log_prob.mean()
            count += 1

        if count == 0:
            return torch.tensor(0.0, device=device, requires_grad=True)
        return total_loss / count


class EnhancedSupConLoss(SupConLoss):
    """SupConLoss with boundary variable weighting (T-004).

    Detects variables on block boundaries via 2-hop label diversity:
    a variable is "boundary" if its co-constrained variables have >1 distinct label.
    Boundary variables get loss multiplied by `boundary_weight`.
    """
    def __init__(self, temperature=0.3, boundary_weight=2.0):
        super().__init__(temperature=temperature)
        self.boundary_weight = boundary_weight

    def _detect_boundary_vars(self, edge_index, labels, num_vars, num_cons):
        device = edge_index.device
        var_idx = edge_index[0].long()
        con_idx = edge_index[1].long()

        adj = torch.sparse_coo_tensor(
            torch.stack([var_idx, con_idx]),
            torch.ones(var_idx.shape[0], device=device),
            (num_vars, num_cons),
        ).coalesce()

        co_var = torch.sparse.mm(adj, adj.t()).coalesce()
        row, col = co_var.indices()
        neighbor_labels = labels[col]

        # Sort by row for efficient segmentation
        sorted_idx = row.argsort()
        sorted_rows = row[sorted_idx]
        sorted_nl = neighbor_labels[sorted_idx]

        row_diff = (sorted_rows[1:] != sorted_rows[:-1]).int()
        row_diff = torch.cat([torch.tensor([1], device=device), row_diff])
        row_starts = row_diff.nonzero().squeeze(-1)

        is_boundary = torch.zeros(num_vars, dtype=torch.bool, device=device)
        for i in range(len(row_starts)):
            r = sorted_rows[row_starts[i]]
            end = row_starts[i + 1] if i + 1 < len(row_starts) else len(sorted_rows)
            seg = sorted_nl[row_starts[i]:end]
            valid = seg >= 0
            if valid.sum() > 0 and seg[valid].unique().numel() > 1:
                is_boundary[r] = True

        return is_boundary

    def forward(self, features, labels, batch_idx, edge_index=None,
                num_vars=None, num_cons=None):
        device = features.device
        features = F.normalize(features, dim=1)

        if edge_index is not None and num_vars is not None and num_cons is not None:
            is_boundary = self._detect_boundary_vars(
                edge_index, labels, num_vars, num_cons)
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

            mean_pos_log_prob = (pos_mask * log_prob).sum(dim=1)[valid] / pos_sum[valid].clamp(min=1e-9)
            per_sample_loss = -mean_pos_log_prob

            weights = torch.where(b[valid], self.boundary_weight, 1.0)
            weighted_loss = per_sample_loss * weights
            total_loss += weighted_loss.mean()
            count += 1

        if count == 0:
            return torch.tensor(0.0, device=device, requires_grad=True)
        return total_loss / count


class GatedFusion(nn.Module):
    """Learnable gated fusion: α * h_het + (1-α) * h_hom."""
    def __init__(self, hidden_dim):
        super().__init__()
        self.gate = nn.Sequential(
            Linear(hidden_dim * 2, hidden_dim),
            nn.Sigmoid(),
        )

    def forward(self, h_het, h_hom):
        alpha = self.gate(torch.cat([h_het, h_hom], dim=-1))
        return alpha * h_het + (1 - alpha) * h_hom


class GraphTransformer(nn.Module):
    def __init__(self, hidden_dim=128, num_layers=3, num_heads=4, pe_dim=8, block_pe_dim=8,
                 homophilic_conv_layers=0, homophilic_conv_heads=4):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        self.use_homophilic = homophilic_conv_layers > 0
        self.block_pe_dim = block_pe_dim

        var_in_dim = 24 + pe_dim + block_pe_dim
        con_in_dim = 18 + pe_dim + block_pe_dim

        self.var_encoder = nn.Sequential(
            Linear(var_in_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.ReLU(),
        )
        self.con_encoder = nn.Sequential(
            Linear(con_in_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.ReLU(),
        )

        # --- Heterophilic channel (var↔con) ---
        self.layers = nn.ModuleList()
        self.norms_var = nn.ModuleList()
        self.norms_con = nn.ModuleList()

        for _ in range(num_layers):
            conv = HeteroConv(
                {
                    ('variable', 'connected_to', 'constraint'): TransformerConv(
                        hidden_dim, hidden_dim // num_heads, heads=num_heads,
                        edge_dim=6, dropout=0.1,
                    ),
                    ('constraint', 'rev_connected_to', 'variable'): TransformerConv(
                        hidden_dim, hidden_dim // num_heads, heads=num_heads,
                        edge_dim=6, dropout=0.1,
                    ),
                },
                aggr='sum',
            )
            self.layers.append(conv)
            self.norms_var.append(nn.LayerNorm(hidden_dim))
            self.norms_con.append(nn.LayerNorm(hidden_dim))

        # --- Homophilic channel (var↔var, con↔con) ---
        if self.use_homophilic:
            self.hom_layers = nn.ModuleList()
            self.hom_norms_var = nn.ModuleList()
            self.hom_norms_con = nn.ModuleList()

            for _ in range(homophilic_conv_layers):
                conv = HeteroConv(
                    {
                        ('variable', 'shares_constraint_with', 'variable'): TransformerConv(
                            hidden_dim, hidden_dim // homophilic_conv_heads,
                            heads=homophilic_conv_heads, dropout=0.1,
                        ),
                        ('constraint', 'shares_variable_with', 'constraint'): TransformerConv(
                            hidden_dim, hidden_dim // homophilic_conv_heads,
                            heads=homophilic_conv_heads, dropout=0.1,
                        ),
                    },
                    aggr='sum',
                )
                self.hom_layers.append(conv)
                self.hom_norms_var.append(nn.LayerNorm(hidden_dim))
                self.hom_norms_con.append(nn.LayerNorm(hidden_dim))

            self.var_fusion = GatedFusion(hidden_dim)
            self.con_fusion = GatedFusion(hidden_dim)

        self.projector = nn.Sequential(
            Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            Linear(hidden_dim, hidden_dim),
        )

    def _has_homophilic_edges(self, data):
        """Check if homophilic edge types exist in the data."""
        return (
            ('variable', 'shares_constraint_with', 'variable') in data.edge_index_dict
            and ('constraint', 'shares_variable_with', 'constraint') in data.edge_index_dict
        )

    def _encode_features(self, data):
        """Encode raw features, conditionally including block PE."""
        v_x = data['variable'].x
        v_pe = data['variable'].pe
        c_x = data['constraint'].x
        c_pe = data['constraint'].pe

        if self.block_pe_dim > 0:
            v_feats = torch.cat([v_x, v_pe, data['variable'].block_pe], dim=-1)
            c_feats = torch.cat([c_x, c_pe, data['constraint'].block_pe], dim=-1)
        else:
            v_feats = torch.cat([v_x, v_pe], dim=-1)
            c_feats = torch.cat([c_x, c_pe], dim=-1)

        return v_feats, c_feats

    def forward(self, data):
        v_feats, c_feats = self._encode_features(data)

        x_dict = {
            'variable': self.var_encoder(v_feats),
            'constraint': self.con_encoder(c_feats),
        }

        edge_index_dict = data.edge_index_dict
        edge_attr_dict = data.edge_attr_dict

        # --- Heterophilic channel (var↔con) ---
        for i, conv in enumerate(self.layers):
            h = conv(x_dict, edge_index_dict, edge_attr_dict=edge_attr_dict)
            x_dict = {
                'variable': self.norms_var[i](F.relu(h['variable'] + x_dict['variable'])),
                'constraint': self.norms_con[i](F.relu(h['constraint'] + x_dict['constraint'])),
            }

        # --- Homophilic channel (var↔var + con↔con) ---
        if self.use_homophilic and self._has_homophilic_edges(data):
            # Re-encode from raw features for the homophilic branch
            x_hom = {
                'variable': self.var_encoder(v_feats),
                'constraint': self.con_encoder(c_feats),
            }

            hom_edge_index_dict = {
                ('variable', 'shares_constraint_with', 'variable'):
                    data['variable', 'shares_constraint_with', 'variable'].edge_index,
                ('constraint', 'shares_variable_with', 'constraint'):
                    data['constraint', 'shares_variable_with', 'constraint'].edge_index,
            }

            for i, conv in enumerate(self.hom_layers):
                h = conv(x_hom, hom_edge_index_dict)
                x_hom = {
                    'variable': self.hom_norms_var[i](F.relu(h['variable'] + x_hom['variable'])),
                    'constraint': self.hom_norms_con[i](F.relu(h['constraint'] + x_hom['constraint'])),
                }

            x_dict = {
                'variable': self.var_fusion(x_dict['variable'], x_hom['variable']),
                'constraint': self.con_fusion(x_dict['constraint'], x_hom['constraint']),
            }

        return self.projector(x_dict['variable'])
