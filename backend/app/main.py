import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .data import ACCOUNTING_RECORDS, APPROVED_SUBMISSIONS,INVOICES,search_invoices
from .schemas import InvoiceCreate, InvoiceRecord, InvoiceSubmission, SimulationFailureRequest
from .agent.api import router as agent_router
from .agent.executor import APPROVAL_THRESHOLD, _add_months
from .currency import get_rate, inr_fields, list_currencies, normalize_currency, to_inr
from .agent import executor
from .simulated_apps import router as simulated_apps_router
from .security import require_demo_key

CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    *[o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()],
]


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    ACCOUNTING_RECORDS.clear()
    APPROVED_SUBMISSIONS.clear()


app = FastAPI(title="OpsPilot Simulated Company API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "X-Demo-Key"],
)
app.include_router(agent_router)
app.include_router(simulated_apps_router)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "opspilot-simulated-company"}


@app.post("/api/simulation/failure", dependencies=[Depends(require_demo_key)])
def arm_simulated_failure(request: SimulationFailureRequest):
    """Make the next matching agent tool call fail once, for recovery demos."""
    executor.FAIL_NEXT_TOOL = request.tool
    return {"armed": True, "tool": request.tool}


@app.delete("/api/simulation/failure", dependencies=[Depends(require_demo_key)])
def clear_simulated_failure():
    """Disarm a failure before the matching tool is called."""
    executor.FAIL_NEXT_TOOL = None
    return {"armed": False}


@app.get("/api/inbox/messages")
def search_inbox(sender: str | None = None, query: str = ""):
    """Search the local inbox and return message summaries, newest first."""
    return search_invoices(sender=sender, query=query)


@app.get("/api/inbox/messages/{message_id}")
def read_invoice(message_id: str):
    for item in INVOICES:
        if item["id"] == message_id:
            return item
    raise HTTPException(status_code=404, detail="Inbox message not found")


@app.get("/api/currencies")
def list_supported_currencies():
    """Every currency the live currency API provides (popular ones first)."""
    names = list_currencies()
    popular = [code for code in ("INR", "USD", "EUR", "GBP", "AED") if code in names]
    rest = sorted(code for code in names if code not in popular)
    return [{"code": code, "name": names[code]} for code in [*popular, *rest]]


@app.get("/api/rates/{currency}")
def read_rate(currency: str):
    """INR per 1 unit of the currency, with the date and source of the rate."""
    try:
        code = normalize_currency(currency)
        return {"currency": code, **get_rate(code)}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/inbox/messages", status_code=201)
def create_inbox_message(payload: InvoiceCreate):
    """Manual 'Create invoice' form: store a new invoice message in the inbox."""
    number = payload.invoice_number.upper()
    if any(row["invoice_number"].upper() == number for row in INVOICES) or number in ACCOUNTING_RECORDS:
        raise HTTPException(status_code=409, detail=f"Invoice {number} already exists")
    message_id = payload.id or f"mail-{number.lower()}"
    if any(row["id"] == message_id for row in INVOICES):
        raise HTTPException(status_code=409, detail=f"Message id {message_id} already exists")
    received = (payload.received_at or datetime.now()).astimezone()  # naive input = server local time
    due = payload.due_date or _add_months(received.date(), 1)
    if due < received.date():
        raise HTTPException(status_code=422, detail="Due date cannot be before the received date")
    try:
        currency = normalize_currency(payload.currency)
        fx_fields = inr_fields(payload.amount, currency)  # INR equivalent + rate used, for the approval rule
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    row = {"id": message_id, "sender": payload.sender or payload.vendor,
           "subject": payload.subject or f"Invoice #{number}",
           "received_at": received.isoformat(timespec="seconds"), "vendor": payload.vendor,
           "invoice_number": number, "amount": payload.amount,
           "currency": currency, "due_date": due.isoformat(), **fx_fields}
    INVOICES.append(row)
    return row


@app.get("/api/accounting/invoices", response_model=list[InvoiceRecord])
def list_accounting_invoices():
    return list(ACCOUNTING_RECORDS.values())


@app.get("/api/accounting/invoices/{invoice_number}")
def get_accounting_invoice(invoice_number: str):
    record = ACCOUNTING_RECORDS.get(invoice_number)
    if not record:
        raise HTTPException(status_code=404, detail="Invoice not found in accounting")
    return record


@app.post("/api/accounting/invoices", response_model=InvoiceRecord, status_code=201)
def submit_invoice(payload: InvoiceSubmission):
    existing = ACCOUNTING_RECORDS.get(payload.invoice_number)
    if existing:
        raise HTTPException(status_code=409, detail="Invoice has already been processed")
    try:
        currency = normalize_currency(payload.currency)
        amount_inr = to_inr(payload.amount, currency)  # the approval rule is always in INR
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    submitted = {**payload.model_dump(mode="json"), "currency": currency}
    if amount_inr > APPROVAL_THRESHOLD:
        approved_payload = APPROVED_SUBMISSIONS.get(payload.invoice_number)
        if approved_payload != submitted:
            raise HTTPException(status_code=403, detail="Human approval is required for invoices above ₹50,000 (INR equivalent). Submit through an approved agent task.")
        del APPROVED_SUBMISSIONS[payload.invoice_number]
    record = {**submitted, "amount_inr": amount_inr, "status": "PROCESSED"}
    ACCOUNTING_RECORDS[payload.invoice_number] = record
    return record
