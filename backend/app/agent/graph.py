from datetime import datetime
import re
from typing import Callable

from langgraph.graph import END, START, StateGraph

from .executor import MAX_AGENT_STEPS, MAX_TOOL_RETRIES, execute_action
from ..currency import inr_value
from .planner import ActionPlanner
from .state import AgentAction, AgentState


def _requested_amount_filter(task: str) -> tuple[str, int] | None:
    """Read an amount comparison or exact amount from common task phrasing."""
    amount = r"(?:₹|rs\.?|inr)?\s*([\d,]+)"
    comparisons = (
        ("lte", r"\b(?:at\s+most|no\s+more\s+th[ae]n)\s*" + amount),
        ("gte", r"\b(?:at\s+least|no\s+less\s+th[ae]n)\s*" + amount),
        ("lt", r"(?:\b(?:less(?:er)?|smaller|lower|fewer)\s+th[ae]n|\b(?:below|under)|<)\s*" + amount),
        ("gt", r"(?:\b(?:more|greater|larger|bigger|higher)\s+th[ae]n|\b(?:above|over)|>)\s*" + amount),
    )
    for operator, pattern in comparisons:
        match = re.search(pattern, task, flags=re.IGNORECASE)
        if match:
            return operator, int(match.group(1).replace(",", ""))

    exact_pattern = r"(?:₹|\brs\.?|\binr\b)\s*([\d,]+)|\b(?:for|of|amount(?:\s+of)?|worth)\s*(?:₹|rs\.?|inr)?\s*([\d,]+)\b"
    match = re.search(exact_pattern, task, flags=re.IGNORECASE)
    if match:
        raw_amount = match.group(1) or match.group(2)
        return "eq", int(raw_amount.replace(",", ""))
    return None


def _amount_matches(amount: int, constraint: tuple[str, int]) -> bool:
    operator, target = constraint
    return {
        "lt": amount < target,
        "lte": amount <= target,
        "gt": amount > target,
        "gte": amount >= target,
        "eq": amount == target,
    }[operator]


def _workflow_action(state: AgentState) -> AgentAction | None:
    """Advance the invoice workflow from observed state instead of asking the LLM to repeat steps."""
    history = state.get("execution_history", [])
    search_done = any(item.get("tool") in ("search_inbox", "create_invoice") and item.get("event") == "TOOL_SUCCESS"
                    for item in history)
    if not search_done:
        return None

    results = state.get("search_results", [])
    invoice = state.get("invoice")
    if not results:
        return AgentAction(tool="finish", arguments={}, reason="No matching invoices were found in the inbox.")
    if not invoice:
        amount_filter = _requested_amount_filter(state.get("task", ""))
        candidates = results
        if amount_filter is not None:
            # amount conditions in a task compare the INR equivalent, so $500 and ¥50,000 are comparable
            candidates = [row for row in results if _amount_matches(inr_value(row), amount_filter)]
            if not candidates:
                operator, requested_amount = amount_filter
                comparison = {"lt": "less than", "lte": "at most", "gt": "more than",
                              "gte": "at least", "eq": "exactly"}[operator]
                return AgentAction(
                    tool="finish", arguments={},
                    reason=(f"No matching invoice meets the requested amount condition: {comparison} "
                            f"{requested_amount:,} INR. No invoice was submitted and no approval was requested."),
                )
        return AgentAction(tool="read_invoice", arguments={"message_id": candidates[0]["id"]},
                           reason="Read the newest matching invoice.")

    number = invoice["invoice_number"]
    if not state.get("accounting_checked"):
        return AgentAction(tool="check_accounting", arguments={"invoice_number": number},
                           reason="Check whether this invoice is already recorded.")
    if any(item.get("event") == "ALREADY_PROCESSED" for item in history):
        if state.get("verification_result") is None:
            return AgentAction(tool="verify_invoice", arguments={"invoice_number": number},
                               reason="Verify the existing accounting record.")
        return AgentAction(tool="finish", arguments={}, reason="Existing invoice verification is complete.")
    if invoice.get("amount", 0) <= 0:
        return AgentAction(tool="finish", arguments={},
                           reason=(f"Invoice {number} is in the inbox with amount 0. Accounting needs an amount greater "
                                   "than 0, so it was not submitted. Run the task again with the amount."))
    if not state.get("accounting_opened"):
        return AgentAction(tool="open_accounting", arguments={"invoice_number": number},
                           reason="Open the accounting form after the duplicate check.")
    if not state.get("invoice_form_filled"):
        return AgentAction(tool="fill_invoice", arguments={"invoice_number": number},
                           reason="Fill the form with the selected invoice details.")

    submitted = any(item.get("event") == "TOOL_SUCCESS" and item.get("tool") == "submit_invoice"
                    for item in history)
    if not submitted:
        return AgentAction(tool="submit_invoice", arguments={"invoice_number": number},
                           reason="Submit the invoice; the executor enforces human approval.")
    if state.get("verification_result") is None:
        return AgentAction(tool="verify_invoice", arguments={"invoice_number": number},
                           reason="Independently verify the accounting record.")
    return AgentAction(tool="finish", arguments={}, reason="Invoice verification is complete.")


