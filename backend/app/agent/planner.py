import os
import json
from typing import Protocol

from langchain_openai import ChatOpenAI

from .state import AgentAction, AgentState


class ActionPlanner(Protocol):
    def plan(self, state: AgentState) -> AgentAction: ...


class OpenAIActionPlanner:
    """Uses an LLM to choose one next tool; policy remains in the executor."""

    def __init__(self):
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is not configured")
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.model = ChatOpenAI(model=model, temperature=0).with_structured_output(AgentAction)

    def plan(self, state: AgentState) -> AgentAction:
        context = {
            "task": state.get("task"),
            "last_observation": state.get("current_observation"),
            "invoice": state.get("invoice"),
            "search_results": state.get("search_results", []),
            "approval_status": state.get("approval_status", "not_required"),
            "verification_result": state.get("verification_result"),
            "recent_history": state.get("execution_history", [])[-8:],
        }
        prompt = """You are the action planner for OpsPilot, a local simulated invoice workflow.
Choose exactly one next tool using the supplied structured action schema. You do not execute tools.

Available tools:
- search_inbox: arguments sender (optional string) and query (optional string).
- create_invoice: arguments invoice_number and vendor (company name as written in the task), plus optional amount (integer, in the invoice's own currency), optional currency exactly as the task writes it (a code like USD or JPY, a symbol like $ € £ ¥ ₹, or a name like yen; leave unset for INR), and an optional due date as exactly one of due_in_months, due_in_days, or due_date (YYYY-MM-DD). The amount stays in its own currency: never convert it yourself and never put a currency symbol in the amount. Only set amount or a due field if the task states it; otherwise leave it unset (amount defaults to 0 and the due date defaults to one month from now). The received time is set automatically; never compute dates yourself. If the invoice already exists with the same details it is reused, not duplicated.
- read_invoice: arguments message_id selected from search_results.
- check_accounting: arguments invoice_number for the currently selected invoice.
- open_accounting: arguments invoice_number. Navigate to the simulated accounting app with Playwright.
- fill_invoice: arguments invoice_number. Fill the accounting form with the currently read invoice using Playwright.
- submit_invoice: arguments invoice_number. Click the accounting form's submit button with Playwright, only after approval when required.
- verify_invoice: arguments invoice_number. Use after submission or finding an existing record.
- finish: no arguments. Use only after independent verification succeeds, or when the task cannot be completed.

Rules: if the task asks to add, create, or record a NEW invoice and gives its details, use create_invoice as the first action and do not search the inbox first; choose the newest matching invoice based on received_at; never invent identifiers or invoice fields; when the task names a sender, pass that company as sender; keep query to short content words such as "invoice" and do not include intent words such as "latest" or "find" because recency is determined from received_at; check accounting before opening/filling/submitting; if an accounting record is already processed, verify it instead of resubmitting; use open_accounting then fill_invoice before submit_invoice; if approval_status is approved, you may continue; if rejected, finish. The executor independently enforces approval and checks every tool's preconditions. If an observation reports an error, select a reasonable next tool or finish with a clear reason.

Current execution context (JSON):
""" + json.dumps(context, ensure_ascii=False)
        return self.model.invoke(prompt)
