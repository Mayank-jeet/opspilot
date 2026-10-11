"""Deterministic sample data for OpsPilot's local company environment."""

import re

INVOICES = [
    {
        "id": "mail-kbc-5001",
        "sender": "KBC Crop",
        "subject": "Invoice #KBC-5001",
        "received_at": "2026-10-08T09:00:00+05:30",
        "vendor": "KBC Crop",
        "invoice_number": "KBC-5001",
        "amount": 70000,
        "currency": "INR",
        "due_date": "2026-10-22",
    },
    {
        "id": "mail-ac-1042",
        "sender": "Acme Corp",
        "subject": "Invoice #AC-1042",
        "received_at": "2026-10-04T09:30:00+05:30",
        "vendor": "Acme Corporation",
        "invoice_number": "AC-1042",
        "amount": 72450,
        "currency": "INR",
        "due_date": "2026-10-15",
    },
    {
        "id": "mail-ac-1038",
        "sender": "Acme Corp",
        "subject": "Invoice #AC-1038",
        "received_at": "2026-09-18T11:00:00+05:30",
        "vendor": "Acme Corporation",
        "invoice_number": "AC-1038",
        "amount": 48900,
        "currency": "INR",
        "due_date": "2026-10-01",
    },
    {
        "id": "mail-globex-2201",
        "sender": "Globex",
        "subject": "Monthly Invoice #GX-2201",
        "received_at": "2026-10-03T15:15:00+05:30",
        "vendor": "Globex",
        "invoice_number": "GX-2201",
        "amount": 18300,
        "currency": "INR",
        "due_date": "2026-10-20",
    },
    {
        "id": "mail-umbrella-801",
        "sender": "Umbrella Ltd",
        "subject": "Payment Reminder #UM-801",
        "received_at": "2026-10-02T08:45:00+05:30",
        "vendor": "Umbrella Ltd",
        "invoice_number": "UM-801",
        "amount": 12600,
        "currency": "INR",
        "due_date": "2026-10-25",
    },
]

_NON_SEARCH_TERMS = {
    "a", "an", "and", "accounting", "find", "for", "from", "get", "give",
    "i", "into", "it", "latest", "me", "most", "newest", "of", "please",
    "process", "processed", "processing", "recent", "record", "show", "the", "to",
}


def search_invoices(sender: str | None = None, query: str = "") -> list[dict]:
    """Match literal content terms while ignoring common task-intent words."""
    sender_term = (sender or "").strip().casefold()
    query_terms = [term for term in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", query.casefold())
                   if term not in _NON_SEARCH_TERMS]
    matches = []
    for invoice in INVOICES:
        sender_text = invoice["sender"].casefold()
        searchable_text = f"{invoice['subject']} {invoice['sender']}".casefold()
        if sender_term and sender_term not in sender_text:
            continue
        if all(term in searchable_text for term in query_terms):
            matches.append(invoice)
    return sorted(matches, key=lambda invoice: invoice["received_at"], reverse=True)

# In-memory for Day 1; a restart resets the simulated accounting system.
ACCOUNTING_RECORDS: dict[str, dict] = {}

# One-time, exact-field approvals granted through the agent's human approval step.
APPROVED_SUBMISSIONS: dict[str, dict] = {}
