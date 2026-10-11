# OpsPilot — Autonomous AI Task Worker

OpsPilot is a prototype AI worker that carries out and **verifies** business tasks in a controlled, simulated company environment. Give it a task in plain English, for example *"Find the invoice from Acme Corp with amount lesser than 50000 and process it"* or *"Add a new invoice ACE-019 for Acme Corp, $2000, due after 1 month"*. It finds or creates the invoice, enters it into an accounting app through a real browser, pauses for human approval when the amount is high, and then proves the ledger holds the expected record.

The application combines a React dashboard, FastAPI simulated business applications, and a LangGraph loop in which an LLM planner chooses one structured action at a time from observed state, while deterministic guards enforce the rules.

🔗 **Live Application:** https://opspilot-mocha-xi.vercel.app

> The agent endpoints are protected by a demo password, because each task calls the OpenAI API. Ask me for the key; the site prompts for it the first time you run a task. The backend runs on a free Render instance, so the first load can take 30 to 60 seconds while it wakes up.

---

## Features

- Run business tasks from a plain-English instruction
- Plan, act, observe loop built with LangGraph
- LLM planner that picks one structured action at a time
- Deterministic guards that validate every action before it runs
- Real browser automation with Playwright on the simulated accounting form
- Human approval gate for invoices above ₹50,000 (INR equivalent)
- Approval rule enforced twice: by the agent executor and by the accounting API
- Independent verification of the accounting record after submission
- Create invoices by prompt or manually with the *Create invoice* form
- Multi-currency amounts such as `$2000`, `¥50000`, `€300` or `500 yen`
- Live daily exchange rates with caching and an offline fallback
- Duplicate invoice detection, verified instead of resubmitted
- One-shot failure injection with automatic retry, visible in the activity trace
- Step-by-step execution trace and activity log
- Responsive UI for desktop and mobile
- Demo-key protection on the costly agent endpoints
- Separate frontend and backend architecture

---

## Tech Stack

### Frontend

- React
- Vite
- Lucide React icons
- CSS
- JavaScript / JSX

### Backend

- Python 3.11
- FastAPI
- LangGraph
- LangChain
- Pydantic
- Uvicorn
- httpx

### AI Models

- OpenAI models (`gpt-4o-mini` by default) for structured action planning

### Browser Automation

- Playwright with headless Chromium

### Currency

