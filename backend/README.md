# OpsPilot API

Local simulated inbox, accounting and currency API, plus the LangGraph agent. Invoices and accounting records live in memory, so restarting the server resets them. Run a single worker.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
uvicorn app.main:app --reload
```

- Interactive API docs: http://localhost:8000/docs
- Simulated inbox: http://localhost:8000/simulated/inbox
- Simulated accounting: http://localhost:8000/simulated/accounting

To run agent tasks, copy the repository-root `.env.example` to `.env` and set `OPENAI_API_KEY`. The API reports a configuration error if the key is missing; the inbox, accounting and currency endpoints stay available.

Currency conversion uses a free public rates API and needs internet access. Without it, INR, USD, EUR, GBP and AED fall back to fixed demo rates.

Run the tests from this folder (no network or API key needed):

```powershell
python -m unittest discover -s tests -v
```

See the repository-root `README.md` for the full overview, endpoints and demo script.
