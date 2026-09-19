# modules/local/surrogate_model/src/surrogate_model/mlp.py

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset


class MultiFingerprintDataset(Dataset):
    def __init__(self, fingerprints, descriptors, targets):
        self.fingerprints = {
            name: torch.as_tensor(fp, dtype=torch.float32)
            for name, fp in fingerprints.items()
        }
        self.descriptors = torch.as_tensor(descriptors, dtype=torch.float32)
        self.targets = torch.as_tensor(targets, dtype=torch.float32)

    def __len__(self):
        return len(self.targets)

    def __getitem__(self, idx):
        fp_item = {name: fp[idx] for name, fp in self.fingerprints.items()}
        return fp_item, self.descriptors[idx], self.targets[idx]


def collate_multi_fingerprint(batch):
    fp_items, descriptors, targets = zip(*batch)
    fp_names = fp_items[0].keys()
    fingerprints = {
        name: torch.stack([item[name] for item in fp_items]) for name in fp_names
    }
    return fingerprints, torch.stack(descriptors), torch.stack(targets)


class FingerprintEncoder(nn.Module):
    def __init__(
        self,
        input_dim,
        embedding_dim,
        dropout=0.3,
        log_transform=False,
        normalize_input=True,
    ):
        super().__init__()
        self.log_transform = log_transform
        self.input_norm = (
            nn.BatchNorm1d(input_dim, affine=False) if normalize_input else None
        )
        self.net = nn.Sequential(
            nn.Linear(input_dim, embedding_dim),
            nn.BatchNorm1d(embedding_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
        )

    def forward(self, x):
        if self.log_transform:
            x = torch.log1p(x)
        if self.input_norm is not None:
            x = self.input_norm(x)
        return self.net(x)


class MultiFingerprintMLP(nn.Module):
    def __init__(
        self,
        fingerprint_dims,
        descriptor_dim=0,
        embedding_dims=None,
        log_transform=None,
        hidden_dims=(512, 256, 128),
        dropout=0.3,
        normalize_descriptors=True,
    ):
        super().__init__()
        embedding_dims = embedding_dims or {}
        log_transform = log_transform or {}
        default_embedding_dim = 128

        self.fingerprint_names = list(fingerprint_dims.keys())
        self.encoders = nn.ModuleDict(
            {
                name: FingerprintEncoder(
                    input_dim=dim,
                    embedding_dim=embedding_dims.get(name, default_embedding_dim),
                    dropout=dropout,
                    log_transform=log_transform.get(name, False),
                )
                for name, dim in fingerprint_dims.items()
            }
        )

        total_embedding_dim = sum(
            embedding_dims.get(name, default_embedding_dim)
            for name in self.fingerprint_names
        )

        self.descriptor_norm = (
            nn.BatchNorm1d(descriptor_dim, affine=False)
            if normalize_descriptors and descriptor_dim > 0
            else None
        )

        input_dim = total_embedding_dim + descriptor_dim
        layers = []
        for hidden_dim in hidden_dims:
            layers.extend(
                [
                    nn.Linear(input_dim, hidden_dim),
                    nn.BatchNorm1d(hidden_dim),
                    nn.ReLU(),
                    nn.Dropout(dropout),
                ]
            )
            input_dim = hidden_dim
        layers.append(nn.Linear(input_dim, 1))
        self.head = nn.Sequential(*layers)

    def forward(self, fingerprints, descriptors=None):
        embeds = [
            self.encoders[name](fingerprints[name]) for name in self.fingerprint_names
        ]
        x = torch.cat(embeds, dim=1)
        if descriptors is not None and descriptors.shape[1] > 0:
            if self.descriptor_norm is not None:
                descriptors = self.descriptor_norm(descriptors)
            x = torch.cat([x, descriptors], dim=1)
        return self.head(x).squeeze(-1)


def pairwise_ranking_loss(preds, targets, margin=0.0, num_pairs=None):
    n = preds.shape[0]
    if num_pairs is None:
        num_pairs = n * 4

    idx_i = torch.randint(0, n, (num_pairs,), device=preds.device)
    idx_j = torch.randint(0, n, (num_pairs,), device=preds.device)

    valid = targets[idx_i] != targets[idx_j]
    idx_i, idx_j = idx_i[valid], idx_j[valid]
    if idx_i.numel() == 0:
        return torch.tensor(0.0, device=preds.device, requires_grad=True)

    target_sign = torch.sign(targets[idx_i] - targets[idx_j])
    pred_diff = preds[idx_i] - preds[idx_j]
    return F.relu(margin - target_sign * pred_diff).mean()


def combined_loss(preds, targets, ranking_weight=0.0, margin=0.0, num_pairs=None):
    mse = F.mse_loss(preds, targets)
    if ranking_weight <= 0.0:
        return mse, {"mse": mse.item(), "ranking": 0.0}
    ranking = pairwise_ranking_loss(preds, targets, margin=margin, num_pairs=num_pairs)
    total = mse + ranking_weight * ranking
    return total, {"mse": mse.item(), "ranking": ranking.item()}


def _move_to_device(fingerprints, device):
    return {name: fp.to(device) for name, fp in fingerprints.items()}


def train_epoch(model, loader, optimizer, device, ranking_weight=0.0):
    model.train()
    total_loss = 0.0
    for fingerprints, descriptors, targets in loader:
        fingerprints = _move_to_device(fingerprints, device)
        descriptors = descriptors.to(device)
        targets = targets.to(device)

        optimizer.zero_grad()
        preds = model(fingerprints, descriptors)
        loss, _ = combined_loss(preds, targets, ranking_weight=ranking_weight)
        loss.backward()
        optimizer.step()
        total_loss += loss.item() * len(targets)

    return total_loss / len(loader.dataset)


@torch.no_grad()
def evaluate(model, loader, device):
    model.eval()
    all_preds, all_targets = [], []
    for fingerprints, descriptors, targets in loader:
        fingerprints = _move_to_device(fingerprints, device)
        descriptors = descriptors.to(device)
        preds = model(fingerprints, descriptors)
        all_preds.append(preds.cpu().numpy())
        all_targets.append(targets.numpy())
    return np.concatenate(all_preds), np.concatenate(all_targets)


def top_k_recall(preds, targets, k_frac=0.01, lower_is_better=False):
    n = len(targets)
    k = max(1, int(n * k_frac))
    if lower_is_better:
        true_top = set(np.argsort(targets)[:k])
        pred_top = set(np.argsort(preds)[:k])
    else:
        true_top = set(np.argsort(targets)[-k:])
        pred_top = set(np.argsort(preds)[-k:])
    return len(true_top & pred_top) / k


def train_model(
    train_fp,
    train_desc,
    train_y,
    val_fp,
    val_desc,
    val_y,
    fingerprint_dims,
    descriptor_dim=0,
    embedding_dims=None,
    log_transform=None,
    epochs=50,
    batch_size=1024,
    lr=1e-3,
    ranking_weight=0.0,
    device=None,
    patience=5,
    recall_fn=None,
):
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    recall_fn = recall_fn or (lambda y_true, y_pred: top_k_recall(y_pred, y_true))

    train_ds = MultiFingerprintDataset(train_fp, train_desc, train_y)
    val_ds = MultiFingerprintDataset(val_fp, val_desc, val_y)
    train_loader = DataLoader(
        train_ds,
        batch_size=batch_size,
        shuffle=True,
        collate_fn=collate_multi_fingerprint,
    )
    val_loader = DataLoader(
        val_ds,
        batch_size=batch_size,
        shuffle=False,
        collate_fn=collate_multi_fingerprint,
    )

    model = MultiFingerprintMLP(
        fingerprint_dims,
        descriptor_dim,
        embedding_dims=embedding_dims,
        log_transform=log_transform,
    ).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-5)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=2)

    best_recall = -1.0
    best_state = None
    epochs_without_improvement = 0

    for epoch in range(epochs):
        train_loss = train_epoch(model, train_loader, optimizer, device, ranking_weight)
        val_preds, val_targets = evaluate(model, val_loader, device)
        recall = recall_fn(val_targets, val_preds)
        scheduler.step(train_loss)

        print(
            f"epoch {epoch + 1}/{epochs} train_loss={train_loss:.4f}"
            f" top1pct_recall={recall:.4f}"
        )

        if recall > best_recall:
            best_recall = recall
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= patience:
                print(f"early stopping at epoch {epoch + 1}")
                break

    if best_state is not None:
        model.load_state_dict(best_state)

    return model, best_recall