def build_agent(planner: ActionPlanner | Callable[[AgentState], AgentAction]):
    def plan(state: AgentState) -> dict:
        if state.get("approval_status") == "rejected":
            return {"current_action": {"tool": "finish", "arguments": {}, "reason": "Human approval was rejected; no invoice was submitted."}}
        if state.get("step_count", 0) >= MAX_AGENT_STEPS:
            return {"current_action": {"tool": "finish", "arguments": {}, "reason": "Stopped after reaching the execution step limit."}}
        retry_action = state.get("retry_action")
        if retry_action:
            action = AgentAction.model_validate(retry_action)
            history = [*state.get("execution_history", []),
                       {"time": datetime.now().astimezone().isoformat(timespec="seconds"),
                        "event": "RECOVERY_RETRY", "detail": f"Retrying {action.tool} after a simulated transient failure.",
                        "tool": action.tool}]
            return {"current_action": action.model_dump(), "retry_action": None,
                    "current_observation": f"Recovering: retry {action.tool} after the one-time failure.",
                    "execution_history": history}
        action = _workflow_action(state)
        if action is None:
            action = planner.plan(state) if hasattr(planner, "plan") else planner(state)
        if not isinstance(action, AgentAction):
            action = AgentAction.model_validate(action)
        history = [*state.get("execution_history", []),
                   {"time": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "event": "TOOL_SELECTED", "detail": action.reason, "tool": action.tool}]
        return {"current_action": action.model_dump(), "execution_history": history}

    def execute(state: AgentState) -> dict:
        action = AgentAction.model_validate(state["current_action"])
        result = execute_action(state, action)
        updates = {**result, "step_count": state.get("step_count", 0) + (action.tool != "finish")}
        history = updates.get("execution_history", [])
        if history and history[-1].get("event") == "TOOL_FAILURE":
            history = [*history[:-1], {**history[-1], "tool": action.tool}]
            updates["execution_history"] = history
            failures = sum(item.get("event") == "TOOL_FAILURE" and item.get("tool") == action.tool
                           for item in history)
            if failures >= 2:
                summary = f"Stopped because {action.tool} failed twice. Latest error: {updates.get('current_observation', 'unknown error')}"
                updates.update({"failed": True, "completed": False, "final_summary": summary,
                                "current_observation": summary})
        simulated_failure = bool(history and history[-1].get("event") == "SIMULATED_FAILURE")
        if simulated_failure:
            retry_count = state.get("retry_count", 0) + 1
            if retry_count > MAX_TOOL_RETRIES:
                summary = f"Stopped after {MAX_TOOL_RETRIES} recovery retries for {action.tool}."
                updates.update({"retry_count": retry_count, "retry_action": None, "failed": True,
                                "final_summary": summary, "current_observation": summary,
                                "execution_history": [*history, {"time": datetime.now().astimezone().isoformat(timespec="seconds"),
                                                                  "event": "RECOVERY_EXHAUSTED", "detail": summary,
                                                                  "tool": action.tool}]})
            else:
                updates.update({"retry_count": retry_count, "retry_action": action.model_dump()})
        return updates

    def after_plan(state: AgentState) -> str:
        return "execute"

    def after_execute(state: AgentState) -> str:
        if state.get("completed") or state.get("failed") or state.get("approval_status") == "pending":
            return "end"
        return "plan"

    builder = StateGraph(AgentState)
    builder.add_node("plan", plan)
    builder.add_node("execute", execute)
    builder.add_edge(START, "plan")
    builder.add_conditional_edges("plan", after_plan, {"execute": "execute"})
    builder.add_conditional_edges("execute", after_execute, {"plan": "plan", "end": END})
    return builder.compile()
