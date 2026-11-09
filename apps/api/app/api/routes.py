import base64
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import String, and_, case, cast, func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import ensure_org_membership, get_current_user, get_project_from_api_key
from app.domain.services import api_key_service
from app.domain.services.analytics_service import (
    p95_nearest_rank as _p95_nearest_rank,
    resolve_overview_cutoff as _resolve_overview_cutoff,
)
from app.domain.services.rag_service import rag_filter_predicate as _rag_filter_predicate
from app.domain.services.audit_service import record_audit
from app.domain.services.trace_ingest_service import ingest_trace_batch
from app.models import EvaluationRun, Event, HumanFeedback, Membership, Notification, Organization, Project, Span, Trace, TraceFlag, User, utcnow
from app.ownership import get_owned_project, project_access, trace_access
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
from app.timestamps import server_timestamp

router = APIRouter(prefix="/v1")


def _encode_cursor(created_at: datetime, trace_id: str) -> str:
    raw = f"{created_at.isoformat()}|{trace_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _to_utc(dt: datetime) -> datetime:
    # created_at is stored in UTC; SQLite compares wall-clock strings, so offsets must be normalized.
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


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
    db.flush()
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
    ensure_org_membership(db, user.id, payload.organization_id, "admin")
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
    project: Project = Depends(project_access(None, "admin")),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Project:
    changes: dict[str, object] = {}
    if payload.name is not None and payload.name != project.name:
        changes["name"] = {"from": project.name, "to": payload.name}
        project.name = payload.name
    if "description" in payload.model_fields_set:
        new_description = payload.description
        if isinstance(new_description, str) and new_description.strip() == "":
            new_description = None
        if new_description != project.description:
            changes["description"] = {"from": project.description, "to": new_description}
            project.description = new_description
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


def _encode_member_cursor(created_at: datetime, user_id: str) -> str:
    raw = f"{created_at.isoformat()}|{user_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode_member_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode()).decode()
        ca_str, user_id = raw.rsplit("|", 1)
        return datetime.fromisoformat(ca_str), user_id
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_cursor")


