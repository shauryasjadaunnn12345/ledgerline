# Ledgerline

**Invoice Dispute Investigator** — a workspace for collecting invoice evidence, checking contract pricing, reconciling payments, and documenting reviewer decisions.

Live frontend: [ledgerline.vercel.app](https://ledgerline.vercel.app)

> Ledgerline is a demonstration project. The Customer/Reviewer switch is a UI role toggle, not authentication. Do not enter real customer, payment, or invoice data until authentication, authorization, and production data protections are in place.

## What it does

- Opens invoice dispute cases and tracks case status.
- Collects invoice lines, contract pricing rules, usage events, and payment/adjustment records.
- Recalculates invoice totals and outstanding balances using deterministic decimal arithmetic.
- Optionally requests a source-cited written interpretation from OpenRouter. The default model selector is `openrouter/free`; free model availability and rate limits are controlled by OpenRouter.
- Supports reviewer actions and records mock adjustments. Mock adjustments do not transfer money.
- Stores local development data in SQLite.

## Technology

- Frontend: React, Vite, Tailwind CSS, Axios
- Backend: FastAPI, SQLAlchemy, Pydantic
- Local database: SQLite
- Optional AI interpretation: OpenRouter; Mistral is retained as a fallback provider

## Run locally

Use separate terminals from the repository root.

### 1. Configure and start the backend

```powershell
Copy-Item backend\.env.example backend\.env
```

Edit `backend/.env` locally and set `OPENROUTER_API_KEY` to your own key. Keep the key private and do not commit `.env`.

```powershell
python -m venv backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
$env:BILLING_AI_ENABLED = "true"
.\backend\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

The API health check is at <http://127.0.0.1:8000/health/> and interactive API documentation is at <http://127.0.0.1:8000/docs>.

If you do not have an AI key, set `BILLING_AI_ENABLED=false`; deterministic invoice calculations still work.

### 2. Configure and start the frontend

In another terminal:

```powershell
Set-Location frontend
npm install
$env:VITE_API_URL = "http://127.0.0.1:8000"
npm run dev
```

Open the local URL printed by Vite, usually <http://localhost:5173>.

## Try a demo case

1. In the customer view, create a dispute:
   - Customer ID: `demo-customer-001`
   - Disputed amount: `120.00`
   - Description: `I was charged more than the agreed hosting rate.`
2. Add an **Invoice line item**:
   - Invoice line ID: `LINE-001`
   - Description: `Monthly hosting`
   - Quantity: `10`
   - Unit price: `12.00`
   - Billed amount: `120.00`
3. Add a **Pricing or contract rule**:
   - Matching line ID: `LINE-001`
   - Rule: `Agreed monthly hosting rate`
   - Allowed unit price: `10.00`
   - Quantity basis: `Invoice quantity`
4. Add **Payment or adjustment** evidence:
   - Type: `Payment`
   - Amount: `50.00`
   - Reference: `PAY-DEMO-001`
   - Description: `Demo payment`
5. Click **Recalculate invoice**.

Expected values: invoice total `$120.00`, recalculated total `$100.00`, original balance `$70.00`, recalculated balance `$50.00`. AI interpretation is optional and may be unavailable when the selected provider/model is rate-limited.

## Deploy

The example hosting setup is Vercel for the frontend and Render for the API and PostgreSQL database.

### Before deploying

1. Push the reviewed project changes to a GitHub repository. Do not commit `backend/.env`, API keys, local databases, or real customer data.
2. Revoke any OpenRouter/Mistral API key that was ever committed or exposed; use a newly issued key only in the backend host's secret settings.
3. Decide whether this deployment is a **fictional-data demo** or will handle real users. This code currently has no authentication, reviewer authorization, or tenant isolation. A public deployment is not safe for real invoice/customer data. Protecting the Vercel frontend alone does not secure the API.
4. Remove `MISTRAL_API_KEY` from backend host settings if you intend to use OpenRouter exclusively.

### Deploy the API and database on Render

1. Create a managed PostgreSQL database in Render. Use its **internal** connection URL for a service in the same Render region.
2. Create a Render **Web Service** connected to the GitHub repository. Set the service root to the repository root.
3. Configure:
   - Build command: `pip install -r backend/requirements.txt`
   - Start command: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
   - Health check path: `/health/`
4. Set these environment variables in Render (use its secret fields for credentials):
   - `DATABASE_URL`: Render's PostgreSQL URL. The backend converts `postgres://` / `postgresql://` to the `psycopg` SQLAlchemy URL format.
   - `FRONTEND_ORIGINS`: initially a temporary Vercel preview origin or the eventual canonical site origin, with no trailing slash. Separate exact origins with commas.
   - `BILLING_AI_ENABLED`: `true` to request optional AI interpretations.
   - `OPENROUTER_API_KEY`: your OpenRouter key.
   - `OPENROUTER_MODEL`: `openrouter/free` (optional; this is also the default).
5. Deploy and confirm `https://<render-service>.onrender.com/health/` responds with `{"status":"ok"}`.

The backend calls `Base.metadata.create_all()` at startup. It creates missing tables in a new database but does **not** migrate an existing schema. Back up any existing database and plan a migration workflow before schema changes or production data.

### Deploy the frontend on Vercel

1. Import the GitHub repository into Vercel.
2. Set the project **Root Directory** to `frontend`.
3. Configure:
   - Framework preset: Vite (or Other)
   - Build command: `npm run build`
   - Output directory: `dist`
   - Environment variable `VITE_API_URL`: the Render API origin, e.g. `https://<render-service>.onrender.com` (no trailing slash)
4. Deploy. Set Render's `FRONTEND_ORIGINS` to the final origin `https://ledgerline.vercel.app`. Include your custom domain's exact `https://` origin too, if applicable.
5. Redeploy/restart the Render backend after changing `FRONTEND_ORIGINS`. Avoid wildcard origins.

### Verify deployment

1. Open `https://ledgerline.vercel.app` and confirm the page loads.
2. Open the Render `/health/` URL and confirm the health check passes.
3. Create a **fictional demo** case, add an invoice line and pricing rule, and confirm the deterministic recalculated total.
4. Check Render logs for database or CORS errors. AI may return `unavailable` when OpenRouter free models are rate-limited; deterministic billing calculations continue to work.
5. Confirm credentials do not appear in browser assets, frontend environment variables, Git history, or deployment logs. `VITE_*` variables are public to browser users.

**Do not use real data until authentication and authorization are implemented and enforced by every API endpoint.** CORS restricts browser origins only; it is not access control. Add backups/retention, monitoring, rate limiting, and a database migration process before operating this as a production service.

## Development checks

```powershell
Set-Location frontend
npm run lint
npm run build
```

From the repository root, run the focused backend unit tests with the configured Python environment:

```powershell
.\backend\.venv\Scripts\python.exe -m unittest backend.services.test_billing_analysis backend.services.test_llm_parser backend.services.test_disputes backend.services.test_database
```

## Security and data notes

- Never commit `.env`, API keys, database files, or real customer information.
- Keep OpenRouter/Mistral API keys on the backend only; never expose them through `VITE_*` variables.
- If a key was committed or otherwise exposed, revoke it and replace it.
- The current app does not implement user authentication, reviewer authorization, or tenant-level case access. The public demo must not be treated as a secure case-management system.
- Mock adjustment records are for workflow testing only and do not issue refunds or credits.
