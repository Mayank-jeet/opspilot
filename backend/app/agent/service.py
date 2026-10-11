import os
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from ..data import APPROVED_SUBMISSIONS
from .graph import build_agent
from .planner import OpenAIActionPlanner
from .state import AgentState
load_dotenv(Path(__file__).resolve().parents[3] / ".env")

TASKS: dict[str, AgentState] = {}
GRAPH_CONFIG = {"recursion_limit": 60}

def _new_planner() -> OpenAIActionPlanner:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is missing. Copy .env.example to .env and add your key.")
    return OpenAIActionPlanner()


def run_task(task: str) -> AgentState:
    task_id = str(uuid.uuid4())
    initial: AgentState = {
        "task_id": task_id,
        "task": task,
        "current_observation": "Task received. Inspect the request and choose the first useful action.",
        "invoice": None,
        "search_results": [],
        "accounting_checked": False,
        "execution_history": [{"time": datetime.now().astimezone().isoformat(timespec="seconds"),
                               "event": "TASK_RECEIVED", "detail": task}],
        "errors": [],
        "step_count": 0,
        "approval_status": "not_required",
        "verification_result": None,
        "completed": False,
        "failed": False,
        "final_summary": "",
    }
    result = build_agent(_new_planner()).invoke(initial, GRAPH_CONFIG)
    TASKS[task_id] = result
    return result


def decide_approval(task_id: str, approved: bool) -> AgentState:
    state = TASKS.get(task_id)
    if state is None:
        raise KeyError(task_id)
    if state.get("approval_status") != "pending":
        raise ValueError("This task is not waiting for approval")
    if not approved:
        summary = "Human approval was rejected; no invoice was submitted."
        updated = {**state, "approval_status": "rejected", "completed": False, "failed": True,
                   "final_summary": summary, "current_observation": summary,
                   "execution_history": [*state.get("execution_history", []),
                                         {"event": "HUMAN_REJECTED", "detail": summary}]}
    else:
        invoice = state.get("invoice")
        if invoice:
            APPROVED_SUBMISSIONS[invoice["invoice_number"]] = {
                "invoice_number": invoice["invoice_number"], "vendor": invoice["vendor"],
                "amount": invoice["amount"], "currency": invoice.get("currency", "INR"),
                "due_date": invoice["due_date"],
            }
        updated = {**state, "approval_status": "approved", "current_observation": "Human approved this invoice. Continue the task."}
        updated = build_agent(_new_planner()).invoke(updated, GRAPH_CONFIG)
    TASKS[task_id] = updated
    return updated
