"""
train_best_reply_local.py — reproduce lead_reply_prediction_CRISPDM_(1).ipynb LOCALLY.

Colab pickles (sklearn 1.6.1) fail to load under the local sklearn (1.9.0):
    AttributeError: Can't get attribute '_RemainderColsList'
Retraining locally regenerates best_lead_reply_model.joblib with THIS machine's
sklearn, eliminating the cross-version incompatibility — same data, same features,
same models, same CV-based selection as the notebook.

Run:  ./venv/Scripts/python.exe ml/train_best_reply_local.py
"""
import os
import joblib
import pandas as pd
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.metrics import roc_auc_score

try:
    from xgboost import XGBClassifier
    HAS_XGB = True
except Exception:
    HAS_XGB = False

HERE = os.path.dirname(__file__)
RANDOM_STATE = 42

# ── Feature engineering (verbatim from the notebook) ──────────────────────────
CITY_TO_COUNTRY = {
    "berlin": "Germany", "munich": "Germany", "hamburg": "Germany", "germany": "Germany",
    "singapore": "Singapore", "london": "UK", "manchester": "UK", "cambridge": "UK",
    "basingstoke": "UK", "uk": "UK", "dubai": "UAE", "abu dhabi": "UAE", "uae": "UAE",
    "paris": "France", "lyon": "France", "toulouse": "France", "france": "France",
    "milan": "Italy", "rome": "Italy", "turin": "Italy", "bologna": "Italy", "italy": "Italy",
    "madrid": "Spain", "barcelona": "Spain", "valencia": "Spain", "spain": "Spain",
    "amsterdam": "Netherlands", "rotterdam": "Netherlands", "utrecht": "Netherlands", "netherlands": "Netherlands",
    "stockholm": "Sweden", "gothenburg": "Sweden", "malmo": "Sweden", "sweden": "Sweden",
    "tokyo": "Japan", "osaka": "Japan", "yokohama": "Japan", "japan": "Japan",
    "bangalore": "India", "mumbai": "India", "delhi": "India", "hyderabad": "India", "india": "India",
    "sao paulo": "Brazil", "rio de janeiro": "Brazil", "belo horizonte": "Brazil", "brazil": "Brazil",
    "toronto": "Canada", "vancouver": "Canada", "montreal": "Canada", "canada": "Canada",
    "sydney": "Australia", "melbourne": "Australia", "brisbane": "Australia", "australia": "Australia",
    "united states": "USA",
}


def get_country(loc):
    if pd.isna(loc):
        return "Unknown"
    parts = [p.strip() for p in str(loc).split(",")]
    last = parts[-1].lower()
    if last in CITY_TO_COUNTRY:
        return CITY_TO_COUNTRY[last]
    first = parts[0].lower()
    return CITY_TO_COUNTRY.get(first, parts[-1])


def role_group(role):
    r = str(role).lower()
    if any(k in r for k in ["cto", "technology", "engineering", "head of ai", "digital", "data"]): return "tech"
    if any(k in r for k in ["sales"]): return "sales"
    if any(k in r for k in ["marketing", "cmo", "retail media"]): return "marketing"
    if any(k in r for k in ["hr", "people", "hrbp"]): return "hr"
    if any(k in r for k in ["finance", "cfo"]): return "finance"
    return "other"


def build_features(data):
    d = pd.DataFrame()
    d["score"]          = data["score"]
    d["email_verified"] = data["email_verified"].astype(int)
    d["has_email"]      = (data["email"].notna() & (data["email"].astype(str).str.strip() != "")).astype(int)
    d["has_insights"]   = (data["insights"].notna() & (data["insights"].astype(str).str.strip() != "")).astype(int)
    d["segment"]        = data["segment"].fillna("unknown")
    d["email_source"]   = data["email_source"].fillna("none").replace("", "none")
    d["role_group"]     = data["role"].apply(role_group)
    d["country"]        = data["location"].apply(get_country)
    return d


NUMERIC   = ["score"]
BINARY    = ["email_verified", "has_email", "has_insights"]
CATEGORIC = ["segment", "email_source", "role_group", "country"]


def main(csv_path=None):
    csv_path = csv_path or os.path.join(HERE, "leads_data.csv")
    df = pd.read_csv(csv_path)
    X = build_features(df)
    y = df["replied"].astype(int)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, stratify=y, random_state=RANDOM_STATE)

    try:
        ohe = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    except TypeError:
        ohe = OneHotEncoder(handle_unknown="ignore", sparse=False)

    preprocess = ColumnTransformer([
        ("num", StandardScaler(), NUMERIC),
        ("bin", "passthrough", BINARY),
        ("cat", ohe, CATEGORIC),
    ])

    models = {
        "Logistic Regression": LogisticRegression(max_iter=1000, random_state=RANDOM_STATE),
        "Decision Tree":       DecisionTreeClassifier(max_depth=6, random_state=RANDOM_STATE),
        "Random Forest":       RandomForestClassifier(n_estimators=300, random_state=RANDOM_STATE),
        "Gradient Boosting":   GradientBoostingClassifier(random_state=RANDOM_STATE),
    }
    if HAS_XGB:
        models["XGBoost"] = XGBClassifier(
            n_estimators=300, learning_rate=0.05, max_depth=4,
            subsample=0.9, colsample_bytree=0.9, eval_metric="logloss",
            random_state=RANDOM_STATE)

    pipes = {name: Pipeline([("prep", preprocess), ("clf", m)]) for name, m in models.items()}

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    scores = {}
    for name, pipe in pipes.items():
        scores[name] = cross_val_score(pipe, X_train, y_train, cv=cv, scoring="roc_auc").mean()
        print(f"  {name:22s} CV ROC-AUC = {scores[name]:.4f}")

    best_name = max(scores, key=scores.get)
    best_model = pipes[best_name].fit(X_train, y_train)   # same as the notebook (fit on train)
    test_auc = roc_auc_score(y_test, best_model.predict_proba(X_test)[:, 1])
    print(f"Best (CV): {best_name}  |  test ROC-AUC = {test_auc:.4f}")

    out = os.path.join(HERE, "best_lead_reply_model.joblib")
    joblib.dump(best_model, out)
    print("Saved ->", out)


if __name__ == "__main__":
    import sys
    main(sys.argv[1] if len(sys.argv) > 1 else None)