- [fawazahmed0 exchange-api](https://github.com/fawazahmed0/exchange-api) for daily rates

### Other

- In-memory state for invoices, accounting records and paused tasks
- Docker for the backend deployment
- REST API communication between frontend and backend
- `unittest` for backend tests

---

# Project Architecture

The application is divided into two main parts:

```text
opspilot/
│
├── backend/
│   │
│   ├── app/
│   │   │
│   │   ├── agent/
│   │   │   ├── __init__.py
│   │   │   ├── api.py
│   │   │   ├── browser.py
│   │   │   ├── executor.py
│   │   │   ├── graph.py
│   │   │   ├── planner.py
│   │   │   ├── service.py
│   │   │   └── state.py
│   │   │
│   │   ├── __init__.py
│   │   ├── currency.py
│   │   ├── data.py
│   │   ├── main.py
│   │   ├── schemas.py
│   │   ├── security.py
│   │   └── simulated_apps.py
│   │
│   ├── tests/
│   │   ├── test_agent.py
│   │   ├── test_currency.py
│   │   └── test_security.py
│   │
│   ├── .dockerignore
│   ├── Dockerfile
│   ├── README.md
│   └── requirements.txt
│
│
├── frontend/
│   │
│   ├── src/
│   │   ├── App.jsx
│   │   ├── invoice-form.css
│   │   ├── main.jsx
│   │   └── styles.css
│   │
│   ├── index.html
│   ├── package-lock.json
│   └── package.json
│
│
├── .env.example
├── .gitignore
└── README.md
```

| File | Role |
|---|---|
| `main.py` | FastAPI app, inbox, accounting and currency endpoints, CORS |
| `currency.py` | Live rates, symbol and name resolution, INR conversion |
| `schemas.py` | Request and response models |
| `data.py` | Seed invoices and the in-memory ledger |
| `simulated_apps.py` | Browser pages the agent operates |
| `security.py` | Demo-key check for the costly endpoints |
| `agent/graph.py` | LangGraph loop and deterministic workflow steps |
| `agent/planner.py` | LLM structured action planner |
| `agent/executor.py` | Tools, safety rules and the approval gate |
| `agent/browser.py` | Playwright adapter |
| `agent/service.py` | Task runs and approval handling |
| `agent/state.py` | Typed agent state and action schemas |

## Workflow Overview

OpsPilot uses a **LangGraph loop** to turn a plain-English task into a verified record in the accounting app.

```text
User
 │
 ▼
React Dashboard
 │
 ▼
FastAPI Backend
 │
 ▼
Agent Task Started
 │
 ▼
Observe
 │
 │  Reads the current state of the task
 ▼
Planner (LLM)
 │
 │  Chooses the next structured action
 ▼
Executor
 │
 │  Checks order, preconditions and safety rules
 ▼
Tool
 │
 ├── search_inbox / read_invoice / create_invoice
 ├── check_accounting
 ├── open_accounting / fill_invoice / submit_invoice
 └── verify_invoice
 │
 ▼
Amount above ₹50,000?
 │
 ├── Yes ──▶ Pause for Human Approval ──▶ Approve or Reject
 │                                              │
 └── No ────────────────────────────────────────┤
                                                ▼
                                    Submit through Playwright
                                                │
                                                ▼
                                    Verify the Accounting Record
                                                │
                                                ▼
                                   Result and Execution Trace
                                                │
                                                ▼
                                              User
```

The loop repeats observe → plan → execute until the task is verified, rejected or stopped. Execution is capped at a fixed number of steps.

## Dashboard

The home screen is for entering a task, watching its status, and handling a pending approval. **Company inbox**, **Accounting** and **Activity log** are separate pages. Phones use a bottom navigation bar and larger screens a side navigation, checked from 320px to 1920px widths.

## Quick Start

Requirements: Python 3.11+, Node.js 20+, and an OpenAI API key for the agent.

### Backend (PowerShell)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
uvicorn app.main:app --reload
```

Copy the root `.env.example` to `.env` and set `OPENAI_API_KEY`. Without a key, the simulated apps still work, but starting an agent task returns a configuration error.

- API docs: http://localhost:8000/docs
- Simulated inbox: http://localhost:8000/simulated/inbox
- Simulated accounting: http://localhost:8000/simulated/accounting

### Frontend (second window)

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

## Try It

| Task | What happens |
|---|---|
| `Find the latest invoice from Acme Corp and process it.` | Finds AC-1042 (₹72,450), pauses for approval, then submits and verifies after you approve. |
| `Find the invoice from Acme Corp with amount lesser than 50000 and process it.` | Filters by amount, picks AC-1038 (₹48,900), and processes it with no approval needed. |
| `Find the invoice from Acme Corp with amount lesser than 10000 and process it.` | No invoice matches, so it reports that clearly and submits nothing. |
| `Add a new invoice ACE-019 for Acme Corp, $500, due after 1 month.` | Creates the invoice in USD, processes it (under ₹50,000, so no approval), and verifies it. |
| `Add a new invoice ACE-020 for Acme Corp, ¥200000.` | Creates it in JPY. The INR equivalent is above ₹50,000, so it asks for approval. |

Amount conditions in a task ("greater than", "under", "at least"…) compare the INR equivalent, so invoices in different currencies are comparable. If no amount is given when adding an invoice, it is created with amount 0 and the agent stops before submitting, because accounting needs a positive amount. Run the task again with the amount to complete it.

### Creating invoices manually

In **Company inbox**, click **Create invoice**. Only the invoice number and vendor are required.

| Field | Default |
|---|---|
| Amount | 0 |
| Currency | INR (type a code, a symbol such as `$` or `¥`, or a name such as `yen`) |
| Received at | now |
| Due date | one month after the received date |
| Sender | the vendor |
| Subject | `Invoice #<number>` |
| Message ID | `mail-<number>` |

A duplicate invoice number is rejected with a clear message. Saved invoices appear in the inbox, where **Enter into accounting** processes them by hand.

## Currency Handling

- **Source.** Daily rates come from the free [fawazahmed0 currency API](https://github.com/fawazahmed0/exchange-api) (no key needed), through its CDN with a Cloudflare mirror as a fallback. Every currency it provides is accepted.
- **Resolution.** Codes (`JPY`), symbols (`$ € £ ¥ ₹ ₩ ₽`…) and names (`yen`, `Japanese Yen`) all work. `$` means USD and `¥` means JPY; write `CNY` or `yuan` for the Chinese yuan.
- **Storage.** An invoice keeps its own `amount` and `currency`, plus `amount_inr` and the rate details (`fx_rate`, `fx_date`, `fx_source`) used for the approval rule. The accounting record keeps the currency too.
- **Approval rule.** The ₹50,000 limit is applied to the INR equivalent, so $700 needs approval while ¥60,000 (about ₹33,000) does not.
- **Caching and fallback.** Rates are cached for an hour. If the API is unreachable, INR, USD, EUR, GBP and AED use fixed demo rates; other currencies return a clear error.
- **Daily rates.** These are end-of-day style rates, not tick-by-tick quotes.

## API Overview

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Health check |
| `POST /api/tasks` | Run an agent task |
| `POST /api/tasks/{id}/approval` | Approve or reject a paused task |
| `GET /api/inbox/messages` | Search the inbox (`sender`, `query`) |
| `GET /api/inbox/messages/{id}` | Read one message |
| `POST /api/inbox/messages` | Create an invoice (manual form) |
| `GET /api/accounting/invoices` | List accounting records |
| `GET /api/accounting/invoices/{number}` | Read one record |
| `POST /api/accounting/invoices` | Submit an invoice (enforces approval above ₹50,000 INR-equivalent) |
| `GET /api/currencies` | All supported currencies |
| `GET /api/rates/{currency}` | INR per 1 unit, with date and source |
| `POST` / `DELETE /api/simulation/failure` | Arm or disarm a one-shot tool failure |

## Simulate a Tool Failure

Arm a one-time failure before starting a task. The next call to that tool fails, shows up in the activity trace, and is retried.

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/simulation/failure `
  -ContentType 'application/json' -Body '{"tool":"search_inbox"}'
```

Allowed tools: `search_inbox`, `read_invoice`, `create_invoice`, `check_accounting`, `open_accounting`, `fill_invoice`, `submit_invoice`, `verify_invoice`. The failure is consumed only when that tool is called. Disarm it with `Invoke-RestMethod -Method Delete -Uri http://localhost:8000/api/simulation/failure`. On a deployment where `DEMO_KEY` is set, add `-Headers @{ 'X-Demo-Key' = '<key>' }` to these calls.

## Safety Model

- `search_inbox`, `read_invoice` and `create_invoice` work on the local inbox data. `create_invoice` validates the invoice number, vendor, amount and currency, computes dates in code (never in the LLM), and refuses to overwrite an existing invoice with different details.
- `check_accounting` prevents duplicate submission. An invoice already in accounting is verified, not resubmitted.
- `open_accounting`, `fill_invoice` and `submit_invoice` use Playwright on the simulated accounting page.
- The executor enforces action order and the approval threshold. The accounting API repeats the approval check using its own conversion.
- `verify_invoice` compares the stored record's fields, currency and status.
- An injected transient failure retries the same action up to two times. After that, the run stops with `RECOVERY_EXHAUSTED`.
- Execution is capped at a fixed number of steps.
- The task, approval and failure-injection endpoints require a demo key when `DEMO_KEY` is set.

## Tests

From `backend` (HTTP calls and the browser are mocked, so no network or API key is needed):

```powershell
python -m unittest discover -s tests -v
```

## Deployment

OpsPilot is deployed using **Vercel** and **Render**.

### Frontend

The React frontend is deployed on **Vercel**.

🔗 **Live Application:** https://opspilot-mocha-xi.vercel.app

### Backend

The FastAPI backend is deployed as a Render **Docker web service**. The frontend communicates with it through REST API endpoints.

### Deployment Architecture

```text
User
  │
  ▼
Vercel
(React Frontend)
  │
  │ REST API  (X-Demo-Key header)
  ▼
Render Docker Web Service
(FastAPI Backend)
  │
  ├── LangGraph
  ├── OpenAI
  └── Playwright (Chromium)
        │
        ▼
   Simulated company pages
   (served by the same backend)
```

### Backend settings

Root Directory `backend`, Health Check Path `/api/health`.

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | OpenAI key for the planner (set as a secret) |
| `OPENAI_MODEL` | Model name, default `gpt-4o-mini` |
| `DEMO_KEY` | Password required in the `X-Demo-Key` header for `/api/tasks`, `/api/tasks/{id}/approval` and `/api/simulation/failure`. If unset (local development), the gate is off. |
| `CORS_ORIGINS` | Comma-separated frontend origins allowed to call the API, with no trailing slash |
| `INTERNAL_BASE_URL` | Optional. Where the agent's browser reaches the app; defaults to `http://127.0.0.1:$PORT` |

The image installs Chromium with `playwright install --with-deps chromium` and starts uvicorn with a single worker, because state is in memory. Chromium is launched with `--disable-dev-shm-usage`, since Docker's shared memory is small.

### Frontend settings

Root Directory `frontend`, Framework Preset Vite, Build Command `npm run build`, Output Directory `dist`.

| Variable | Purpose |
|---|---|
| `VITE_API_URL` | Backend URL with no trailing slash. It is read at build time, so redeploy the frontend after changing it. |

When the API returns 401, the dashboard asks for the demo key and keeps it in `sessionStorage` for the browser session.

## Limitations

- Playwright only drives the simulated local pages; no external company systems are connected.
- Invoices, accounting records and paused tasks are in memory, so a backend restart or redeploy resets them. Run a single backend worker.
- On the free Render plan, the service sleeps when idle and 512 MB of memory is tight for Chromium.
- Authentication is a single shared demo key on the task and failure-injection endpoints, not per-user accounts. The inbox and accounting endpoints and `/docs` are public, which is acceptable for a demo with simulated data.
- The planner needs an OpenAI API key, and API usage depends on the limits and billing of that account.
- The planner can choose poorly; deterministic guards and final verification limit the impact.
- Exchange rates are daily, with fixed fallback rates for only a few currencies when the rate API is unreachable.
- There is no persistent database, task queue, or evaluation dashboard.

## Future Improvements

- Persistent database-backed storage for invoices, ledger and tasks
- Per-user authentication
- Streaming agent progress to the dashboard
- Broader recovery policies
- Live browser-state observation
- An evaluation report covering success, verification, recovery and human intervention

## Demo Checklist

1. Start the backend and frontend and confirm the dashboard shows the API as connected.
2. Run the default Acme task. Confirm it finds `AC-1042` and pauses for approval.
3. Approve it, then check the execution trace and the accounting page for verification.
4. Run the task again. The already-processed invoice is verified without a duplicate submission.
5. Run the "lesser than 50000" task to show amount filtering, then "lesser than 10000" to show the no-match response.
6. Run `Add a new invoice … $500 …` and then a large yen invoice, and note which one needs approval.
7. Arm a failure with `{"tool":"submit_invoice"}`, run a lower-value task, and confirm the trace shows `SIMULATED_FAILURE`, `RECOVERY_RETRY` and eventual verification.
8. Reject an approval to confirm nothing is submitted.

## Built With

Python, FastAPI, Pydantic, LangGraph, LangChain OpenAI, Playwright, httpx, React, Vite and Lucide. The default model is `gpt-4o-mini`; set `OPENAI_MODEL` to use another. Exchange rates: fawazahmed0/exchange-api.

## Author

### Mayank Jeet

- GitHub: [@Mayank-jeet](https://github.com/Mayank-jeet)
- LinkedIn: [Mayank Jeet](https://www.linkedin.com/in/mayank-jeet-211583364/)
