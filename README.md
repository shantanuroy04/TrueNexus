# TrueNexus

AI phishing detection demo: check a URL, or an email (pasted or uploaded as `.eml`), with two trained models. Every link inside an email is also checked by the URL model, and the stronger warning wins. Results are advisory. Nothing submitted is opened, fetched, stored or logged.

## Model files (not in git)

Put these in `models/`:

| Folder | What | Where it comes from |
|---|---|---|
| `models/model_bundle/` | URL model v6, with `final_report.json` (test results shown on "How it works") | `model_bundle/` from the Kaggle run of `notebooks/MLPhil_URL_Phishing_Pipeline.ipynb` |
| `models/email_security_model/` | Email model, with its own `email_preprocess.py` | `email_security_model/` from the Kaggle run |
| `models/email_reports/` | Test results shown on "How it works" | `summary.json`, `external_metrics.csv`, `external_ci95.csv` from the Kaggle run's `reports/` |

A missing model does not stop the site: that section shows "Analysis unavailable" and the rest keeps working. Missing reports only hide the figures.

## Run with Docker (one command)

```powershell
docker compose up --build
```

Open http://localhost:5173. Only the website port is published; the backend is reachable only through it. Use another port with `$env:WEB_PORT = "8080"` before the command. Accounts are kept in the Docker volume `accounts`.

## Run without Docker (PowerShell)

Backend, on port 8000:

```powershell
cd backend
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu
.venv\Scripts\python -m pip install -r requirements.txt
$env:MLPHIL_URL_BUNDLE = "..\models\model_bundle"
$env:MLPHIL_EMAIL_MODEL_DIR = "..\models\email_security_model"
.venv\Scripts\python -m uvicorn main:app --host 127.0.0.1 --port 8000 --no-server-header
```

Website, on port 5173 (forwards `/api` to the backend):

```powershell
cd frontend
npm install
npm run dev
```

Check which models loaded: http://localhost:5173/api/health

## Tests

```powershell
cd backend;  .venv\Scripts\python -m pytest -q     # API, models, accounts, .eml
cd frontend; npm test                              # pages and results (mocked API)
cd frontend; npm run e2e                           # real browser, real models (needs Google Chrome)
```

## Accounts

Login and signup use SQLite at `data/mlphil.db` (created on first start, not in git). It stores name, email, an Argon2id password hash and hashed session tokens; never checked URLs or emails. Checks do not need an account. To reset all accounts, stop the backend and delete `data/mlphil.db`. Set `MLPHIL_COOKIE_SECURE=1` when the site is served over HTTPS.

## Known limitations

The figures are on the site's "How it works" page, read from the model reports. In short: the email model scores much lower on the external test than on the internal one, the URL model has no test results in its bundle, neither model can see page content, senders or attachments, and the email model's base is English-only.
