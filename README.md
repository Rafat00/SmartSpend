# SmartSpend – AI-Powered Personal Expense Tracker and Financial Analytics System

Flask + PostgreSQL + Bootstrap 5 + Chart.js, with scikit-learn predictions, unusual-expense detection,
and an AI assistant (any OpenAI-compatible API such as Groq or OpenAI). Every AI feature has a
rule-based fallback, so the app works even without an API key.

## Project structure

```
SmartSpend/
├── app/
│   ├── __init__.py        # app factory (create_app)
│   ├── models.py          # User, Expense, Budget
│   ├── routes.py          # dashboard, chart API, profile
│   ├── auth/              # register / login / logout
│   ├── expenses/          # CRUD, search/filter, CSV export, categorize
│   ├── budget/            # monthly budget + progress
│   ├── analytics/         # pandas statistics
│   ├── ai/                # ai_service.py (the ONLY file that calls the LLM API), fallback.py
│   ├── ml/                # prediction.py (LinearRegression), anomaly.py (IsolationForest)
│   ├── templates/  static/
├── migrations/            # Flask-Migrate (Alembic)
├── tests/                 # pytest
├── .env.example  .gitignore  config.py  requirements.txt  run.py
```

## Setup on Windows PowerShell

Prerequisites: Python 3.11+ and PostgreSQL (with pgAdmin or psql) installed.

```powershell
cd path\to\SmartSpend
python -m venv venv
.\venv\Scripts\Activate.ps1
# If activation is blocked:  Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Create the PostgreSQL database

```powershell
psql -U postgres -c "CREATE DATABASE smartspend_db;"
```
(If `psql` is not found, open "SQL Shell (psql)" from the Start menu, or use pgAdmin → Create → Database → `smartspend_db`.)

### Create your `.env`

```powershell
Copy-Item .env.example .env
notepad .env
```
Edit these lines (replace `YOUR_PASSWORD` with your own PostgreSQL password):

```
DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/smartspend_db
SECRET_KEY=<paste output of:  python -c "import secrets; print(secrets.token_hex(32))">
AI_API_KEY=<your Groq/OpenAI key, or leave empty to use fallbacks>
AI_MODEL=<e.g. llama-3.3-70b-versatile for Groq, gpt-4o-mini for OpenAI>
AI_BASE_URL=https://api.groq.com/openai/v1
```
If your password has special characters (`@`, `#`, `/`), URL-encode them (`@` → `%40`).
**Never upload `.env` to GitHub** (it is already in `.gitignore`).

### Create / update the tables

The repository contains all migrations (initial tables + admin side). Just run:

```powershell
flask db upgrade
```
This is safe on an existing database: it only ADDS the `users.role`, `users.is_active`, `users.last_login_at`
columns and the `categories` / `activity_logs` tables. Existing users become active plain users and
existing expenses are untouched.
(Only if you change `models.py` later: `flask db migrate -m "describe change"` then `flask db upgrade`.)

### Run

```powershell
flask seed-demo     # optional: demo user demo@smartspend.local / Demo@12345 with sample data
python run.py
```
Open http://127.0.0.1:5000

### Admin side (new)

Create the first administrator (you are asked for the password; it is hashed, never stored in code):

```powershell
flask create-admin --email you@example.com --name "Your Name"
```
Then log in at http://127.0.0.1:5000/login – admins are sent to `/admin/`.
If the email already belongs to a normal user, the command promotes it (after you confirm and enter that
account's password). All other admins are created from **Admin → Users** (role change asks for your password).

Admin pages: Dashboard (statistics + Chart.js), Users (search, filter, paginate, activate/deactivate, roles),
Categories (create, edit/rename, deactivate – expenses are preserved), System Monitoring (database, AI status
without secrets, runtime). Every `/admin/*` route is checked on the server: anonymous users are redirected to
login, ordinary users get HTTP 403. Admins cannot deactivate or demote themselves.

### Tests

```powershell
pytest
```
Tests use an in-memory database by default. To run them on PostgreSQL, create a separate
`smartspend_test` database and set `$env:TEST_DATABASE_URL="postgresql+psycopg://postgres:YOUR_PASSWORD@localhost:5432/smartspend_test"`.

## Push to GitHub

Create an empty repository on github.com first (no README), then:

```powershell
git init
git add .
git commit -m "Initial commit: SmartSpend"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```
Check `git status` first to confirm `.env` is not listed.

## Notes
- AI output and ML predictions are estimates, not professional financial advice.
- AI calls only ever receive summaries of the logged-in user's own data.
- API keys are read from the server environment and never reach browser JavaScript.
