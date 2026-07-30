# TheLeadFlow

**Automated B2B lead engagement, from discovery to analysis.**

TheLeadFlow turns a plain-language campaign brief into a full outreach cycle. A pipeline of **8 specialized AI agents** finds prospects, qualifies them, writes personalized emails, sends them with follow-ups, tracks replies, and reports on performance — augmented by **2 machine-learning models** that predict reply likelihood and score email quality.

---

## ✨ Features

- **Prompt-to-campaign** — describe your target in natural language; the pipeline does the rest.
- **8-agent pipeline** (LangGraph) — Collector → Qualifier → Enricher → Writer → Sender → Tracker → Monitor → Analyst.
- **Lead scoring & segmentation** — hot / warm / cold, with SMTP-verified emails.
- **A/B personalized emails** — insight-led vs challenge-led, editable before send.
- **Automatic follow-ups** — J+3 / J+7 / J+14 sequences.
- **Unified inbox** — replies classified automatically (interested, info request, out-of-office, bounce…).
- **Analytics & PDF reports** — click / reply / bounce rates, best variant, recommendations.
- **Predictive ML** — a **Reply %** per lead and a live **email-quality score** with suggestions.
- **Auth & multi-tenant** — email/password + Google sign-in, email verification, per-user data isolation.
- **GDPR-ready** — one-click unsubscribe (HMAC-signed) and complete data erasure (Art. 17).

---

## 🏗️ Architecture

```
React SPA  ──REST/JWT──▶  FastAPI (auth · multi-tenant)
                              │  orchestration
                    LangGraph pipeline (8 agents)
              ┌───────────────┼────────────────────────┐
     LLM Factory (fallback)   External services      PostgreSQL
     Groq·Gemini·Together     Tavily·Hunter·SMTP/IMAP  (multi-tenant)
     + ML models              Google
     Reply% · Email Quality
```

### The 8 agents

| # | Agent | Role | LLM | Tools |
|---|-------|------|-----|-------|
| 1 | **Collector** | Find real prospects | ✅ | Tavily |
| 2 | **Qualifier** | Score, segment, find email | ✅ | Hunter · SMTP verify |
| 3 | **Enricher** | Gather personalization context | ✅ | Tavily |
| 4 | **Writer** | Write A/B personalized emails | ✅ | — |
| 5 | **Sender** | Send + schedule follow-ups | — | SMTP · scheduler |
| 6 | **Tracker** | Read replies & clicks | — | IMAP |
| 7 | **Monitor** | Classify replies & act | ✅ | — |
| 8 | **Analyst** | Metrics & PDF reports | ✅ | ReportLab |

*LLM calls go through an **LLM Factory** with an automatic fallback chain: Groq → Google Gemini → Together → OpenRouter.*

### The 2 ML models (scikit-learn, trained with CRISP-DM)

| Model | Predicts | Algorithm | Inputs |
|-------|----------|-----------|--------|
| **Reply %** | Probability a lead replies | Gradient Boosting | Lead profile (score, email verified, segment, source, role, country) |
| **Email Quality** | Reply likelihood of a message | Logistic Regression + TF-IDF | Email content (subject, body) + engineered features |

---

## 🧰 Tech stack

- **Backend:** Python · FastAPI · PostgreSQL · psycopg2
- **Frontend:** React (Create React App) · Recharts
- **Orchestration:** LangGraph · LangChain
- **LLMs:** Groq, Google Gemini, Together, OpenRouter (via a fallback factory)
- **ML:** scikit-learn · LightGBM · XGBoost · joblib
- **Services:** Tavily (web search) · Hunter (emails) · SMTP/IMAP · Google OAuth · ReportLab (PDF)
- **Auth:** JWT (PyJWT) · bcrypt · Google Identity Services

---

## 📁 Project structure

