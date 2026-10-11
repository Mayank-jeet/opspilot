import unittest
from unittest.mock import patch

from app.agent.graph import build_agent
from app.agent.service import decide_approval
from app.agent.state import AgentAction
from app.data import ACCOUNTING_RECORDS, APPROVED_SUBMISSIONS, INVOICES, search_invoices
from app.agent import executor


class SequencePlanner:
    def __init__(self, *actions):
        self.actions = list(actions)

    def plan(self, _state):
        if not self.actions:
            raise AssertionError("Agent requested more planner actions than expected")
        return self.actions.pop(0)


def action(tool, arguments=None, reason="test action"):
    return AgentAction(tool=tool, arguments=arguments or {}, reason=reason)


def start_state():
    return {
        "task_id": "test-task",
        "task": "Process the latest Acme invoice",
        "current_observation": "Task received",
        "invoice": None,
        "search_results": [],
        "accounting_checked": False,
        "accounting_opened": False,
        "invoice_form_filled": False,
        "execution_history": [],
        "errors": [],
        "step_count": 0,
        "retry_count": 0,
        "retry_action": None,
        "approval_status": "not_required",
        "verification_result": None,
        "completed": False,
        "failed": False,
        "final_summary": "",
    }


class AgentGraphTests(unittest.TestCase):
    def setUp(self):
        ACCOUNTING_RECORDS.clear()
        APPROVED_SUBMISSIONS.clear()
        executor.FAIL_NEXT_TOOL = None
        # Never hit the real currency API in tests: use the offline fixed rates.
        from app import currency as currency_module
        test_rates = {**currency_module.FALLBACK_INR_PER_UNIT, "JPY": 0.55}
        patch("app.currency.list_currencies", return_value={**currency_module.FALLBACK_NAMES, "JPY": "Japanese Yen"}).start()
        patch("app.currency.get_rate", side_effect=lambda code: {
            "rate": test_rates[code.upper()], "date": "2026-10-10", "source": "live"}).start()
        patch("app.agent.browser.open_accounting_page", return_value="Accounting").start()
        patch("app.agent.browser.fill_invoice_form", side_effect=lambda invoice: invoice["invoice_number"]).start()

        def submit_in_browser(invoice):
            record = {key: invoice[key] for key in ("invoice_number", "vendor", "amount", "due_date")}
            record["currency"] = invoice.get("currency", "INR")
            record["status"] = "PROCESSED"
            ACCOUNTING_RECORDS[record["invoice_number"]] = record
            return {"invoice_number": record["invoice_number"], "status": record["status"]}

        patch("app.agent.browser.submit_invoice_form", side_effect=submit_in_browser).start()
        self.addCleanup(patch.stopall)
        self.invoice = next(row for row in INVOICES if row["invoice_number"] == "AC-1042")

    def test_action_schema_disallows_unbounded_argument_properties(self):
        schema = AgentAction.model_json_schema()
        arguments_schema = schema["$defs"]["ActionArguments"]
        self.assertFalse(schema.get("additionalProperties", True))
        self.assertFalse(arguments_schema.get("additionalProperties", True))

    def test_injected_transient_failure_retries_same_tool_then_completes(self):
        invoice = next(row for row in INVOICES if row["invoice_number"] == "GX-2201")
        executor.FAIL_NEXT_TOOL = "search_inbox"
        done = build_agent(SequencePlanner(
            action("search_inbox", {"sender": "Globex", "query": "invoice"}),
            action("read_invoice", {"message_id": invoice["id"]}),
            action("check_accounting", {"invoice_number": invoice["invoice_number"]}),
            action("open_accounting", {"invoice_number": invoice["invoice_number"]}),
            action("fill_invoice", {"invoice_number": invoice["invoice_number"]}),
            action("submit_invoice", {"invoice_number": invoice["invoice_number"]}),
            action("verify_invoice", {"invoice_number": invoice["invoice_number"]}),
            action("finish", reason="Verified result"),
        )).invoke(start_state())
        events = [entry["event"] for entry in done["execution_history"]]
        self.assertTrue(done["completed"])
        self.assertEqual(events.count("SIMULATED_FAILURE"), 1)
        self.assertEqual(events.count("RECOVERY_RETRY"), 1)
        self.assertEqual(done["retry_count"], 1)
        self.assertEqual(ACCOUNTING_RECORDS[invoice["invoice_number"]]["status"], "PROCESSED")

    def test_search_and_read_invoice_tools(self):
        from app.agent.executor import execute_action
        state = start_state()
        state.update(execute_action(state, action("search_inbox", {"sender": "Acme", "query": "invoice"})))
        self.assertEqual(state["search_results"][0]["invoice_number"], "AC-1042")
        state.update(execute_action(state, action("read_invoice", {"message_id": "mail-ac-1042"})))
        self.assertEqual(state["invoice"]["amount"], 72450)

    def test_natural_language_search_finds_latest_acme_invoice(self):
        results = search_invoices(sender="Acme Corp", query="Find the latest invoice from Acme Corp and process it")
        self.assertEqual([row["invoice_number"] for row in results], ["AC-1042", "AC-1038"])

    def test_high_value_invoice_pauses_and_resumes_after_approval(self):
        first_run = build_agent(SequencePlanner(
            action("search_inbox", {"sender": "Acme", "query": "invoice"}),
            action("read_invoice", {"message_id": "mail-ac-1042"}),
            action("check_accounting", {"invoice_number": "AC-1042"}),
            action("open_accounting", {"invoice_number": "AC-1042"}),
            action("fill_invoice", {"invoice_number": "AC-1042"}),
            action("submit_invoice", {"invoice_number": "AC-1042"}),
        )).invoke(start_state())
        self.assertEqual(first_run["approval_status"], "pending")
        self.assertNotIn("AC-1042", ACCOUNTING_RECORDS)

        approved = {**first_run, "approval_status": "approved"}
        done = build_agent(SequencePlanner(
            action("submit_invoice", {"invoice_number": "AC-1042"}),
            action("verify_invoice", {"invoice_number": "AC-1042"}),
            action("finish", reason="Verified result"),
        )).invoke(approved)
        self.assertTrue(done["completed"])
        self.assertTrue(done["verification_result"]["success"])
        self.assertEqual(ACCOUNTING_RECORDS["AC-1042"]["status"], "PROCESSED")

    def test_existing_invoice_is_verified_without_resubmission(self):
        ACCOUNTING_RECORDS["AC-1042"] = {
            **{key: self.invoice[key] for key in ("invoice_number", "vendor", "amount", "due_date")},
            "status": "PROCESSED",
        }
        done = build_agent(SequencePlanner(
            action("search_inbox", {"sender": "Acme", "query": "invoice"}),
            action("read_invoice", {"message_id": "mail-ac-1042"}),
            action("check_accounting", {"invoice_number": "AC-1042"}),
            action("verify_invoice", {"invoice_number": "AC-1042"}),
            action("finish", reason="Already processed and verified"),
        )).invoke(start_state())
        self.assertTrue(done["completed"])
        self.assertEqual(sum(e["event"] == "ALREADY_PROCESSED" for e in done["execution_history"]), 1)

    def test_rejection_stops_without_submission(self):
        pending = start_state()
        pending.update({"task_id": "approval-test", "approval_status": "pending", "invoice": self.invoice})
        from app.agent.service import TASKS
        TASKS["approval-test"] = pending
        rejected = decide_approval("approval-test", approved=False)
        self.assertTrue(rejected["failed"])
        self.assertEqual(rejected["approval_status"], "rejected")
        self.assertNotIn("AC-1042", ACCOUNTING_RECORDS)

    def test_submit_is_blocked_without_accounting_precheck(self):
        from app.agent.executor import execute_action
        state = start_state()
        state["invoice"] = self.invoice
        result = execute_action(state, action("submit_invoice", {"invoice_number": "AC-1042"}))
        self.assertIn("check_accounting must confirm", result["current_observation"])
        self.assertNotIn("AC-1042", ACCOUNTING_RECORDS)

    def test_verification_fails_when_accounting_record_is_missing(self):
        from app.agent.executor import execute_action
        state = start_state()
        state["invoice"] = self.invoice
        result = execute_action(state, action("verify_invoice", {"invoice_number": "AC-1042"}))
        self.assertFalse(result["verification_result"]["success"])
        self.assertEqual(result["execution_history"][-1]["event"], "VERIFICATION_FAILURE")

    def test_high_value_api_submission_requires_and_consumes_exact_approval(self):
        from fastapi import HTTPException
        from app.main import submit_invoice
        from app.schemas import InvoiceSubmission

        payload = InvoiceSubmission(invoice_number="AC-1042", vendor="Acme Corporation",
                                    amount=72450, due_date="2026-10-15")
        with self.assertRaises(HTTPException) as error:
            submit_invoice(payload)
        self.assertEqual(error.exception.status_code, 403)

        APPROVED_SUBMISSIONS["AC-1042"] = payload.model_dump(mode="json")
        record = submit_invoice(payload)
        self.assertEqual(record["status"], "PROCESSED")
        self.assertNotIn("AC-1042", APPROVED_SUBMISSIONS)

    def _cleanup_invoice(self, number):
        def remove():
            INVOICES[:] = [row for row in INVOICES if row["invoice_number"] != number]
        self.addCleanup(remove)

    def test_create_invoice_adds_inbox_message_with_computed_due_date(self):
        from datetime import date
        from app.agent.executor import _add_months, execute_action
        self._cleanup_invoice("ACE-019")
        result = execute_action(start_state(), action("create_invoice", {
            "invoice_number": "ace-019", "vendor": "Acme Corp", "amount": 50000, "due_in_months": 1}))
        self.assertEqual(result["invoice"]["invoice_number"], "ACE-019")
        self.assertEqual(result["invoice"]["due_date"], _add_months(date.today(), 1).isoformat())
        self.assertIn("ACE-019", [row["invoice_number"] for row in search_invoices(query="ACE-019")])

    def test_add_months_clamps_to_month_end(self):
        from datetime import date
        from app.agent.executor import _add_months
        self.assertEqual(_add_months(date(2026, 1, 31), 1), date(2026, 2, 28))
        self.assertEqual(_add_months(date(2026, 12, 15), 1), date(2027, 1, 15))

    def test_create_invoice_rejects_duplicate_number(self):
        from app.agent.executor import execute_action
        result = execute_action(start_state(), action("create_invoice", {
            "invoice_number": "AC-1042", "vendor": "Acme Corp", "amount": 50000, "due_in_months": 1}))
        self.assertEqual(result["execution_history"][-1]["event"], "TOOL_FAILURE")
        self.assertEqual(len([row for row in INVOICES if row["invoice_number"] == "AC-1042"]), 1)

    def test_create_invoice_then_existing_flow_completes_without_approval(self):
        self._cleanup_invoice("ACE-019")
        state = start_state()
        state["task"] = "Add a new invoice of 50000 by Acme Corp, due after 1 month, invoice no. ACE-019"
        done = build_agent(SequencePlanner(
            action("create_invoice", {"invoice_number": "ACE-019", "vendor": "Acme Corp",
                                      "amount": 50000, "due_in_months": 1}),
        )).invoke(state)
        self.assertTrue(done["completed"])
        self.assertEqual(ACCOUNTING_RECORDS["ACE-019"]["amount"], 50000)
        self.assertNotEqual(done["approval_status"], "pending")

    def test_create_invoice_defaults_amount_zero_and_due_one_month(self):
        from datetime import date
        from app.agent.executor import _add_months, execute_action
        self._cleanup_invoice("ACE-020")
        result = execute_action(start_state(), action("create_invoice", {
            "invoice_number": "ACE-020", "vendor": "Acme Corp"}))
        self.assertEqual(result["invoice"]["amount"], 0)
        self.assertEqual(result["invoice"]["due_date"], _add_months(date.today(), 1).isoformat())

    def test_create_invoice_uses_specified_due_date(self):
        from datetime import date, timedelta
        from app.agent.executor import execute_action
        self._cleanup_invoice("ACE-021")
        wanted = (date.today() + timedelta(days=45)).isoformat()
        result = execute_action(start_state(), action("create_invoice", {
            "invoice_number": "ACE-021", "vendor": "Acme Corp", "amount": 100, "due_date": wanted}))
        self.assertEqual(result["invoice"]["due_date"], wanted)

    def test_create_invoice_same_details_reuses_existing(self):
        from app.agent.executor import execute_action
        self._cleanup_invoice("ACE-019")
        args = {"invoice_number": "ACE-019", "vendor": "Acme Corp", "amount": 50000}
        execute_action(start_state(), action("create_invoice", args))
        again = execute_action(start_state(), action("create_invoice", args))
        self.assertEqual(again["execution_history"][-1]["event"], "TOOL_SUCCESS")
        self.assertEqual(len([r for r in INVOICES if r["invoice_number"] == "ACE-019"]), 1)

    def test_create_invoice_conflicting_details_is_rejected_and_unchanged(self):
        from app.agent.executor import execute_action
        self._cleanup_invoice("ACE-019")
        execute_action(start_state(), action("create_invoice", {
            "invoice_number": "ACE-019", "vendor": "Acme Corp", "amount": 50000}))
        result = execute_action(start_state(), action("create_invoice", {
            "invoice_number": "ACE-019", "vendor": "Acme Corp", "amount": 60000}))
        self.assertEqual(result["execution_history"][-1]["event"], "TOOL_FAILURE")
        row = next(r for r in INVOICES if r["invoice_number"] == "ACE-019")
        self.assertEqual(row["amount"], 50000)

    def test_create_invoice_fills_amount_on_existing_zero_amount_invoice(self):
        from app.agent.executor import execute_action
        self._cleanup_invoice("ACE-022")
        execute_action(start_state(), action("create_invoice", {"invoice_number": "ACE-022", "vendor": "Acme Corp"}))
        execute_action(start_state(), action("create_invoice", {
            "invoice_number": "ACE-022", "vendor": "Acme Corp", "amount": 5000}))
        row = next(r for r in INVOICES if r["invoice_number"] == "ACE-022")
        self.assertEqual(row["amount"], 5000)

    def test_zero_amount_invoice_is_not_submitted_to_accounting(self):
        self._cleanup_invoice("ACE-020")
        done = build_agent(SequencePlanner(
            action("create_invoice", {"invoice_number": "ACE-020", "vendor": "Acme Corp"}),
        )).invoke(start_state())
        self.assertTrue(done["failed"])
        self.assertIn("amount", done["final_summary"])
        self.assertNotIn("ACE-020", ACCOUNTING_RECORDS)

    def test_manual_create_saves_invoice_with_defaults(self):
        from datetime import date
        from app.agent.executor import _add_months
        from app.main import create_inbox_message
        from app.schemas import InvoiceCreate
        self._cleanup_invoice("MAN-001")
        row = create_inbox_message(InvoiceCreate(invoice_number="man-001", vendor="Manual Co", amount=1200))
        self.assertEqual(row["invoice_number"], "MAN-001")
        self.assertEqual(row["id"], "mail-man-001")
        self.assertEqual(row["sender"], "Manual Co")
        self.assertEqual(row["subject"], "Invoice #MAN-001")
        self.assertEqual(row["due_date"], _add_months(date.today(), 1).isoformat())
        self.assertIn("MAN-001", [r["invoice_number"] for r in search_invoices(query="MAN-001")])

    def test_manual_create_rejects_duplicate_invoice_number(self):
        from fastapi import HTTPException
        from app.main import create_inbox_message
        from app.schemas import InvoiceCreate
        with self.assertRaises(HTTPException) as error:
            create_inbox_message(InvoiceCreate(invoice_number="ac-1042", vendor="Acme Corporation", amount=72450))
        self.assertEqual(error.exception.status_code, 409)

    def test_manual_create_rejects_due_date_before_received(self):
        from fastapi import HTTPException
        from app.main import create_inbox_message
        from app.schemas import InvoiceCreate
        self._cleanup_invoice("MAN-002")
        with self.assertRaises(HTTPException) as error:
            create_inbox_message(InvoiceCreate(invoice_number="MAN-002", vendor="Manual Co", due_date="2020-01-01"))
        self.assertEqual(error.exception.status_code, 422)
        self.assertNotIn("MAN-002", [r["invoice_number"] for r in INVOICES])

    def test_create_invoice_converts_foreign_currency_to_inr(self):
        from app.agent.executor import execute_action
        from app.currency import to_inr
        self._cleanup_invoice("USD-001")
        result = execute_action(start_state(), action("create_invoice", {
            "invoice_number": "USD-001", "vendor": "Globex", "amount": 700, "currency": "usd"}))
        invoice = result["invoice"]
        self.assertEqual((invoice["amount"], invoice["currency"]), (700, "USD"))
        self.assertEqual(invoice["amount_inr"], to_inr(700, "USD"))
        self.assertGreater(invoice["amount_inr"], 50_000)  # so the approval rule applies correctly

    def test_create_invoice_rejects_unsupported_currency(self):
        from app.agent.executor import execute_action
        result = execute_action(start_state(), action("create_invoice", {
            "invoice_number": "XYZ-001", "vendor": "Globex", "amount": 10, "currency": "XYZ"}))
        self.assertEqual(result["execution_history"][-1]["event"], "TOOL_FAILURE")
        self.assertNotIn("XYZ-001", [r["invoice_number"] for r in INVOICES])

    def test_manual_create_converts_currency_and_rejects_unsupported(self):
        from fastapi import HTTPException
        from app.currency import to_inr
        from app.main import create_inbox_message
        from app.schemas import InvoiceCreate
        self._cleanup_invoice("MAN-003")
        row = create_inbox_message(InvoiceCreate(invoice_number="MAN-003", vendor="Manual Co", amount=100, currency="EUR"))
        self.assertEqual((row["amount"], row["currency"]), (100, "EUR"))
        self.assertEqual(row["amount_inr"], to_inr(100, "EUR"))
        with self.assertRaises(HTTPException) as error:
            create_inbox_message(InvoiceCreate(invoice_number="MAN-004", vendor="Manual Co", amount=1, currency="XYZ"))
        self.assertEqual(error.exception.status_code, 422)

    def test_same_foreign_invoice_is_not_a_conflict_when_rate_changes(self):
        from app.agent.executor import execute_action
        self._cleanup_invoice("USD-002")
        args = {"invoice_number": "USD-002", "vendor": "Globex", "amount": 700, "currency": "USD"}
        execute_action(start_state(), action("create_invoice", args))
        with patch("app.currency.get_rate", return_value={"rate": 90.0, "date": "2026-10-11", "source": "live"}):
            again = execute_action(start_state(), action("create_invoice", args))
        self.assertEqual(again["execution_history"][-1]["event"], "TOOL_SUCCESS")
        self.assertEqual(len([r for r in INVOICES if r["invoice_number"] == "USD-002"]), 1)

    def test_create_invoice_accepts_symbols_and_names(self):
        from app.agent.executor import execute_action
        for number, given, expected in (("SYM-1", "$", "USD"), ("SYM-2", "¥", "JPY"),
                                        ("SYM-3", "euro", "EUR"), ("SYM-4", "yen", "JPY")):
            self._cleanup_invoice(number)
            result = execute_action(start_state(), action("create_invoice", {
                "invoice_number": number, "vendor": "Globex", "amount": 2000, "currency": given}))
            self.assertEqual((result["invoice"]["amount"], result["invoice"]["currency"]), (2000, expected))

    def test_foreign_invoice_below_limit_is_processed_without_approval(self):
        self._cleanup_invoice("USD-100")
        done = build_agent(SequencePlanner(action("create_invoice", {
            "invoice_number": "USD-100", "vendor": "Globex", "amount": 500, "currency": "$"}))).invoke(start_state())
        self.assertTrue(done["completed"])  # 500 USD is about 41,500 INR
        record = ACCOUNTING_RECORDS["USD-100"]
        self.assertEqual((record["amount"], record["currency"]), (500, "USD"))

    def test_foreign_invoice_above_limit_needs_approval_by_inr_equivalent(self):
        self._cleanup_invoice("USD-101")
        done = build_agent(SequencePlanner(action("create_invoice", {
            "invoice_number": "USD-101", "vendor": "Globex", "amount": 700, "currency": "USD"}))).invoke(start_state())
        self.assertEqual(done["approval_status"], "pending")  # 700 < 50,000 numerically, but about 58,100 INR
        self.assertNotIn("USD-101", ACCOUNTING_RECORDS)

    def test_yen_amount_large_in_yen_but_small_in_inr_needs_no_approval(self):
        self._cleanup_invoice("JPY-100")
        done = build_agent(SequencePlanner(action("create_invoice", {
            "invoice_number": "JPY-100", "vendor": "Globex", "amount": 60000, "currency": "¥"}))).invoke(start_state())
        self.assertTrue(done["completed"])  # 60,000 JPY is only about 33,000 INR
        self.assertEqual(ACCOUNTING_RECORDS["JPY-100"]["currency"], "JPY")

    def test_accounting_api_applies_threshold_to_inr_equivalent(self):
        from fastapi import HTTPException
        from app.main import submit_invoice
        from app.schemas import InvoiceSubmission
        big = InvoiceSubmission(invoice_number="USD-102", vendor="Globex", amount=700, currency="USD", due_date="2026-12-01")
        with self.assertRaises(HTTPException) as error:
            submit_invoice(big)
        self.assertEqual(error.exception.status_code, 403)
        APPROVED_SUBMISSIONS["USD-102"] = big.model_dump(mode="json")
        self.assertEqual(submit_invoice(big)["amount_inr"], 58100)
        small = InvoiceSubmission(invoice_number="JPY-102", vendor="Globex", amount=60000, currency="JPY", due_date="2026-12-01")
        self.assertEqual(submit_invoice(small)["status"], "PROCESSED")

    def test_amount_filter_compares_inr_equivalent(self):
        from app.agent.graph import _workflow_action
        state = start_state()
        state["task"] = "process the invoice with amount greater than 50000"
        state["execution_history"] = [{"event": "TOOL_SUCCESS", "tool": "search_inbox"}]
        state["search_results"] = [
            {"id": "m-inr", "invoice_number": "I-1", "amount": 40000, "currency": "INR"},
            {"id": "m-usd", "invoice_number": "U-1", "amount": 700, "currency": "USD", "amount_inr": 58100},
        ]
        self.assertEqual(_workflow_action(state).arguments.message_id, "m-usd")

    def test_inbox_message_endpoint_returns_invoice(self):
        from app.main import read_invoice
        self.assertEqual(read_invoice("mail-ac-1042")["invoice_number"], "AC-1042")

    def test_amount_filter_supports_symbols(self):
        from app.agent.graph import _requested_amount_filter
        self.assertEqual(_requested_amount_filter("process invoice < 50,000"), ("lt", 50000))
        self.assertEqual(_requested_amount_filter("process invoice > 50000"), ("gt", 50000))
        self.assertEqual(_requested_amount_filter("invoice under 50000"), ("lt", 50000))

    def test_persistent_injected_failure_stops_after_retry_limit(self):
        def always_fail(state, selected_action):
            message = "Repeated injected failure"
            return {
                "current_observation": message,
                "errors": [*state.get("errors", []), message],
                "execution_history": [*state.get("execution_history", []),
                                      {"event": "SIMULATED_FAILURE", "detail": message}],
            }

        with patch("app.agent.graph.execute_action", side_effect=always_fail):
            result = build_agent(SequencePlanner(
                action("search_inbox", {"sender": "Acme", "query": "invoice"}),
            )).invoke(start_state())
        self.assertTrue(result["failed"])
        self.assertEqual(result["retry_count"], 3)
        self.assertEqual(result["execution_history"][-1]["event"], "RECOVERY_EXHAUSTED")


if __name__ == "__main__":
    unittest.main()