@router.get("/organizations/{org_id}/members")
def list_organization_members(
    org_id: str,
    limit: int = Query(50, ge=1, le=200),
    cursor: str | None = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    ensure_org_membership(db, user.id, org_id)
    query = (
        db.query(Membership, User)
        .join(User, User.id == Membership.user_id)
        .filter(Membership.organization_id == org_id)
    )
    if cursor:
        cursor_created_at, cursor_user_id = _decode_member_cursor(cursor)
        query = query.filter(
            or_(
                Membership.created_at > cursor_created_at,
                and_(Membership.created_at == cursor_created_at, Membership.user_id > cursor_user_id),
            )
        )
    rows = (
        query.order_by(Membership.created_at.asc(), Membership.user_id.asc())
        .limit(limit + 1)
        .all()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = (
        _encode_member_cursor(rows[-1][0].created_at, rows[-1][0].user_id) if has_more and rows else None
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
        ],
        "next_cursor": next_cursor,
    }


@router.get("/projects/{project_id}/api-keys")
def list_api_keys(
    project: Project = Depends(project_access(None, "admin")),
    db: Session = Depends(get_db),
) -> dict:
    return {"data": api_key_service.list_keys(db, project)}


@router.post("/projects/{project_id}/api-keys", status_code=status.HTTP_201_CREATED, response_model=ApiKeyCreateOut)
def create_api_key(
    payload: ApiKeyCreate,
    project: Project = Depends(project_access(None, "admin")),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiKeyCreateOut:
    return api_key_service.create_key(db, project, payload, user.id)


@router.post("/projects/{project_id}/api-keys/{key_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(
    key_id: str,
    project: Project = Depends(project_access(None, "admin")),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    key = api_key_service.revoke_key(db, project, key_id, user.id)
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")


@router.delete("/projects/{project_id}/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_api_key(
    key_id: str,
    project: Project = Depends(project_access(None, "destructive")),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    try:
        key = api_key_service.delete_key(db, project, key_id, user.id)
    except api_key_service.ApiKeyStillActiveError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="api_key_not_revoked",
        ) from exc
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
            return "timeout"
        if "schema" in message:
            return "schema_mismatch"
    return "partial_trace" if trace.status == "partial" else "trace_error"


def _delta_ms(later: datetime, earlier: datetime) -> int:
    if later.tzinfo is None and earlier.tzinfo is not None:
        earlier = earlier.replace(tzinfo=None)
    elif later.tzinfo is not None and earlier.tzinfo is None:
        later = later.replace(tzinfo=None)
    return max(0, int((later - earlier).total_seconds() * 1000))


@router.get("/projects/{project_id}/attention", response_model=AttentionResponse)
def get_project_attention(
    environment: str | None = Query(None, pattern=r"^(dev|staging|prod)$"),
    project: Project = Depends(get_owned_project),
    db: Session = Depends(get_db),
) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    query = (
        db.query(Trace)
        .filter(
            Trace.project_id == project.id,
            Trace.deleted_at.is_(None),
            Trace.status != "ok",
            Trace.created_at >= cutoff,
        )
    )
    if environment:
        query = query.filter(Trace.environment == environment)
    traces = query.order_by(Trace.created_at.desc()).limit(25).all()
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
    p95 = _p95_nearest_rank(ingestion_latencies)
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
    project: Project = Depends(project_access(None, "write")),
    db: Session = Depends(get_db),
) -> dict:
    now = utcnow()
    query = (
        db.query(Notification)
        .filter(Notification.project_id == project.id, Notification.read_at.is_(None))
        .filter(Notification.id.in_(payload.ids))
    )
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


# Priority of cost-source labels (worst-of-mix wins). Plain "unknown" beats
# everything; "provided" beats "priced" because a client-supplied number is
# less verifiable than a table-applied one. The UI uses this to surface the
# most degraded signal across spans, not the most flattering.
_COST_SOURCE_PRIORITY: dict[str, int] = {
    "unknown": 4,
    "unpriced": 3,
    "provided": 2,
    "priced": 1,
}


def _bulk_model_for_traces(db: Session, trace_ids: list[str]) -> dict[str, str]:
    """Model of each trace's newest LLM call: the one that produced the final answer."""
    if not trace_ids:
        return {}
    rows = (
        db.query(Span.trace_id, Span.model)
        .filter(Span.trace_id.in_(trace_ids), Span.type == "llm_call", Span.model.is_not(None))
        .order_by(Span.started_at)
        .all()
    )
    return dict(rows)


def _bulk_cost_source_for_traces(db: Session, trace_ids: list[str]) -> dict[str, str]:
    """Aggregate the per-span ``_cost_source`` metadata into a trace-level label.

    Spans without cost or tokens are ignored — they carry no cost signal and
    would otherwise drag every trace with a tool/eval span into "unknown".
    Falls back to the legacy aggregate-only heuristic for spans ingested
    before this metadata was being written.
    """
    if not trace_ids:
        return {}
    rows = (
        db.query(Span.trace_id, Span.metadata_json, Span.cost_usd, Span.tokens_in, Span.tokens_out)
        .filter(Span.trace_id.in_(trace_ids))
        .all()
    )
    per_trace: dict[str, str] = {}
    for trace_id, metadata, cost, tokens_in, tokens_out in rows:
        has_signal = (cost or 0) > 0 or (tokens_in or 0) > 0 or (tokens_out or 0) > 0
        if not has_signal:
            continue
        source = None
        if isinstance(metadata, dict):
            raw = metadata.get("_cost_source")
            if isinstance(raw, str) and raw in _COST_SOURCE_PRIORITY:
                source = raw
        if source is None:
            # Legacy span: no `_cost_source` written at ingest. Infer from
            # available signals so historical data still shows a label.
            if (cost or 0) > 0:
                source = "priced"
            elif (tokens_in or 0) + (tokens_out or 0) > 0:
                source = "unpriced"
            else:
                source = "unknown"
        prev = per_trace.get(trace_id)
        if prev is None or _COST_SOURCE_PRIORITY[source] > _COST_SOURCE_PRIORITY[prev]:
            per_trace[trace_id] = source
    return per_trace


def _classify_cost_source(trace: Trace, *, span_label: str | None = None) -> str:
    """Single-trace classifier kept for compatibility.

    Prefer ``_bulk_cost_source_for_traces`` for list-style queries; this helper
    is a single-row convenience used by the detail endpoint where we already
    have the spans loaded.
    """
    if span_label is not None:
        return span_label
    if (trace.total_cost_usd or 0) > 0:
        return "priced"
    if (trace.total_tokens_in or 0) > 0 or (trace.total_tokens_out or 0) > 0:
        return "unpriced"
    return "unknown"


_SLOW_KIND_TO_SPAN_PREDICATE: dict[str, object] = {
    "llm": Span.type == "llm_call",
    "retrieval": or_(
        Span.type == "retrieval",
        Span.name.ilike("retrieval.%"),
        Span.name.ilike("rag.retrieve%"),
    ),
}


@router.get("/traces")
def list_traces(
    trace_status: str | None = Query(None, alias="status"),
    environment: str | None = None,
    name: str | None = None,
    limit: int = 50,
    cursor: str | None = None,
    duration_gt: int | None = Query(None, ge=0),
    slow_kind: str | None = Query(None, pattern="^(trace|llm|retrieval)$"),
    rag: bool | None = Query(None),
    conversation_id: str | None = Query(None, max_length=255),
    flagged: bool | None = Query(None),
    since: datetime | None = None,
    until: datetime | None = None,
    tag: str | None = Query(None, max_length=255, pattern="^[^:]+:.+$"),
    user_ref: str | None = Query(None, max_length=255),
    model: str | None = Query(None, max_length=255),
    failed: bool | None = Query(None),
    score_lt: float | None = Query(None, ge=0, le=1),
    verdict: str | None = Query(None, pattern="^(approved|rejected|partial|unknown)$"),
    q: str | None = Query(None, max_length=255),
    project: Project = Depends(project_access("read")),
    db: Session = Depends(get_db),
) -> dict:
    project_id = project.id
    ranked = (
        select(
            EvaluationRun.trace_id,
            EvaluationRun.aggregate_score,
            EvaluationRun.passed,
            EvaluationRun.run_metadata,
            func.row_number().over(
                partition_by=EvaluationRun.trace_id,
                order_by=(EvaluationRun.created_at.desc(), EvaluationRun.id.desc()),
            ).label("rn"),
        )
        .where(EvaluationRun.project_id == project_id)
        .subquery()
    )
    # Compare the JSON boolean itself; text/number lookalikes must stay unknown.
    partial_failure = (
        cast(ranked.c.run_metadata["partial_failure"], String) == "true"
        if db.get_bind().dialect.name == "postgresql"
        else func.json_type(ranked.c.run_metadata, "$.partial_failure") == "true"
    )
    latest_verdict = case(
        (ranked.c.passed.is_(True), "approved"),
        (ranked.c.passed.is_(False), "rejected"),
        (partial_failure, "partial"),
        else_="unknown",
    )
    query = (
        db.query(Trace)
        .outerjoin(ranked, and_(ranked.c.trace_id == Trace.id, ranked.c.rn == 1))
        .filter(Trace.project_id == project_id, Trace.deleted_at.is_(None))
    )
    if verdict:
        query = query.filter(latest_verdict == verdict)
    if trace_status:
        status_values = [s.strip() for s in trace_status.split(",") if s.strip()]
        if len(status_values) == 1:
            query = query.filter(Trace.status == status_values[0])
        elif status_values:
            query = query.filter(Trace.status.in_(status_values))
    if environment:
        query = query.filter(Trace.environment == environment)
    if name:
        query = query.filter(Trace.name.ilike(f"%{name}%"))
    # Slowness contract:
    # - slow_kind="trace" or unset: legacy filter on Trace.duration_ms.
    # - slow_kind="llm": at least one llm_call span exceeds duration_gt.
    # - slow_kind="retrieval": at least one retrieval/rag.retrieve span exceeds duration_gt.
    # The reason that matched is exposed as `slow_reason` on each item.
    effective_slow_kind: str | None = None
    if duration_gt is not None:
        if slow_kind in {"llm", "retrieval"}:
            span_predicate = _SLOW_KIND_TO_SPAN_PREDICATE[slow_kind]
            slow_subq = (
                select(Span.trace_id)
                .where(span_predicate, Span.duration_ms > duration_gt)
                .scalar_subquery()
            )
            query = query.filter(Trace.id.in_(slow_subq))
            effective_slow_kind = slow_kind
        else:
            query = query.filter(Trace.duration_ms > duration_gt)
            effective_slow_kind = "trace"
    if rag is True:
        query = query.filter(_rag_filter_predicate())
    if conversation_id:
        query = query.filter(Trace.metadata_json["conversation_id"].as_string() == conversation_id)
    if flagged is True:
        query = query.filter(Trace.id.in_(select(TraceFlag.trace_id)))
    if since:
        query = query.filter(Trace.created_at >= _to_utc(since))
    if until:
        query = query.filter(Trace.created_at <= _to_utc(until))
    if tag:
        tag_key, tag_value = tag.split(":", 1)
        query = query.filter(Trace.tags[tag_key].as_string() == tag_value)
    if user_ref:
        query = query.filter(Trace.user_ref == user_ref)
    if model:
        query = query.filter(Trace.id.in_(select(Span.trace_id).where(Span.type == "llm_call", Span.model == model)))
    # shortcut: matches any run, not just the latest; upgrade when filtering by rubric
    if failed is True:
        query = query.filter(Trace.id.in_(select(EvaluationRun.trace_id).where(EvaluationRun.passed.is_(False))))
    if score_lt is not None:
        query = query.filter(Trace.id.in_(select(EvaluationRun.trace_id).where(EvaluationRun.aggregate_score < score_lt)))
    if q:
        query = query.filter(
            or_(
                Trace.name.ilike(f"%{q}%"),
                Trace.id == q,
                Trace.user_ref == q,
                Trace.metadata_json["conversation_id"].as_string() == q,
            )
        )
    if cursor:
        cursor_created_at, cursor_id = _decode_cursor(cursor)
        query = query.filter(
            or_(
                Trace.created_at < cursor_created_at,
                and_(Trace.created_at == cursor_created_at, Trace.id < cursor_id),
            )
        )
    page_limit = min(max(limit, 1), 200)
    page = (
        query.add_columns(ranked.c.aggregate_score, latest_verdict)
        .order_by(Trace.created_at.desc(), Trace.id.desc())
        .limit(page_limit + 1)
        .all()
    )
    has_more = len(page) > page_limit
    page = page[:page_limit]
    rows = [row for row, _, _ in page]
    trace_ids = [row.id for row in rows]
    cost_sources = _bulk_cost_source_for_traces(db, trace_ids)
    models = _bulk_model_for_traces(db, trace_ids)
    flag_counts = dict(
        db.query(TraceFlag.trace_id, func.count(TraceFlag.id))
        .filter(TraceFlag.trace_id.in_(trace_ids))
        .group_by(TraceFlag.trace_id)
        .all()
    )
    data = []
    for row, last_score, last_verdict in page:
        item = TraceOut.model_validate(row).model_dump()
        item["last_score"] = float(last_score) if last_score is not None else None
        item["last_verdict"] = last_verdict
        item["slow_reason"] = effective_slow_kind
        item["cost_source"] = _classify_cost_source(row, span_label=cost_sources.get(row.id))
        item["model"] = models.get(row.id)
        item["flag_count"] = flag_counts.get(row.id, 0)
        data.append(item)
    next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id) if has_more and rows else None
    return {"data": data, "next_cursor": next_cursor}


@router.get("/traces/{trace_id}")
def get_trace(
    trace: Trace = Depends(trace_access("read")),
    db: Session = Depends(get_db),
) -> dict:
    trace_id = trace.id
    spans = db.query(Span).filter(Span.trace_id == trace_id).order_by(Span.started_at).all()
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
            "created_at": server_timestamp(row.created_at),
        }
        for row in feedback
    ]
    cost_sources = _bulk_cost_source_for_traces(db, [trace_id])
    trace_out = TraceOut.model_validate(trace).model_dump()
    trace_out["cost_source"] = _classify_cost_source(trace, span_label=cost_sources.get(trace_id))
    trace_out["model"] = _bulk_model_for_traces(db, [trace_id]).get(trace_id)
    flags = (
        db.query(TraceFlag)
        .filter(TraceFlag.trace_id == trace_id)
        .order_by(TraceFlag.created_at.desc())
        .all()
    )
    return {
        "trace": trace_out,
        "spans": span_data,
        "events_count": len(events),
        "feedback": feedback_data,
        "flags": [
            {"id": row.id, "reason": row.reason, "note": row.note, "created_at": server_timestamp(row.created_at)}
            for row in flags
        ],
    }


