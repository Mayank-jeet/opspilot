from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class InvoiceSubmission(BaseModel):
    invoice_number: str = Field(min_length=1)
    vendor: str = Field(min_length=1)
    amount: int = Field(gt=0)  # in `currency`
    currency: str = Field(default="INR", min_length=2, max_length=12)
    due_date: date


class InvoiceRecord(InvoiceSubmission):
    amount_inr: int | None = None  # INR equivalent when the record was filed
    status: str


class InvoiceCreate(BaseModel):
    """Manual 'Create invoice' form. Only invoice_number and vendor are required."""

    model_config = ConfigDict(str_strip_whitespace=True)

    invoice_number: str = Field(min_length=1, max_length=40)
    vendor: str = Field(min_length=1, max_length=120)
    amount: int = Field(default=0, ge=0)  # in `currency`
    currency: str = Field(default="INR", min_length=1, max_length=40)  # code, symbol ($, ¥) or name (yen)
    due_date: date | None = None          # default: one month after received_at
    received_at: datetime | None = None   # default: now
    id: str | None = None                 # default: mail-<invoice number>
    sender: str | None = None             # default: vendor
    subject: str | None = None            # default: Invoice #<invoice number>


class SimulationFailureRequest(BaseModel):
    tool: Literal[
        "search_inbox", "read_invoice", "create_invoice", "check_accounting", "open_accounting",
        "fill_invoice", "submit_invoice", "verify_invoice",
    ]
