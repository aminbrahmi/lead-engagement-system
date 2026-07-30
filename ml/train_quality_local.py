"""
train_quality_local.py — retrain the email-quality model LOCALLY so the saved
pipeline matches this machine's scikit-learn version (Colab-trained .joblib files
fail to load across versions: '_RemainderColsList').

Reproduces ml/email_quality_scoring_v2.ipynb:
  - 5 models, winner chosen on 5-fold CV ROC-AUC
  - a separate interpretable LogReg (engineered features only) for suggestions
Saves -> ml/email_quality_model.joblib  (dict: pipeline, interp_model, coef_map, ...)

Run:  ./venv/Scripts/python.exe ml/train_quality_local.py
"""
import os, joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import MinMaxScaler, OneHotEncoder
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from lightgbm import LGBMClassifier
from xgboost import XGBClassifier

HERE = os.path.dirname(__file__)
RANDOM_STATE = 42
TEXT_COL = "full_text"
NUM_COLS = ["word_count", "has_question", "has_cta", "has_link",
            "personalization_level", "num_exclamations"]
CAT_COLS = ["tone", "length_bucket"]


def main(csv_path=None):
    csv_path = csv_path or os.path.join(HERE, "email_replied_dataset.csv")
    df = pd.read_csv(csv_path)
    df = df.dropna(subset=["replied"]).reset_index(drop=True)
    df["subject"] = df["subject"].fillna("")
    df["body"]    = df["body"].fillna("")
    df[TEXT_COL]  = df["subject"].astype(str) + " . " + df["body"].astype(str)
    for col in NUM_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    X = df[[TEXT_COL] + NUM_COLS + CAT_COLS]
    y = df["replied"].astype(int).values

    X_train, _, y_train, _ = train_test_split(
        X, y, test_size=0.25, stratify=y, random_state=RANDOM_STATE)

    pre = ColumnTransformer(
        transformers=[
            ("txt", TfidfVectorizer(max_features=1500, ngram_range=(1, 2),
                                    stop_words="english", min_df=2), TEXT_COL),
            ("num", MinMaxScaler(), NUM_COLS),
            ("cat", OneHotEncoder(handle_unknown="ignore"), CAT_COLS),
        ],
        sparse_threshold=0,
    )

    models = {
        "LogisticRegression": LogisticRegression(max_iter=1000, C=1.0),
        "RandomForest":       RandomForestClassifier(n_estimators=400, random_state=RANDOM_STATE),
        "GradientBoosting":   GradientBoostingClassifier(random_state=RANDOM_STATE),
        "LightGBM":           LGBMClassifier(random_state=RANDOM_STATE, verbose=-1),
        "XGBoost":            XGBClassifier(random_state=RANDOM_STATE, eval_metric="logloss"),
    }

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    scores = {}
    for name, clf in models.items():
        pipe = Pipeline([("pre", pre), ("clf", clf)])
        scores[name] = cross_val_score(pipe, X_train, y_train, cv=cv, scoring="roc_auc").mean()
        print(f"  {name:20s} CV ROC-AUC = {scores[name]:.3f}")

    best_name = max(scores, key=scores.get)
    print("Best (CV):", best_name)

    # Final score model on ALL data
    final = Pipeline([("pre", pre), ("clf", models[best_name])]).fit(X, y)

    # Interpretable model (engineered features only) -> coefficients for suggestions
    interp_pre = ColumnTransformer([
        ("num", MinMaxScaler(), NUM_COLS),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CAT_COLS),
    ])
    interp_model = Pipeline([("pre", interp_pre), ("clf", LogisticRegression(max_iter=1000))])
    interp_model.fit(df[NUM_COLS + CAT_COLS], y)
    interp_names = interp_model.named_steps["pre"].get_feature_names_out()
    interp_coefs = interp_model.named_steps["clf"].coef_.ravel()
    coef_map = dict(zip(interp_names, interp_coefs))

    out = os.path.join(HERE, "email_quality_model.joblib")
    joblib.dump({
        "pipeline": final,
        "interp_model": interp_model,
        "coef_map": coef_map,
        "num_cols": NUM_COLS, "cat_cols": CAT_COLS, "text_col": TEXT_COL,
        "best_name": best_name,
    }, out)
    print("Saved ->", out)


if __name__ == "__main__":
    import sys
    main(sys.argv[1] if len(sys.argv) > 1 else None)
