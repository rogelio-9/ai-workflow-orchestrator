import uuid

from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Workflow, Run, Step
from app.schemas import WorkflowCreate, WorkflowRead, WorkflowUpdate, RunCreate, RunRead
from app.dag_parser import CycleError, ready_steps, topological_sort
from app.kafka_producer import flush, publish_step
from app.steps import sync_steps
from app.retry_run import retry_run


app = FastAPI(title="Orchestrator")

@app.post("/workflows", response_model=WorkflowRead, status_code=status.HTTP_201_CREATED)
def create_workflow(payload: WorkflowCreate, db: Session = Depends(get_db)):
    workflow = Workflow(**payload.model_dump())
    db.add(workflow)
    db.flush()
    sync_steps(db, workflow)
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

    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(workflow, field, value)

    if "dag_json" in changes:
        # Copy-on-write: a new version, a new set of steps rows. Existing runs
        # stay pinned to the version they started on, so their step_results
        # keep describing the graph that actually produced them.
        workflow.version += 1
        sync_steps(db, workflow)

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

    # Pinned at creation: a retry must resume against the graph this run
    # started on, not whatever it has been edited into since.
    run = Run(
        **payload.model_dump(),
        status="PENDING",
        workflow_version=workflow.version,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    step_ids = {
        step.node_id: step.id
        for step in db.query(Step).filter(
            Step.workflow_id == workflow.id, Step.version == run.workflow_version
        )
    }

    published_at = datetime.now(timezone.utc).isoformat()
    for node in ready_steps(workflow.dag_json):
        publish_step(
            {
                "run_id": str(run.id),
                # node_id is graph identity, step_id is database identity. The
                # worker keys locks on the former and the step_results FK on
                # the latter.
                "node_id": node["id"],
                "step_id": str(step_ids[node["id"]]),
                "step_type": node.get("type"),
                "attempt": 1,
                "config": node.get("config", {}),
                "input_vars": payload.input_vars or {},
                "published_at": published_at,
            }
        )
    flush()

    return run

@app.post("/runs/{run_id}/retry", response_model=RunRead)
def retry_run_endpoint(
    run_id: uuid.UUID,
    from_node_id: str | None = None,
    db: Session = Depends(get_db),
):
    run = db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    try:
        republished = retry_run(db, run, from_node_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if not republished:
        # Nothing failed, so there is nothing to resume. 409 rather than a
        # silent 200: the caller asked for work that does not exist.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="run has no failed steps to retry",
        )

    db.refresh(run)
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