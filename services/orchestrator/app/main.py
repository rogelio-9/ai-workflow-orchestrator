import uuid

from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Workflow, Run
from app.schemas import WorkflowCreate, WorkflowRead, WorkflowUpdate, RunCreate, RunRead
from app.dag_parser import CycleError, ready_steps, topological_sort
from app.kafka_producer import flush, publish_step


app = FastAPI(title="Orchestrator")

@app.post("/workflows", response_model=WorkflowRead, status_code=status.HTTP_201_CREATED)
def create_workflow(payload: WorkflowCreate, db: Session = Depends(get_db)):
    workflow = Workflow(**payload.model_dump())
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    return workflow


@app.get("/workflows", response_model=list[WorkflowRead])
def list_workflows(db: Session = Depends(get_db)):
    return db.query(Workflow).all()

@app.get("/workflows/{workflow_id}", response_model=WorkflowRead)
def get_workflow(workflow_id: uuid.UUID, db: Session = Depends(get_db)):
    workflow = db.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return workflow

@app.patch("/workflows/{workflow_id}", response_model=WorkflowRead)
def update_workflow(
    workflow_id: uuid.UUID,
    payload: WorkflowUpdate,
    db: Session = Depends(get_db),
):
    workflow = db.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(workflow, field, value)

    db.commit()
    db.refresh(workflow)
    return workflow

@app.delete("/workflows/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workflow(workflow_id: uuid.UUID, db: Session = Depends(get_db)):
    workflow = db.get(Workflow, workflow_id)
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    db.delete(workflow)
    db.commit()

@app.post("/runs", response_model=RunRead, status_code=status.HTTP_201_CREATED)
def create_run(payload: RunCreate, db: Session = Depends(get_db)):
    workflow = db.get(Workflow, payload.workflow_id)
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    try:
        topological_sort(workflow.dag_json)
    except CycleError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    run = Run(**payload.model_dump(), status="PENDING")
    db.add(run)
    db.commit()
    db.refresh(run)

    published_at = datetime.now(timezone.utc).isoformat()
    for node in ready_steps(workflow.dag_json):
        publish_step(
            {
                "run_id": str(run.id),
                # TODO(steps): node ids are workflow-local strings; once the steps
                # table is populated per run this becomes the step row's uuid.
                "step_id": node["id"],
                "step_type": node.get("type"),
                "attempt": 1,
                "config": node.get("config", {}),
                "input_vars": payload.input_vars or {},
                "published_at": published_at,
            }
        )
    flush()

    return run

@app.get("/runs/{run_id}", response_model=RunRead)
def get_run(run_id: uuid.UUID, db: Session = Depends(get_db)):
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run

@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "reload": "works"}