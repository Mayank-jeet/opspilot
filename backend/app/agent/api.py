from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..security import require_demo_key
from .service import decide_approval, run_task
from .state import AgentState

router = APIRouter(prefix="/api/tasks", tags=["agent tasks"], dependencies=[Depends(require_demo_key)])


class TaskRequest(BaseModel):
    task: str = Field(min_length=5, max_length=1000)


class ApprovalRequest(BaseModel):
    approved: bool


@router.post("")
def start_task(request: TaskRequest) -> AgentState:
    try:
        return run_task(request.task)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Agent execution failed: {exc}") from exc


@router.post("/{task_id}/approval")
def resume_after_approval(task_id: str, request: ApprovalRequest) -> AgentState:
    try:
        return decide_approval(task_id, request.approved)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Task not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Could not resume the task: {exc}") from exc
