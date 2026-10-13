import calendar
from datetime import date, datetime, timedelta
from typing import Any

from ..data import ACCOUNTING_RECORDS, INVOICES, search_invoices
from .state import AgentAction, AgentState

APPROVAL_THRESHOLD = 50_000
MAX_AGENT_STEPS = 12
MAX_TOOL_RETRIES = 2
FAIL_NEXT_TOOL: str | None = None


def _event(state: AgentState, event: str, detail: str, **extra: Any) -> list[dict[str, Any]]:
    item = {"time": datetime.now().astimezone().isoformat(timespec="seconds"), "event": event, "detail": detail, **extra}
    return [*state.get("execution_history", []), item]


def _fail(state: AgentState, message: str, event: str = "TOOL_FAILURE") -> dict[str, Any]:
    return {
        "current_observation": f"Tool error: {message}",
        "errors": [*state.get("errors", []), message],
        "execution_history": _event(state, event, message),
    }

def _add_months(start: date, months: int) -> date:
    """Calendar-aware month addition (Jan 31 + 1 month -> Feb 28/29)."""
    index = start.month - 1 + months
    year, month = start.year + index // 12, index % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))

def execute_action(state: AgentState, action: AgentAction) -> dict[str, Any]:
    """Run one allow-listed tool after deterministic checks and policy gates."""
    args = action.arguments.model_dump(exclude_none=True)
    if action.tool == "finish":
        verified = (state.get("verification_result") or {}).get("success", False)
        if verified:
            number = (state.get("invoice") or {}).get("invoice_number")
            already = any(i.get("event") == "ALREADY_PROCESSED" for i in state.get("execution_history", []))
            summary = (f"{number} was already processed; nothing new was submitted. Verified it is PROCESSED in accounting."
                       if already else f"Verified {number} is PROCESSED in accounting.")
            return {"completed": True, "failed": False, "final_summary": summary,
                    "current_observation": summary, "execution_history": _event(state, "TASK_COMPLETED", summary)}
        summary = action.reason or "The task ended without independent verification."
        return {"completed": False, "failed": True, "final_summary": summary,
                "current_observation": summary, "execution_history": _event(state, "TASK_FAILED", summary)}

    global FAIL_NEXT_TOOL
    if FAIL_NEXT_TOOL == action.tool:
        failed_tool = FAIL_NEXT_TOOL
        FAIL_NEXT_TOOL = None
        return _fail(state, f"Injected one-time simulation failure in {failed_tool}.", event="SIMULATED_FAILURE")

    if action.tool == "search_inbox":
        sender = str(args.get("sender", "")).strip()
        query = str(args.get("query", "")).strip()
        matches = search_invoices(sender=sender, query=query)
        return {"search_results": matches, "current_observation": f"Found {len(matches)} matching messages, newest first.",
                "execution_history": _event(state, "TOOL_SUCCESS", f"search_inbox found {len(matches)} messages", tool="search_inbox")}

    if action.tool == "create_invoice":
        number = str(args.get("invoice_number", "")).strip().upper()
        vendor = str(args.get("vendor", "")).strip()
        amount = args.get("amount", 0)  # defaults to 0 when the task gives no amount
        if not number or not vendor:
            return _fail(state, "create_invoice requires invoice_number and vendor")
        if not isinstance(amount, int) or amount < 0:
            return _fail(state, "create_invoice amount must be a whole number of INR (0 or more)")
        now = datetime.now().astimezone()
        today = now.date()
        try:
            if args.get("due_date"):
                due, exact_due = date.fromisoformat(args["due_date"]), True
            elif args.get("due_in_months") is not None:
                due, exact_due = _add_months(today, args["due_in_months"]), False
            elif args.get("due_in_days") is not None:
                due, exact_due = today + timedelta(days=args["due_in_days"]), False
            else:
                due, exact_due = _add_months(today, 1), False  # default: one month from now
        except (ValueError, OverflowError):
            return _fail(state, "Could not work out a valid due date (use YYYY-MM-DD or a month/day offset)")
        if due < today:
            return _fail(state, "Due date cannot be before the received date")

        existing = next((row for row in INVOICES if row["invoice_number"].upper() == number), None)
        if existing is None and number in ACCOUNTING_RECORDS:
            return _fail(state, f"Invoice number {number} already exists in accounting; it was not created again")
        if existing:
            diffs, fill_amount = [], False
            if existing["vendor"].casefold() != vendor.casefold():
                diffs.append(f"vendor {existing['vendor']} vs {vendor}")
            if amount > 0 and existing["amount"] != amount:
                if existing["amount"] == 0 and number not in ACCOUNTING_RECORDS:
                    fill_amount = True  # earlier created with the default amount 0; complete it now
                else:
                    diffs.append(f"amount {existing['amount']} vs {amount}")
            if exact_due and existing["due_date"] != due.isoformat():
                diffs.append(f"due date {existing['due_date']} vs {due.isoformat()}")
            if diffs:
                return _fail(state, f"Invoice {number} already exists with different details ({'; '.join(diffs)}); nothing was changed")
            if fill_amount:
                existing["amount"] = amount
            note = "filled in the missing amount" if fill_amount else "reused it instead of creating a duplicate"
            return {"invoice": dict(existing), "search_results": [dict(existing)],
                    "current_observation": f"Invoice {number} already exists; {note}.",
                    "execution_history": _event(state, "TOOL_SUCCESS", f"create_invoice: {number} already exists; {note}", tool="create_invoice")}

        row = {"id": f"mail-{number.lower()}", "sender": vendor, "subject": f"Invoice #{number}",
               "received_at": now.isoformat(timespec="seconds"), "vendor": vendor, "invoice_number": number,
               "amount": amount, "currency": "INR", "due_date": due.isoformat()}
        INVOICES.append(row)
        return {"invoice": dict(row), "search_results": [dict(row)],
                "current_observation": f"Created invoice {number} from {vendor} for {amount} INR, due {row['due_date']}.",
                "execution_history": _event(state, "TOOL_SUCCESS", f"create_invoice added {number} ({amount} INR, due {row['due_date']})", tool="create_invoice")}
    
    if action.tool == "read_invoice":
        message_id = args.get("message_id")
        selected = next((row for row in state.get("search_results", []) if row["id"] == message_id), None)
        if selected is None:
            return _fail(state, "read_invoice requires a message_id returned by search_inbox")
        return {"invoice": dict(selected), "current_observation": f"Read invoice {selected['invoice_number']} from {selected['vendor']}.",
                "execution_history": _event(state, "TOOL_SUCCESS", f"read_invoice read {selected['invoice_number']}", tool="read_invoice")}

    invoice = state.get("invoice")
    invoice_number = args.get("invoice_number")
    if not invoice or invoice_number != invoice.get("invoice_number"):
        return _fail(state, f"{action.tool} requires the currently read invoice number")

    if action.tool == "check_accounting":
        record = ACCOUNTING_RECORDS.get(invoice_number)
        if record:
            valid = all(record.get(k) == invoice.get(k) for k in ("invoice_number", "vendor", "amount", "due_date"))
            if not valid or record.get("status") != "PROCESSED":
                return _fail(state, "Existing accounting record does not match the invoice")
            return {"current_observation": f"Invoice {invoice_number} is already processed and matches; no submission was made. Verify it independently.",
                    "accounting_checked": True,
                    "execution_history": _event(state, "ALREADY_PROCESSED", f"{invoice_number} already exists; skipped submit")}
        return {"accounting_checked": True, "current_observation": f"Invoice {invoice_number} is not yet in accounting.",
                "execution_history": _event(state, "TOOL_SUCCESS", f"check_accounting found no {invoice_number} record", tool="check_accounting")}

    if action.tool == "open_accounting":
        if not state.get("accounting_checked"):
            return _fail(state, "check_accounting must run before opening accounting")
        try:
            from .browser import open_accounting_page
            title = open_accounting_page()
        except Exception as exc:
            return _fail(state, f"Could not open simulated accounting in Playwright: {exc}")
        return {"accounting_opened": True, "current_observation": f"Opened {title} in the browser.",
                "execution_history": _event(state, "TOOL_SUCCESS", "Opened simulated accounting with Playwright", tool="open_accounting")}

    if action.tool == "fill_invoice":
        if not state.get("accounting_checked") or not state.get("accounting_opened"):
            return _fail(state, "open_accounting must succeed before filling the invoice form")
        try:
            from .browser import fill_invoice_form
            filled_number = fill_invoice_form(invoice)
        except Exception as exc:
            return _fail(state, f"Could not fill the accounting form with Playwright: {exc}")
        if filled_number != invoice_number:
            return _fail(state, "The accounting form did not retain the expected invoice number")
        return {"invoice_form_filled": True, "current_observation": f"Filled the accounting form for {invoice_number}.",
                "execution_history": _event(state, "TOOL_SUCCESS", f"Filled form for {invoice_number} with Playwright", tool="fill_invoice")}

    if action.tool == "submit_invoice":
        if not state.get("accounting_checked"):
            return _fail(state, "check_accounting must confirm there is no existing record before submission")
        if not state.get("accounting_opened") or not state.get("invoice_form_filled"):
            return _fail(state, "open_accounting and fill_invoice must succeed before submission")
        if (state.get("verification_result") or {}).get("success"):
            return {"current_observation": "Invoice is already verified; duplicate submission was skipped.",
                    "execution_history": _event(state, "DUPLICATE_SKIPPED", f"Skipped duplicate submit for {invoice_number}")}
        if invoice["amount"] > APPROVAL_THRESHOLD and state.get("approval_status") != "approved":
            detail = f"{invoice_number} is {invoice['amount']} INR, above the {APPROVAL_THRESHOLD} INR approval threshold."
            return {"approval_status": "pending", "current_observation": detail,
                    "execution_history": _event(state, "APPROVAL_REQUIRED", detail, invoice_number=invoice_number, amount=invoice["amount"])}
        existing = ACCOUNTING_RECORDS.get(invoice_number)
        if existing:
            return _fail(state, f"{invoice_number} already exists; check and verify it instead of resubmitting")
        try:
            from .browser import submit_invoice_form
            record = submit_invoice_form(invoice)
        except Exception as exc:
            return _fail(state, f"Playwright could not submit {invoice_number}: {exc}")
        return {"current_observation": f"Accounting browser reported {record['invoice_number']} as {record['status']}.",
                "execution_history": _event(state, "TOOL_SUCCESS", f"Clicked submit for {invoice_number} in Playwright", tool="submit_invoice")}

    if action.tool == "verify_invoice":
        record = ACCOUNTING_RECORDS.get(invoice_number)
        fields_match = bool(record) and all(record.get(k) == invoice.get(k) for k in ("invoice_number", "vendor", "amount", "due_date"))
        success = bool(fields_match and record.get("status") == "PROCESSED")
        result = {"success": success, "record": dict(record) if record else None,
                  "evidence": "Accounting record fields and status match." if success else "Accounting record is missing or does not match."}
        event = "VERIFICATION_SUCCESS" if success else "VERIFICATION_FAILURE"
        return {"verification_result": result, "current_observation": result["evidence"],
                "execution_history": _event(state, event, result["evidence"], invoice_number=invoice_number)}

    return _fail(state, f"Unsupported tool: {action.tool}")
