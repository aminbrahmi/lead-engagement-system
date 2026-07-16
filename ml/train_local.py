"""
train_local.py — retrain the reply model IN THE LOCAL ENV so the saved
.joblib is compatible with the installed scikit-learn / lightgbm.

Uses the SAME build_features as inference (ml/reply_scorer) → no train/serve drift.

Usage:
    python ml/train_local.py path/to/leads_data.csv     (default: ml/leads_data.csv)
"""

import sys
import joblib
import pandas as pd

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.metrics import roc_auc_score, average_precision_score, classification_report
from lightgbm import LGBMClassifier

# Same feature engineering used at inference time
sys.path.insert(0, ".")
from ml.reply_scorer import build_features

NUMERIC   = ["score"]
BINARY    = ["email_verified", "has_email", "has_insights"]
CATEGORIC = ["segment", "email_source", "role_group", "country"]


def main(csv_path):
    df = pd.read_csv(csv_path)
    if "replied" not in df.columns:
        print("ERROR: dataset must contain a 'replied' column."); return
    X = build_features(df)
    y = df["replied"].astype(int)
    print(f"Rows: {len(df)} | replied=1: {int(y.sum())} ({y.mean()*100:.1f}%)")

    try:
        ohe = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    except TypeError:
        ohe = OneHotEncoder(handle_unknown="ignore", sparse=False)

    pre = ColumnTransformer([
        ("num", StandardScaler(), NUMERIC),
        ("bin", "passthrough", BINARY),
        ("cat", ohe, CATEGORIC),
    ])
    pipe = Pipeline([
        ("prep", pre),
        ("clf", LGBMClassifier(n_estimators=300, learning_rate=0.05, random_state=42, verbose=-1)),
    ])

    Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, stratify=y, random_state=42)
    pipe.fit(Xtr, ytr)
    proba = pipe.predict_proba(Xte)[:, 1]
    print(f"Test ROC-AUC: {roc_auc_score(yte, proba):.4f} | PR-AUC: {average_precision_score(yte, proba):.4f}")
    print(classification_report(yte, (proba >= 0.5).astype(int), digits=3))

    # Refit on all data and save
    pipe.fit(X, y)
    out = "ml/lead_reply_model.joblib"
    joblib.dump(pipe, out)
    print(f"\n✓ Saved {out} (compatible with local scikit-learn / lightgbm)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "ml/leads_data.csv")
