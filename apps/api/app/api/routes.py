import base64
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, and_
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import ensure_org_membership, get_current_user, get_project_from_api_key
from app.domain.services import api_key_service
from app.domain.services.audit_service import record_audit
from app.domain.services.trace_ingest_service import ingest_trace_batch
from app.models import EvaluationRun, Event, HumanFeedback, Membership, Notification, Organization, Project, Span, Trace, User, utcnow
from app.ownership import get_owned_project, get_owned_trace
from app.schemas import (
    AttentionResponse,
    ApiKeyCreate,
    ApiKeyCreateOut,
    MemberOut,
    NotificationListResponse,
    NotificationMarkReadIn,
    NotificationOut,
    OrganizationCreate,
    OrganizationOut,
    ProjectCreate,
    ProjectOut,
    ProjectUpdateIn,
    SdkStatusOut,
    TraceBatchIn,
    TraceOut,
)
from app.security import new_id

router = APIRouter(prefix="/v1")


def _encode_cursor(created_at: datetime, trace_id: str) -> str:
    raw = f"{created_at.isoformat()}|{trace_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode()).decode()
        ca_str, trace_id = raw.rsplit("|", 1)
        return datetime.fromisoformat(ca_str), trace_id
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_cursor")


@router.get("/me")
def get_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    memberships = db.query(Membership).filter(Membership.user_id == user.id).all()
    orgs = [db.get(Organization, m.organization_id) for m in memberships]
    organizations = [OrganizationOut.model_validate(org).model_dump() for org in orgs if org]
    return {
        "user": {"id": user.id, "email": user.email, "name": user.name},
        "organizations": organizations,
        "current_org": organizations[0] if organizations else None,
    }


