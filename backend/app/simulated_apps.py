from html import escape

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from .data import INVOICES

router = APIRouter(tags=["simulated browser applications"])


def _page(title: str, content: str) -> HTMLResponse:
    return HTMLResponse(f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} · OpsPilot Sim</title>
<style>
body{{font:16px system-ui,sans-serif;background:#f3f6fa;color:#17243a;margin:0;padding:32px}}
main{{max-width:760px;margin:auto;background:white;padding:28px;border-radius:14px;box-shadow:0 8px 30px #17243a12}}
a{{color:#155eef}}li{{padding:12px 0;border-bottom:1px solid #e5eaf1}}label{{display:block;font-weight:600;margin:16px 0 6px}}
input{{box-sizing:border-box;width:100%;padding:11px;border:1px solid #aab5c5;border-radius:7px;font:inherit}}
button{{margin-top:20px;padding:11px 18px;border:0;border-radius:7px;background:#155eef;color:white;font:inherit;font-weight:700;cursor:pointer}}
#submission-result{{margin-top:18px;white-space:pre-wrap}}.field{{padding:8px 0}}small{{color:#617089}}
@media(max-width:520px){{body{{padding:12px}}main{{padding:18px}}}}
</style></head><body><main>{content}</main></body></html>""")


@router.get("/simulated/inbox", response_class=HTMLResponse)
def simulated_inbox():
    rows = "".join(
        f'<li><a href="/simulated/inbox/{escape(item["id"])}">{escape(item["sender"])} — {escape(item["subject"])}</a>'
        f'<br><small>Received {escape(item["received_at"])}</small></li>'
        for item in sorted(INVOICES, key=lambda row: row["received_at"], reverse=True)
    )
    return _page("Company inbox", f"<h1>Company inbox</h1><p>Local simulated messages</p><ul>{rows}</ul>")


@router.get("/simulated/inbox/{message_id}", response_class=HTMLResponse)
def simulated_invoice(message_id: str):
    invoice = next((item for item in INVOICES if item["id"] == message_id), None)
    if not invoice:
        raise HTTPException(status_code=404, detail="Inbox message not found")
    fields = "".join(
        f'<div class="field"><b>{label}:</b> <span data-field="{key}">{escape(str(invoice[key]))}</span></div>'
        for key, label in (("vendor", "Vendor"), ("invoice_number", "Invoice Number"),
                           ("amount", "Amount"), ("currency", "Currency"), ("due_date", "Due Date"))
    )
    return _page("Invoice details", f'<p><a href="/simulated/inbox">← Inbox</a></p><h1>{escape(invoice["subject"])}</h1>{fields}')


@router.get("/simulated/accounting", response_class=HTMLResponse)
def simulated_accounting():
    content = """<h1>Accounting</h1><p>Local simulated invoice register</p>
<form id="invoice-form">
<label for="invoice_number">Invoice number</label><input id="invoice_number" name="invoice_number" required>
<label for="vendor">Vendor</label><input id="vendor" name="vendor" required>
<label for="amount">Amount</label><input id="amount" name="amount" type="number" min="1" required>
<label for="currency">Currency</label><input id="currency" name="currency" value="INR" required>
<label for="due_date">Due date</label><input id="due_date" name="due_date" type="date" required>
<button type="submit">Submit invoice</button></form><div id="submission-result" role="status" aria-live="polite"></div>
<script>
document.querySelector('#invoice-form').addEventListener('submit', async (event) => {
 event.preventDefault(); const form = event.currentTarget; const result = document.querySelector('#submission-result');
 const payload = Object.fromEntries(new FormData(form)); payload.amount = Number(payload.amount);
 try { const response = await fetch('/api/accounting/invoices', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
 const body = await response.json(); result.dataset.status = response.ok ? 'success' : 'error'; result.textContent = response.ok ? `${body.invoice_number} — ${body.status}` : body.detail; }
 catch (error) { result.dataset.status = 'error'; result.textContent = error.message; }
});
</script>"""
    return _page("Accounting", content)