```
lead-engagement-system/
├── agents/            # The 8 pipeline agents + llm_factory
├── orchestration/     # LangGraph graph + prompts
├── backend/           # FastAPI app (server.py) — REST + WebSocket + auth
├── frontend/          # React single-page app
├── ml/                # ML models, notebooks, training scripts
├── memory/            # PostgreSQL storage layer (storage.py)
├── tools/             # Prompt parser & helpers
├── utils/             # Auth, email verification, JSON helpers
├── main.py            # CLI entry point (run the pipeline in a terminal)
└── requirements.txt
```

---

## 🚀 Getting started

### Prerequisites

- **Python 3.11+**
- **Node.js 18+**
- **PostgreSQL** (a reachable database)

### 1. Backend

```bash
# from the project root
python -m venv venv
source venv/Scripts/activate        # Windows (Git Bash)
# source venv/bin/activate          # macOS/Linux
pip install -r requirements.txt
```

Create a `.env` file at the project root (see **Configuration** below), then start the API:

```bash
python backend/server.py            # serves on http://localhost:8000
```

### 2. Frontend

```bash
cd frontend
npm install
npm start                           # serves on http://localhost:3000
```

### 3. (Optional) Run the pipeline from the terminal

```bash
python main.py                      # prompts for a campaign brief
```

---

## ⚙️ Configuration (`.env`)

Create a `.env` at the project root. **Never commit it** — it is gitignored.

**Required**

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | PostgreSQL connection string |
| `JWT_SECRET` | Secret for signing auth tokens *(the app refuses to start if unset)* |
| `UNSUB_SECRET` | Secret for HMAC-signed unsubscribe links |
| `GROQ_API_KEY` | Primary LLM provider |
| `TAVILY_API_KEY` | Web search (Collector, Enricher) |

**Recommended**

| Variable | Purpose |
|----------|---------|
| `GOOGLE_API_KEY`, `TOGETHER_API_KEY`, `OPENROUTER_API_KEY` | LLM fallback providers |
| `HUNTER_API_KEY` | Email discovery |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS` | Sending & email verification |
| `GOOGLE_CLIENT_ID` | Google sign-in (frontend fetches it at runtime) |
| `APP_URL` | Base URL for email-verification links (default `http://localhost:8000`) |
| `REACT_APP_API_URL` | API base URL used by the frontend |

> Generate a strong `JWT_SECRET`:
> `python -c "import secrets; print(secrets.token_urlsafe(48))"`

---

## 🤖 Machine-learning models

The trained models live in `ml/`:

- `ml/best_lead_reply_model.joblib` — the **Reply %** model
- `ml/email_quality_model.joblib` — the **Email Quality** model

They degrade gracefully: if a model can't be loaded, the corresponding feature is hidden (no crash).

### Version compatibility (Colab ↔ local)

Models trained on Google Colab (scikit-learn 1.6.x) can fail to load under a different local scikit-learn version (`_RemainderColsList` error). The fix is to **retrain locally**, which regenerates a compatible artifact from the same data and pipeline:

```bash
python ml/train_best_reply_local.py     # regenerates best_lead_reply_model.joblib
python ml/train_quality_local.py        # regenerates email_quality_model.joblib
```

The Colab notebooks used to build the models are in `ml/` (`lead_reply_prediction_CRISPDM_(1).ipynb`, `email_quality_scoring_v2.ipynb`).

---

## 🔒 Security & privacy

- **Authentication** on every endpoint (global middleware) except public lead-facing links (unsubscribe/tracking, protected by HMAC tokens) and the OAuth callback.
- **Ownership checks** on leads, campaigns and discussions — an authenticated user only ever accesses their own data (anti-IDOR).
- **Multi-tenant isolation** — campaigns, leads, notifications, discussions and exclusions are scoped per user.
- **GDPR** — HMAC-signed one-click unsubscribe, and full erasure of a lead's data across all stores.

---

## 🧭 Methodology

Built with **Scrum** (4 iterative sprints) combined with **CRISP-DM** for the data-science work — each ML model follows its own CRISP-DM cycle (Business Understanding → Deployment) inside its sprint.

---

