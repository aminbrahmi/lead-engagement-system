"""
train_reply_model.py — train a lead-reply prediction model (replied 0/1).

Usage:
    python ml/train_reply_model.py path/to/dataset.csv

Produces:
  • class balance + feasibility check
  • cross-validated ROC-AUC / PR-AUC for Logistic Regression and LightGBM
  • classification report on a stratified hold-out
  • feature importances
  • saves the best model to ml/reply_model.joblib
"""

import sys
import warnings
warnings.filterwarnings("ignore")

import joblib
import numpy as np
import pandas as pd

from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.metrics import (
    roc_auc_score, average_precision_score, classification_report, confusion_matrix,
)

try:
    from lightgbm import LGBMClassifier
    HAS_LGBM = True
except Exception:
    HAS_LGBM = False


FREE_DOMAINS = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "icloud.com", "protonmail.com"}


# ── Feature engineering ────────────────────────────────────────────────────────

def build_features(df: pd.DataFrame):
    df = df.copy()

    # ── Derived features ──
    if "email" in df:
        df["has_email"] = df["email"].notna().astype(int)
        def _domain_type(e):
            if not isinstance(e, str) or "@" not in e:
                return "none"
            d = e.split("@")[-1].lower()
            return "free" if d in FREE_DOMAINS else "corporate"
        df["domain_type"] = df["email"].apply(_domain_type)
    else:
        df["has_email"], df["domain_type"] = 0, "none"

    df["has_insights"] = df["insights"].notna().astype(int) if "insights" in df else 0

    if "location" in df:
        df["country"] = (df["location"].fillna("")
                         .apply(lambda s: (s.split(",")[-1].strip() or "unknown")))
    else:
        df["country"] = "unknown"

    if "notes" in df:
        df["has_funding"] = (df["notes"].fillna("")
            .str.contains(r"rais|fund|seed|series|\$|£|€|\bM\b", case=False, regex=True)
            .astype(int))
    else:
        df["has_funding"] = 0

    if "email_verified" in df:
        df["email_verified"] = df["email_verified"].astype(int)

    # ── Select features (only those present) ──
    cat_features = [c for c in ["role", "country", "email_source", "segment", "domain_type"] if c in df.columns]
    num_features = [c for c in ["score", "email_verified", "has_email", "has_insights", "has_funding"] if c in df.columns]

    X = df[cat_features + num_features].copy()
    for c in cat_features:
        X[c] = X[c].fillna("unknown").astype(str)
    for c in num_features:
        X[c] = pd.to_numeric(X[c], errors="coerce").fillna(0)

    return X, cat_features, num_features


def make_preprocessor(cat_features, num_features):
    # min_frequency groups rare categories → avoids exploding one-hot on 600-800 rows
    ohe = OneHotEncoder(handle_unknown="ignore", min_frequency=10, sparse_output=False)
    return ColumnTransformer([
        ("cat", ohe, cat_features),
        ("num", StandardScaler(), num_features),
    ])


# ── Main ───────────────────────────────────────────────────────────────────────

def main(csv_path: str):
    df = pd.read_csv(csv_path)
    if "replied" not in df.columns:
        print("ERROR: no 'replied' column in the dataset."); return

    y = df["replied"].astype(int)
    n, n1, n0 = len(y), int(y.sum()), int((y == 0).sum())
    minority = min(n1, n0)
    print("=" * 60)
    print(f"Dataset: {n} rows | replied=1: {n1} ({n1/n*100:.1f}%) | replied=0: {n0} ({n0/n*100:.1f}%)")
    print(f"Minority class: {minority} samples")
    if minority < 30:
        print("⚠️  Minority class < 30 → model will be unreliable. Collect more data.")
    elif minority < 60:
        print("⚠️  Minority class small (30-60) → baseline only, keep few features.")
    else:
        print("✅ Enough samples to train a baseline.")
    print("=" * 60)

    X, cat, num = build_features(df)
    print(f"Features ({len(cat)+len(num)}): {cat + num}\n")

    pre = make_preprocessor(cat, num)
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    models = {
        "LogisticRegression": LogisticRegression(class_weight="balanced", max_iter=1000),
    }
    if HAS_LGBM:
        models["LightGBM"] = LGBMClassifier(
            n_estimators=300, num_leaves=15, min_child_samples=20,
            learning_rate=0.05, class_weight="balanced", verbose=-1,
        )

    # ── Cross-validated comparison ──
    best_name, best_auc, best_pipe = None, -1, None
    for name, clf in models.items():
        pipe = Pipeline([("pre", pre), ("clf", clf)])
        auc = cross_val_score(pipe, X, y, cv=cv, scoring="roc_auc").mean()
        ap  = cross_val_score(pipe, X, y, cv=cv, scoring="average_precision").mean()
        print(f"{name:20} CV ROC-AUC={auc:.3f}  PR-AUC={ap:.3f}")
        if auc > best_auc:
            best_name, best_auc, best_pipe = name, auc, pipe

    print(f"\n→ Best model: {best_name} (ROC-AUC={best_auc:.3f})\n")

    # ── Hold-out evaluation ──
    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)
    best_pipe.fit(Xtr, ytr)
    proba = best_pipe.predict_proba(Xte)[:, 1]
    pred = (proba >= 0.5).astype(int)
    print("Hold-out (20%):")
    print(f"  ROC-AUC={roc_auc_score(yte, proba):.3f}  PR-AUC={average_precision_score(yte, proba):.3f}")
    print("  Confusion matrix [ [TN FP] [FN TP] ]:\n", confusion_matrix(yte, pred))
    print(classification_report(yte, pred, digits=3))

    # ── Refit on ALL data + save ──
    best_pipe.fit(X, y)
    out = "ml/reply_model.joblib"
    joblib.dump({"pipeline": best_pipe, "features": cat + num}, out)
    print(f"Saved model → {out}")
    print("Score a lead:  proba = pipeline.predict_proba(X)[:,1]  → lead score 0-100")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "data/leads_export.csv"
    main(path)
