"""External harness imports are evidence, never authorization to dispatch work."""
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app import models as m
from app.api.routes_tasks import task_db, visible_list
from app.domain.tasks import service as s
from app.domain.tasks.executions import ExecutionImport, import_execution

router = APIRouter(prefix="/v1")


@router.post("/projects/{project_id}/execution-imports", status_code=201)
def create_import(project_id: str, payload: ExecutionImport, request: Request, db: Session = Depends(task_db)):
    actor = s.authenticate(request, db, "write")
    s.project_access(db, actor, project_id, "write")
    return s.serialize(s.write(db, actor, request, project_id, payload.model_dump(mode="json"),
                               lambda: import_execution(db, actor, project_id, payload)))


@router.get("/projects/{project_id}/executions")
def list_executions(project_id: str, request: Request, limit: int = Query(100, ge=1, le=500),
                    cursor: int = Query(0, ge=0), db: Session = Depends(task_db)):
    actor = s.authenticate(request, db)
    s.project_access(db, actor, project_id)
    return visible_list(db, actor, "execution", db.query(m.Execution).filter_by(project_id=project_id), limit, cursor)


@router.get("/executions/{execution_id}")
def get_execution(execution_id: str, request: Request, db: Session = Depends(task_db)):
    return s.serialize(s.load(db, s.authenticate(request, db), "execution", execution_id))