@router.delete("/traces/{trace_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_trace(
    trace: Trace = Depends(trace_access(None, "destructive")),
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


def _evaluation_kpis(db: Session, traces) -> tuple[float | None, int]:
    """Mean score of each trace's newest rubric versions, and how many traces it covers.

    Errors and partial runs have no verdict (``passed`` is null): they are not quality evidence.
    """
    ranked = (
        select(
            EvaluationRun.trace_id,
            EvaluationRun.aggregate_score,
            EvaluationRun.passed,
            func.row_number()
            .over(
                partition_by=(EvaluationRun.trace_id, EvaluationRun.rubric_id),
                order_by=EvaluationRun.rubric_version.desc(),
            )
            .label("rn"),
        )
        .where(EvaluationRun.trace_id.in_(traces.with_entities(Trace.id)))
        .subquery()
    )
    average, covered = db.execute(
        select(func.avg(ranked.c.aggregate_score), func.count(func.distinct(ranked.c.trace_id))).where(
            ranked.c.rn == 1, ranked.c.passed.isnot(None)
        )
    ).one()
    return (round(float(average), 4) if average is not None else None), int(covered or 0)


def _human_feedback_kpis(db: Session, traces) -> dict:
    valid_rating = case((HumanFeedback.rating.between(1, 5), HumanFeedback.rating))
    count, trace_count, up, down, rating_count, average = db.execute(
        select(
            func.count(HumanFeedback.id),
            func.count(func.distinct(HumanFeedback.trace_id)),
            func.count(case((HumanFeedback.thumbs == "up", 1))),
            func.count(case((HumanFeedback.thumbs == "down", 1))),
            func.count(valid_rating),
            func.avg(valid_rating),
        ).where(HumanFeedback.trace_id.in_(traces.with_entities(Trace.id)))
    ).one()
    return {
        "feedback_count": int(count),
        "trace_count": int(trace_count),
        "thumbs_up": int(up),
        "thumbs_down": int(down),
        "rating_count": int(rating_count),
        "avg_rating": round(float(average), 4) if average is not None else None,
    }


@router.get("/analytics/overview")
def analytics_overview(
    environment: str | None = None,
    limit_days: int = 14,
    window: str | None = Query(default=None, pattern="^(24h|7d|30d)$"),
    project: Project = Depends(get_owned_project),
    db: Session = Depends(get_db),
) -> dict:
    project_id = project.id
    cutoff, day_cap = _resolve_overview_cutoff(window, limit_days)
    base_query = (
        db.query(Trace)
        .filter(Trace.project_id == project_id, Trace.deleted_at.is_(None))
        .filter(Trace.created_at >= cutoff)
    )
    if environment:
        base_query = base_query.filter(Trace.environment == environment)
    rows = base_query.all()
    human_feedback = _human_feedback_kpis(db, base_query)
    if not rows:
        return {
            "kpis": {
                "traces": 0,
                "cost_usd": 0.0,
                "latency_p95_ms": 0,
                "avg_score": None,
                "evaluated_traces": 0,
                "error_rate": 0.0,
            },
            "cost_by_day": [],
            "model_breakdown": [],
            "recent_flagged": [],
            "human_feedback": human_feedback,
        }

    avg_score, evaluated_traces = _evaluation_kpis(db, base_query)
    p95 = _p95_nearest_rank([row.duration_ms for row in rows])
    error_count = sum(1 for row in rows if row.status == "error")
    total_cost = float(sum(Decimal(str(row.total_cost_usd)) for row in rows))

    day_rows_query = (
        db.query(
            func.date(Trace.created_at).label("day"),
            func.sum(Trace.total_cost_usd).label("total_cost"),
            func.count(Trace.id).label("traces_count"),
        )
        .filter(Trace.project_id == project_id, Trace.deleted_at.is_(None))
        .filter(Trace.created_at >= cutoff)
    )
    if environment:
        day_rows_query = day_rows_query.filter(Trace.environment == environment)
    day_query = (
        day_rows_query
        .group_by(func.date(Trace.created_at))
        .order_by(func.date(Trace.created_at).desc())
    )
    if day_cap is not None:
        day_query = day_query.limit(day_cap)
    day_rows = list(reversed(day_query.all()))

    model_rows_query = (
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
        .filter(Trace.created_at >= cutoff)
    )
    if environment:
        model_rows_query = model_rows_query.filter(Trace.environment == environment)
    model_rows = (
        model_rows_query
        .group_by(Span.provider, Span.model)
        .order_by(func.sum(Span.cost_usd).desc())
        .all()
    )

    flagged_query = (
        db.query(Trace)
        .filter(Trace.project_id == project_id, Trace.deleted_at.is_(None))
        .filter(Trace.created_at >= cutoff)
        .filter(Trace.status.in_(["error", "partial"]))
    )
    if environment:
        flagged_query = flagged_query.filter(Trace.environment == environment)
    flagged = flagged_query.order_by(Trace.created_at.desc()).limit(10).all()

    return {
        "kpis": {
            "traces": len(rows),
            "cost_usd": round(total_cost, 6),
            "latency_p95_ms": p95,
            "avg_score": avg_score,
            "evaluated_traces": evaluated_traces,
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
        "human_feedback": human_feedback,
    }
