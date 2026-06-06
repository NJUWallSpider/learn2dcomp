"""Evaluate GNN accuracy on OR-Library instances that have labels."""
import torch, numpy as np
from pathlib import Path
from gnn_model import GraphTransformer
from data_process import MILPDataset
import config, utilities
from torch_geometric.loader import DataLoader
from sklearn.metrics import adjusted_rand_score, v_measure_score, normalized_mutual_info_score

mp = config.MODEL_PARAMS
model = GraphTransformer(
    hidden_dim=mp["emb_size"], num_layers=3,
    pe_dim=mp.get("pe_dim", 8), block_pe_dim=mp.get("block_pe_dim", 8)
).cuda()
ckpt = torch.load("models/best_model.pth", map_location="cuda")
model.load_state_dict(ckpt)
model.eval()

for d in ["orlib_gapa", "orlib_gapd"]:
    files = [str(f) for f in Path(f"data/processed/gap/{d}").glob("*.pt")]
    if not files:
        continue
    ds = MILPDataset(files)
    loader = DataLoader(ds, batch_size=1, shuffle=False)
    pcr, vm, ari, nmi, la = [], [], [], [], []
    for data in loader:
        data = data.cuda()
        with torch.no_grad():
            ve, ce, cbl, cll = model(data)
        emb = ve.cpu().numpy()
        labels = data["variable"].y.cpu().numpy()
        mask = labels >= 0
        if mask.sum() == 0:
            continue
        val_emb = emb[mask]
        val_labels = labels[mask]
        ms = max(2, int(len(val_emb) * 0.05))
        pred, _ = utilities.hierarchical_dbscan(val_emb, ms, 0.2, 0.2, 4.0)
        pred = utilities.reassign_noise_points(val_emb, pred)
        ari.append(adjusted_rand_score(val_labels, pred))
        nmi.append(normalized_mutual_info_score(val_labels, pred))
        vm.append(v_measure_score(val_labels, pred))
        tc = {l: set() for l in set(val_labels)}
        pc = {l: set() for l in set(pred) if l >= 0}
        for idx, l in enumerate(val_labels):
            tc[l].add(idx)
        for idx, l in enumerate(pred):
            if l >= 0:
                pc[l].add(idx)
        perfect = 0
        for tl, ts in tc.items():
            sample = next(iter(ts))
            pl = pred[sample]
            if pl >= 0 and pc.get(pl) == ts:
                perfect += 1
        pcr.append(perfect / len(tc) if tc else 0)
        if hasattr(data["constraint"], "y") and data["constraint"].y is not None:
            ct = data["constraint"].y.cpu().numpy()
            lpm = (ct >= 0) | (ct == -2)
            if lpm.sum() > 0:
                lp = (torch.sigmoid(cll).cpu().numpy() > 0.5).flatten()
                lt = (ct == -2).astype(float)
                la.append(float((lp[lpm] == lt[lpm]).mean()))
    print("%s: PCR=%.4f V=%.4f ARI=%.4f NMI=%.4f LinkAcc=%.4f" % (
        d, np.mean(pcr), np.mean(vm), np.mean(ari), np.mean(nmi),
        np.mean(la) if la else 0))
