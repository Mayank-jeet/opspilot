# OpsPilot — Autonomous AI Task Worker

OpsPilot is a prototype AI worker that carries out and **verifies** business tasks in a controlled, simulated company environment. Give it a task in plain English, for example *"Find the invoice from Acme Corp with amount lesser than 50000 and process it"* or *"Add a new invoice ACE-019 for Acme Corp, $2000, due after 1 month"*. It finds or creates the invoice, enters it into an accounting app through a real browser, pauses for human approval when the amount is high, and then proves the ledger holds the expected record.

It combines a React dashboard, FastAPI simulated business applications, and a LangGraph loop in which an LLM planner chooses one structured action at a time from observed state, while deterministic guards enforce the rules.

## Highlights

- **Plan, act, observe loop.** The LLM picks the next tool; the executor validates preconditions and safety rules before running it.
- **Real browser automation.** Playwright opens, fills and submits the simulated accounting form.
- **Human approval gate.** Invoices above ₹50,000 (INR equivalent) pause until a person approves or rejects. The model cannot approve its own transaction, and the API enforces the rule a second time.
- **Independent verification.** After submitting, the agent reads the accounting record back and checks its fields and `PROCESSED` status.
- **Create invoices two ways.** By prompt (the agent extracts the details), or manually with the *Create invoice* form in the inbox.
- **Any currency.** Amounts like `$2000`, `¥50000`, `€300` or `500 yen` are understood. Rates are live, with an offline fallback (see [Currency handling](#currency-handling)).
- **Duplicate handling.** Re-submitting the same invoice is detected and verified instead of resubmitted.
- **Failure recovery demo.** A one-shot injected tool failure is retried, with the whole sequence visible in the trace.

## Architecture

```text
React dashboard (Vite, localhost:5173)
    └── FastAPI (localhost:8000)
         ├── Simulated inbox, accounting API and browser pages
         ├── Currency service (live daily rates, cached, offline fallback)
         └── LangGraph: observe → plan → execute tool → observe
              ├── LLM structured action selection (OpenAI)
              ├── Playwright actions on the simulated accounting page
              ├── Deterministic checks and the approval threshold
              └── Independent accounting verification
```

## Dashboard

The home screen is for entering a task, watching its status, and handling a pending approval. **Company inbox**, **Accounting** and **Activity log** are separate pages. Phones use a bottom navigation bar and larger screens a side navigation, checked from 320px to 1920px widths.

## Quick start

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

## Try it

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

## Currency handling

- **Source.** Daily rates come from the free [fawazahmed0 currency API](https://github.com/fawazahmed0/exchange-api) (no key needed), through its CDN with a Cloudflare mirror as a fallback. Every currency it provides is accepted.
- **Resolution.** Codes (`JPY`), symbols (`$ € £ ¥ ₹ ₩ ₽`…) and names (`yen`, `Japanese Yen`) all work. `$` means USD and `¥` means JPY; write `CNY` or `yuan` for the Chinese yuan.
- **Storage.** An invoice keeps its own `amount` and `currency`, plus `amount_inr` and the rate details (`fx_rate`, `fx_date`, `fx_source`) used for the approval rule. The accounting record keeps the currency too.
- **Approval rule.** The ₹50,000 limit is applied to the INR equivalent, so $700 needs approval while ¥60,000 (about ₹33,000) does not.
- **Caching and fallback.** Rates are cached for an hour. If the API is unreachable, INR, USD, EUR, GBP and AED use fixed demo rates; other currencies return a clear error.
- **Daily rates.** These are end-of-day style rates, not tick-by-tick quotes.

## API overview

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

## Simulate a tool failure

Arm a one-time failure before starting a task. The next call to that tool fails, shows up in the activity trace, and is retried.

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/simulation/failure `
  -ContentType 'application/json' -Body '{"tool":"search_inbox"}'
```

Allowed tools: `search_inbox`, `read_invoice`, `create_invoice`, `check_accounting`, `open_accounting`, `fill_invoice`, `submit_invoice`, `verify_invoice`. The failure is consumed only when that tool is called. Disarm it with `Invoke-RestMethod -Method Delete -Uri http://localhost:8000/api/simulation/failure`.

## Safety model

- `search_inbox`, `read_invoice` and `create_invoice` work on the local inbox data. `create_invoice` validates the invoice number, vendor, amount and currency, computes dates in code (never in the LLM), and refuses to overwrite an existing invoice with different details.
- `check_accounting` prevents duplicate submission. An invoice already in accounting is verified, not resubmitted.
- `open_accounting`, `fill_invoice` and `submit_invoice` use Playwright on the simulated accounting page.
- The executor enforces action order and the approval threshold. The accounting API repeats the approval check using its own conversion.
- `verify_invoice` compares the stored record's fields, currency and status.
- An injected transient failure retries the same action up to two times. After that, the run stops with `RECOVERY_EXHAUSTED`.
- Execution is capped at a fixed number of steps.

## Tests

From `backend` (HTTP calls and the browser are mocked, so no network or API key is needed):

```powershell
python -m unittest discover -s tests -v
```

## Project structure

```text
backend/
  app/
    main.py            FastAPI app, inbox/accounting/currency endpoints
    currency.py        live rates, symbol and name resolution, INR conversion
    schemas.py         request and response models
    data.py            seed invoices, in-memory ledger
    simulated_apps.py  browser pages the agent operates
    agent/
      graph.py         LangGraph loop and deterministic workflow steps
      planner.py       LLM structured action planner
      executor.py      tools, safety rules, approval gate
      browser.py       Playwright adapter
      service.py       task runs and approval handling
      state.py         typed agent state and action schemas
  tests/
frontend/
  src/                 React dashboard (Vite)
```

## Limitations and next steps

- Playwright only drives the simulated local pages; no external company systems are connected.
- Invoices, accounting records and paused tasks are in memory, so a backend restart resets them. Run a single backend worker.
- The browser adapter targets `http://127.0.0.1:8000`, and CORS allows the local dashboard only.
- There is no authentication. The agent and failure-injection endpoints are open and intended for a local demo.
- The planner needs an OpenAI API key and can choose poorly; deterministic guards and final verification limit the impact.
- There is no persistent database, task queue, or evaluation dashboard.
- Next: persistence, deployment with authentication, broader recovery policies, live browser-state observation, and an evaluation report covering success, verification, recovery and human intervention.

## Demo checklist

1. Start the backend and frontend and confirm the dashboard shows the API as connected.
2. Run the default Acme task. Confirm it finds `AC-1042` and pauses for approval.
3. Approve it, then check the execution trace and the accounting page for verification.
4. Run the task again. The already-processed invoice is verified without a duplicate submission.
5. Run the "lesser than 50000" task to show amount filtering, then "lesser than 10000" to show the no-match response.
6. Run `Add a new invoice … $500 …` and then a large yen invoice, and note which one needs approval.
7. Arm a failure with `{"tool":"submit_invoice"}`, run a lower-value task, and confirm the trace shows `SIMULATED_FAILURE`, `RECOVERY_RETRY` and eventual verification.
8. Reject an approval to confirm nothing is submitted.

## Built with

Python, FastAPI, Pydantic, LangGraph, LangChain OpenAI, Playwright, httpx, React, Vite and Lucide. The default model is `gpt-4o-mini`; set `OPENAI_MODEL` to use another. Exchange rates: fawazahmed0/exchange-api.