@router.get("/organizations")
def list_organizations(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    memberships = db.query(Membership).filter(Membership.user_id == user.id).all()
    orgs = [db.get(Organization, m.organization_id) for m in memberships]
    data = [OrganizationOut.model_validate(org).model_dump() for org in orgs if org]
    return {"data": data}


@router.post("/organizations", status_code=status.HTTP_201_CREATED, response_model=OrganizationOut)
def create_organization(
    payload: OrganizationCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Organization:
    if db.query(Organization).filter(Organization.slug == payload.slug).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="organization_slug_taken")
    org = Organization(id=new_id("org"), name=payload.name, slug=payload.slug)
    db.add(org)
    db.add(Membership(user_id=user.id, organization_id=org.id, role="owner"))
    db.commit()
    db.refresh(org)
    return org


@router.get("/resolve")
def resolve_slugs(
    org_slug: str,
    project_slug: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Resolve org_slug + project_slug → real IDs. Used by the dashboard."""
    org = db.query(Organization).filter(Organization.slug == org_slug).first()
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    ensure_org_membership(db, user.id, org.id)
    project = (
        db.query(Project)
        .filter(Project.organization_id == org.id, Project.slug == project_slug, Project.archived_at.is_(None))
        .first()
    )
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    return {
        "org_id": org.id,
        "org_slug": org.slug,
        "org_name": org.name,
        "project_id": project.id,
        "project_slug": project.slug,
        "project_name": project.name,
    }


@router.get("/projects", response_model=dict)
def list_projects(
    organization_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    ensure_org_membership(db, user.id, organization_id)
    projects = (
        db.query(Project)
        .filter(Project.organization_id == organization_id, Project.archived_at.is_(None))
        .order_by(Project.created_at.desc())
        .all()
    )
    return {"data": [ProjectOut.model_validate(p).model_dump() for p in projects], "next_cursor": None}


@router.post("/projects", status_code=status.HTTP_201_CREATED, response_model=ProjectOut)
def create_project(
    payload: ProjectCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Project:
    ensure_org_membership(db, user.id, payload.organization_id)
    if (
        db.query(Project)
        .filter(Project.organization_id == payload.organization_id, Project.slug == payload.slug)
        .first()
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="project_slug_taken")
    project = Project(
        id=new_id("prj"),
        organization_id=payload.organization_id,
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        default_environment=payload.default_environment,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project(
    payload: ProjectUpdateIn,
    project: Project = Depends(get_owned_project),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Project:
    changes: dict[str, object] = {}
    if payload.name is not None and payload.name != project.name:
        changes["name"] = {"from": project.name, "to": payload.name}
        project.name = payload.name
    if "description" in payload.model_fields_set and payload.description != project.description:
        changes["description"] = {"from": project.description, "to": payload.description}
        project.description = payload.description
    if payload.default_environment is not None and payload.default_environment != project.default_environment:
        changes["default_environment"] = {
            "from": project.default_environment,
            "to": payload.default_environment,
        }
        project.default_environment = payload.default_environment
    db.add(project)
    if changes:
        record_audit(
            db, "project.updated",
            organization_id=project.organization_id,
            actor_user_id=user.id,
            target_type="project",
            target_id=project.id,
            payload={"changes": changes},
        )
    db.commit()
    db.refresh(project)
    return project


@router.get("/organizations/{org_id}/members")
def list_organization_members(
    org_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    ensure_org_membership(db, user.id, org_id)
    rows = (
        db.query(Membership, User)
        .join(User, User.id == Membership.user_id)
        .filter(Membership.organization_id == org_id)
        .order_by(Membership.created_at.asc(), User.email.asc())
        .all()
    )
    return {
        "data": [
            MemberOut(
                user_id=member.user_id,
                email=row_user.email,
                name=row_user.name,
                role=member.role,
                joined_at=member.created_at,
            ).model_dump()
            for member, row_user in rows
        ]
    }


@router.get("/projects/{project_id}/api-keys")
def list_api_keys(
    project: Project = Depends(get_owned_project),
    db: Session = Depends(get_db),
) -> dict:
    return {"data": api_key_service.list_keys(db, project)}


@router.post("/projects/{project_id}/api-keys", status_code=status.HTTP_201_CREATED, response_model=ApiKeyCreateOut)
def create_api_key(
    payload: ApiKeyCreate,
    project: Project = Depends(get_owned_project),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiKeyCreateOut:
    return api_key_service.create_key(db, project, payload, user.id)


@router.post("/projects/{project_id}/api-keys/{key_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(
    key_id: str,
    project: Project = Depends(get_owned_project),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    key = api_key_service.revoke_key(db, project, key_id, user.id)
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")


def _problem_cause(trace: Trace, spans: list[Span]) -> str:
    meta = trace.metadata_json or {}
    for key in ("cause", "error_type", "flagged_reason", "reason"):
        value = meta.get(key)
        if isinstance(value, str) and value:
            return value
    for span in spans:
        err = span.error or {}
        for key in ("type", "code", "error", "reason"):
            value = err.get(key)
            if isinstance(value, str) and value:
                return value
        message = str(err.get("message") or "").lower()
        if "timeout" in message:
            return "vector_db_timeout" if "vector" in message else "timeout"
        if "schema" in message:
            return "schema_mismatch"
    if trace.status == "partial":
        return "low_confidence"
    if trace.total_cost_usd and float(trace.total_cost_usd) > 1:
        return "cost_spike"
    return "trace_error"


def _delta_ms(later: datetime, earlier: datetime) -> int:
    if later.tzinfo is None and earlier.tzinfo is not None:
        earlier = earlier.replace(tzinfo=None)
    elif later.tzinfo is not None and earlier.tzinfo is None:
        later = later.replace(tzinfo=None)
    return max(0, int((later - earlier).total_seconds() * 1000))


@router.get("/projects/{project_id}/attention", response_model=AttentionResponse)
def get_project_attention(
    project: Project = Depends(get_owned_project),
    db: Session = Depends(get_db),
) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    traces = (
        db.query(Trace)
        .filter(
            Trace.project_id == project.id,
            Trace.deleted_at.is_(None),
            Trace.status != "ok",
            Trace.created_at >= cutoff,
        )
        .order_by(Trace.created_at.desc())
        .limit(25)
        .all()
    )
    trace_ids = [trace.id for trace in traces]
    spans = db.query(Span).filter(Span.trace_id.in_(trace_ids)).all() if trace_ids else []
    spans_by_trace: dict[str, list[Span]] = {}
    for span in spans:
        spans_by_trace.setdefault(span.trace_id, []).append(span)
    items = [
        {
            "trace_id": trace.id,
            "cause": _problem_cause(trace, spans_by_trace.get(trace.id, [])),
            "service": trace.service,
            "at": trace.created_at,
        }
        for trace in traces
    ]
    return {"count": len(items), "items": items}


@router.get("/projects/{project_id}/sdk-status", response_model=SdkStatusOut)
def get_project_sdk_status(
    project: Project = Depends(get_owned_project),
    db: Session = Depends(get_db),
) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=60)
    traces = (
        db.query(Trace)
        .filter(Trace.project_id == project.id, Trace.deleted_at.is_(None), Trace.created_at >= cutoff)
        .all()
    )
    trace_ids = [trace.id for trace in traces]
    spans = db.query(Span).filter(Span.trace_id.in_(trace_ids)).all() if trace_ids else []
    span_ids = [span.id for span in spans]
    events = db.query(Event).filter(Event.span_id.in_(span_ids)).all() if span_ids else []

    ingestion_latencies = []
    for trace in traces:
        if trace.created_at and trace.ended_at:
            ingestion_latencies.append(_delta_ms(trace.created_at, trace.ended_at))
    ingestion_latencies.sort()
    if ingestion_latencies:
        p95_index = max(0, min(len(ingestion_latencies) - 1, int(0.95 * (len(ingestion_latencies) - 1))))
        p95 = ingestion_latencies[p95_index]
    else:
        p95 = 0
    last_trace_at = max((trace.created_at for trace in traces), default=None)
    last_event_at = max((event.occurred_at for event in events), default=None)
    candidates = [value for value in [last_trace_at, last_event_at] if value is not None]
    services = sorted({trace.service for trace in traces if trace.service})
    return {
        "p95_ingestion_ms": p95,
        "spans_per_minute": round(len(spans) / 60, 3),
        "last_event_at": max(candidates) if candidates else None,
        "services_seen": services,
    }


@router.get("/projects/{project_id}/notifications", response_model=NotificationListResponse)
def list_project_notifications(
    limit: int = Query(20, ge=1, le=100),
    project: Project = Depends(get_owned_project),
    db: Session = Depends(get_db),
) -> dict:
    rows = (
        db.query(Notification)
        .filter(Notification.project_id == project.id)
        .order_by(Notification.created_at.desc())
        .limit(limit)
        .all()
    )
    unread_count = (
        db.query(func.count(Notification.id))
        .filter(Notification.project_id == project.id, Notification.read_at.is_(None))
        .scalar()
        or 0
    )
    return {
        "data": [NotificationOut.model_validate(row).model_dump() for row in rows],
        "unread_count": int(unread_count),
    }


@router.post("/projects/{project_id}/notifications/mark-read")
def mark_project_notifications_read(
    payload: NotificationMarkReadIn,
    project: Project = Depends(get_owned_project),
    db: Session = Depends(get_db),
) -> dict:
    now = utcnow()
    query = db.query(Notification).filter(Notification.project_id == project.id, Notification.read_at.is_(None))
    if payload.ids:
        query = query.filter(Notification.id.in_(payload.ids))
    rows = query.all()
    for row in rows:
        row.read_at = now
        db.add(row)
    db.commit()
    return {"updated": len(rows)}


@router.post("/traces", status_code=status.HTTP_202_ACCEPTED)
def ingest_traces(
    request: Request,
    payload: TraceBatchIn,
    project: Project = Depends(get_project_from_api_key),
    db: Session = Depends(get_db),
) -> dict:
    redact_header = request.headers.get("X-EvalOps-Redact")
    return ingest_trace_batch(db, project, payload, redact_header)


@router.get("/traces")
def list_traces(
    trace_status: str | None = Query(None, alias="status"),
    environment: str | None = None,
    name: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
    project: Project = Depends(get_owned_project),
    db: Session = Depends(get_db),
) -> dict:
    project_id = project.id
    query = db.query(Trace).filter(Trace.project_id == project_id, Trace.deleted_at.is_(None))
    if trace_status:
        query = query.filter(Trace.status == trace_status)
    if environment:
        query = query.filter(Trace.environment == environment)
    if name:
        query = query.filter(Trace.name.ilike(f"%{name}%"))
    if cursor:
        cursor_created_at, cursor_id = _decode_cursor(cursor)
        query = query.filter(
            or_(
                Trace.created_at < cursor_created_at,
                and_(Trace.created_at == cursor_created_at, Trace.id < cursor_id),
            )
        )
    page_limit = min(max(limit, 1), 200)
    rows = query.order_by(Trace.created_at.desc(), Trace.id.desc()).limit(page_limit + 1).all()
    has_more = len(rows) > page_limit
    rows = rows[:page_limit]
    trace_ids = [row.id for row in rows]
    last_scores: dict[str, float | None] = {}
    if trace_ids:
        runs = (
            db.query(EvaluationRun)
            .filter(EvaluationRun.trace_id.in_(trace_ids))
            .order_by(EvaluationRun.trace_id.asc(), EvaluationRun.created_at.desc())
            .all()
        )
        for run in runs:
            if run.trace_id not in last_scores:
                last_scores[run.trace_id] = float(run.aggregate_score) if run.aggregate_score is not None else None
    data = []
    for row in rows:
        item = TraceOut.model_validate(row).model_dump()
        item["last_score"] = last_scores.get(row.id)
        data.append(item)
    next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id) if has_more and rows else None
    return {"data": data, "next_cursor": next_cursor}


@router.get("/traces/{trace_id}")
def get_trace(
    trace: Trace = Depends(get_owned_trace),
    db: Session = Depends(get_db),
) -> dict:
    trace_id = trace.id
    spans = db.query(Span).filter(Span.trace_id == trace_id).all()
    span_ids = [span.id for span in spans]
    events = db.query(Event).filter(Event.span_id.in_(span_ids)).all() if span_ids else []
    events_by_span: dict[str, list[Event]] = {}
    for event in events:
        events_by_span.setdefault(event.span_id, []).append(event)
    span_data: list[dict] = []
    for span in spans:
        span_data.append(
            {
                "id": span.id,
                "trace_id": span.trace_id,
                "parent_span_id": span.parent_span_id,
                "type": span.type,
                "name": span.name,
                "status": span.status,
                "started_at": span.started_at,
                "ended_at": span.ended_at,
                "duration_ms": span.duration_ms,
                "provider": span.provider,
                "model": span.model,
                "prompt_version_ref": span.prompt_version_ref,
                "messages_in": span.messages_in,
                "messages_out": span.messages_out,
                "tools": span.tools,
                "tokens_in": span.tokens_in,
                "tokens_out": span.tokens_out,
                "cost_usd": float(span.cost_usd) if span.cost_usd is not None else None,
                "fallback_from_span_id": span.fallback_from_span_id,
                "input": span.input,
                "output": span.output,
                "error": span.error,
                "metadata": span.metadata_json,
                "events": [
                    {"id": e.id, "type": e.type, "occurred_at": e.occurred_at, "payload": e.payload}
                    for e in events_by_span.get(span.id, [])
                ],
            }
        )
    feedback = (
        db.query(HumanFeedback)
        .filter(HumanFeedback.trace_id == trace_id)
        .order_by(HumanFeedback.created_at.desc())
        .all()
    )
    feedback_data = [
        {
            "id": row.id,
            "trace_id": row.trace_id,
            "source": row.source,
            "thumbs": row.thumbs,
            "rating": row.rating,
            "comment": row.comment,
            "tags": row.tags or [],
            "user_ref": row.user_ref,
            "correction": row.correction,
            "created_at": row.created_at,
        }
        for row in feedback
    ]
    return {
        "trace": TraceOut.model_validate(trace).model_dump(),
        "spans": span_data,
        "events_count": len(events),
        "feedback": feedback_data,
    }


@router.delete("/traces/{trace_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_trace(
    trace: Trace = Depends(get_owned_trace),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    trace.deleted_at = utcnow()
    db.add(trace)
    record_audit(
        db, "trace.deleted",
        organization_id=trace.organization_id,
        actor_user_id=user.id,
        target_type="trace",
        target_id=trace.id,
        payload={"project_id": trace.project_id, "trace_name": trace.name},
    )
    db.commit()


@router.get("/analytics/overview")
def analytics_overview(
    environment: str | None = None,
    limit_days: int = 14,
    project: Project = Depends(get_owned_project),
    db: Session = Depends(get_db),
) -> dict:
    project_id = project.id
    base_query = db.query(Trace).filter(Trace.project_id == project_id, Trace.deleted_at.is_(None))
    if environment:
        base_query = base_query.filter(Trace.environment == environment)
    rows = base_query.all()
    if not rows:
        return {
            "kpis": {
                "traces": 0,
                "cost_usd": 0.0,
                "latency_p95_ms": 0,
                "avg_score": None,
                "error_rate": 0.0,
            },
            "cost_by_day": [],
            "model_breakdown": [],
            "recent_flagged": [],
        }

    durations = sorted([row.duration_ms for row in rows])
    p95_index = max(0, min(len(durations) - 1, int(0.95 * (len(durations) - 1))))
    p95 = durations[p95_index]
    error_count = sum(1 for row in rows if row.status == "error")
    total_cost = float(sum(Decimal(str(row.total_cost_usd)) for row in rows))

    day_rows = (
        db.query(
            func.date(Trace.created_at).label("day"),
            func.sum(Trace.total_cost_usd).label("total_cost"),
            func.count(Trace.id).label("traces_count"),
        )
        .filter(Trace.project_id == project_id, Trace.deleted_at.is_(None))
        .group_by(func.date(Trace.created_at))
        .order_by(func.date(Trace.created_at).desc())
        .limit(max(1, min(limit_days, 90)))
        .all()
    )
    day_rows = list(reversed(day_rows))

    model_rows = (
        db.query(
            Span.provider.label("provider"),
            Span.model.label("model"),
            func.sum(Span.cost_usd).label("total_cost"),
            func.sum(Span.tokens_in).label("tokens_in"),
            func.sum(Span.tokens_out).label("tokens_out"),
            func.count(Span.id).label("calls"),
        )
        .join(Trace, Span.trace_id == Trace.id)
        .filter(Trace.project_id == project_id, Trace.deleted_at.is_(None), Span.type == "llm_call")
        .group_by(Span.provider, Span.model)
        .order_by(func.sum(Span.cost_usd).desc())
        .all()
    )

    flagged = (
        db.query(Trace)
        .filter(Trace.project_id == project_id, Trace.deleted_at.is_(None))
        .filter(Trace.status.in_(["error", "partial"]))
        .order_by(Trace.created_at.desc())
        .limit(10)
        .all()
    )

    return {
        "kpis": {
            "traces": len(rows),
            "cost_usd": round(total_cost, 6),
            "latency_p95_ms": p95,
            "avg_score": None,
            "error_rate": round(error_count / max(1, len(rows)), 4),
        },
        "cost_by_day": [
            {
                "day": str(day_row.day),
                "cost_usd": float(day_row.total_cost or 0),
                "traces": int(day_row.traces_count or 0),
            }
            for day_row in day_rows
        ],
        "model_breakdown": [
            {
                "provider": row.provider,
                "model": row.model,
                "cost_usd": float(row.total_cost or 0),
                "tokens_in": int(row.tokens_in or 0),
                "tokens_out": int(row.tokens_out or 0),
                "calls": int(row.calls or 0),
            }
            for row in model_rows
        ],
        "recent_flagged": [TraceOut.model_validate(row).model_dump() for row in flagged],
    }
