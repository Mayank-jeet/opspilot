from typing import Any, Literal

from typing_extensions import TypedDict

from pydantic import BaseModel, ConfigDict, Field


class ActionArguments(BaseModel):
    """Known optional parameters supported by the agent's tools."""

    model_config = ConfigDict(extra="forbid")

    sender: str | None = None
    query: str | None = None
    message_id: str | None = None
    invoice_number: str | None = None
    vendor: str | None = None
    amount: int | None = None
    due_date: str | None = None
    due_in_months: int | None = None
    due_in_days: int | None = None
    currency: str | None = None


class AgentAction(BaseModel):
    """One structured decision from the task planner."""

    model_config = ConfigDict(extra="forbid")

    tool: Literal[
        "search_inbox",
        "read_invoice",
        "create_invoice",
        "check_accounting",
        "open_accounting",
        "fill_invoice",
        "submit_invoice",
        "verify_invoice",
        "finish",
    ]
    arguments: ActionArguments = Field(default_factory=ActionArguments)
    reason: str


class AgentState(TypedDict, total=False):
    task_id: str
    task: str
    current_observation: str
    current_action: dict[str, Any]
    invoice: dict[str, Any] | None
    search_results: list[dict[str, Any]]
    accounting_checked: bool
    accounting_opened: bool
    invoice_form_filled: bool
    execution_history: list[dict[str, Any]]
    errors: list[str]
    step_count: int
    retry_count: int
    retry_action: dict[str, Any] | None
    approval_status: Literal["not_required", "pending", "approved", "rejected"]
    verification_result: dict[str, Any] | None
    completed: bool
    failed: bool
    final_summary: str
