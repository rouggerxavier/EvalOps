from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import ensure_org_membership, get_current_user, get_project_from_api_key
from app.domain.services.usage_service import enforce_quota, increment_usage
from app.infra.llm.pricing import compute_cost_usd
from app.models import ApiKey, Event, HumanFeedback, Membership, Organization, Project, Span, Trace, User
from app.schemas import (
    ApiKeyCreate,
    ApiKeyCreateOut,
    ApiKeyOut,
    OrganizationCreate,
    OrganizationOut,
    ProjectCreate,
    ProjectOut,
    TraceBatchIn,
    TraceOut,
)
from app.security import generate_api_key, hash_api_key, new_id

router = APIRouter(prefix="/v1")


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
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/projects/{project_id}/api-keys")
def list_api_keys(
    project_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    project = db.get(Project, project_id)
    if not project or project.archived_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    ensure_org_membership(db, user.id, project.organization_id)
    keys = (
        db.query(ApiKey)
        .filter(ApiKey.project_id == project_id)
        .order_by(ApiKey.created_at.desc())
        .all()
    )
    data = [
        ApiKeyOut(
            id=k.id,
            prefix=k.prefix,
            name=k.name,
            environment=k.environment,
            scopes=[s for s in k.scopes.split(",") if s],
            rate_limit_per_minute=k.rate_limit_per_minute,
            created_at=k.created_at,
            revoked_at=k.revoked_at,
        ).model_dump()
        for k in keys
    ]
    return {"data": data}


@router.post("/projects/{project_id}/api-keys", status_code=status.HTTP_201_CREATED, response_model=ApiKeyCreateOut)
def create_api_key(
    project_id: str,
    payload: ApiKeyCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiKeyCreateOut:
    project = db.get(Project, project_id)
    if not project or project.archived_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    ensure_org_membership(db, user.id, project.organization_id)
    raw_key, prefix = generate_api_key(payload.environment)
    scopes = ",".join(payload.scopes)
    row = ApiKey(
        id=new_id("key"),
        project_id=project_id,
        prefix=prefix,
        hash=hash_api_key(raw_key),
        name=payload.name,
        environment=payload.environment,
        scopes=scopes,
        rate_limit_per_minute=60,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ApiKeyCreateOut(
        id=row.id,
        prefix=row.prefix,
        name=row.name,
        environment=row.environment,
        scopes=payload.scopes,
        rate_limit_per_minute=row.rate_limit_per_minute,
        created_at=row.created_at,
        revoked_at=row.revoked_at,
        key=raw_key,
    )


@router.post("/projects/{project_id}/api-keys/{key_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(
    project_id: str,
    key_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    project = db.get(Project, project_id)
    if not project or project.archived_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    ensure_org_membership(db, user.id, project.organization_id)
    key = db.get(ApiKey, key_id)
    if not key or key.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    if key.revoked_at is None:
        from app.models import utcnow

        key.revoked_at = utcnow()
        db.add(key)
        db.commit()


@router.post("/traces", status_code=status.HTTP_202_ACCEPTED)
def ingest_traces(
    payload: TraceBatchIn,
    project: Project = Depends(get_project_from_api_key),
    db: Session = Depends(get_db),
) -> dict:
    enforce_quota(db, project, "traces_ingested", len(payload.traces))
    results: list[dict] = []
    errors: list[dict] = []

    for idx, trace_in in enumerate(payload.traces):
        try:
            if trace_in.ended_at < trace_in.started_at:
                raise ValueError("ended_at must be >= started_at")

            if trace_in.client_trace_id:
                existing = (
                    db.query(Trace)
                    .filter(
                        Trace.project_id == project.id,
                        Trace.client_trace_id == trace_in.client_trace_id,
                    )
                    .one_or_none()
                )
                if existing is not None:
                    results.append({"client_trace_id": trace_in.client_trace_id, "trace_id": existing.id})
                    continue

            trace_id = new_id("tr")
            duration_ms = int((trace_in.ended_at - trace_in.started_at).total_seconds() * 1000)
            trace_row = Trace(
                id=trace_id,
                project_id=project.id,
                organization_id=project.organization_id,
                client_trace_id=trace_in.client_trace_id,
                name=trace_in.name,
                service=trace_in.service,
                environment=trace_in.environment,
                status=trace_in.status,
                started_at=trace_in.started_at,
                ended_at=trace_in.ended_at,
                duration_ms=duration_ms,
                tags=trace_in.tags,
                user_ref=trace_in.user_ref,
                metadata_json=trace_in.metadata,
                redacted=False,
            )
            db.add(trace_row)
            db.flush()

            client_to_span: dict[str, str] = {}
            fallback_refs: list[tuple[Span, str]] = []
            parent_refs: list[tuple[Span, str]] = []
            total_in = 0
            total_out = 0
            total_cost = Decimal("0")

            for span_in in trace_in.spans:
                if span_in.ended_at < span_in.started_at:
                    raise ValueError(f"span '{span_in.client_span_id}' has invalid timestamps")
                span_id = new_id("sp")
                client_to_span[span_in.client_span_id] = span_id
                duration_span_ms = int((span_in.ended_at - span_in.started_at).total_seconds() * 1000)
                if span_in.cost_usd is None:
                    cost = compute_cost_usd(span_in.provider, span_in.model, span_in.tokens_in, span_in.tokens_out)
                else:
                    cost = Decimal(str(span_in.cost_usd))
                row = Span(
                    id=span_id,
                    trace_id=trace_id,
                    parent_span_id=None,
                    type=span_in.type,
                    name=span_in.name,
                    status=span_in.status,
                    started_at=span_in.started_at,
                    ended_at=span_in.ended_at,
                    duration_ms=duration_span_ms,
                    provider=span_in.provider,
                    model=span_in.model,
                    prompt_version_ref=span_in.prompt_version_ref,
                    messages_in=span_in.messages_in,
                    messages_out=span_in.messages_out,
                    tools=span_in.tools,
                    tokens_in=span_in.tokens_in,
                    tokens_out=span_in.tokens_out,
                    cost_usd=float(cost),
                    fallback_from_span_id=None,
                    input=span_in.input,
                    output=span_in.output,
                    error=span_in.error,
                    metadata_json=span_in.metadata,
                )
                db.add(row)
                if span_in.parent_client_span_id:
                    parent_refs.append((row, span_in.parent_client_span_id))
                if span_in.fallback_from_client_span_id:
                    fallback_refs.append((row, span_in.fallback_from_client_span_id))
                total_in += span_in.tokens_in or 0
                total_out += span_in.tokens_out or 0
                total_cost += cost
                for event_in in span_in.events:
                    db.add(
                        Event(
                            id=new_id("ev"),
                            span_id=span_id,
                            type=event_in.type,
                            occurred_at=event_in.occurred_at,
                            payload=event_in.payload,
                        )
                    )

            for span_row, parent_client_id in parent_refs:
                parent_id = client_to_span.get(parent_client_id)
                if parent_id is None:
                    raise ValueError(f"parent span '{parent_client_id}' not found")
                span_row.parent_span_id = parent_id

            for span_row, fallback_client_id in fallback_refs:
                fallback_id = client_to_span.get(fallback_client_id)
                if fallback_id:
                    span_row.fallback_from_span_id = fallback_id

            trace_row.total_tokens_in = total_in
            trace_row.total_tokens_out = total_out
            trace_row.total_cost_usd = float(total_cost)
            db.add(trace_row)
            db.commit()
            increment_usage(db, project.organization_id, traces=1, cost_usd=float(total_cost))
            db.commit()
            results.append({"client_trace_id": trace_in.client_trace_id, "trace_id": trace_id})
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            errors.append({"index": idx, "client_trace_id": trace_in.client_trace_id, "message": str(exc)})

    return {"ingested": len(results), "results": results, "errors": errors}


@router.get("/traces")
def list_traces(
    project_id: str,
    status: str | None = None,
    environment: str | None = None,
    name: str | None = None,
    limit: int = 50,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    project = db.get(Project, project_id)
    if not project or project.archived_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    ensure_org_membership(db, user.id, project.organization_id)
    query = db.query(Trace).filter(Trace.project_id == project_id)
    if status:
        query = query.filter(Trace.status == status)
    if environment:
        query = query.filter(Trace.environment == environment)
    if name:
        query = query.filter(Trace.name.ilike(f"%{name}%"))
    rows = query.order_by(Trace.created_at.desc()).limit(min(max(limit, 1), 200)).all()
    data = [TraceOut.model_validate(row).model_dump() for row in rows]
    return {"data": data, "next_cursor": None}


@router.get("/traces/{trace_id}")
def get_trace(
    trace_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    trace = db.get(Trace, trace_id)
    if not trace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    ensure_org_membership(db, user.id, trace.organization_id)
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
    trace_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    trace = db.get(Trace, trace_id)
    if not trace:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    ensure_org_membership(db, user.id, trace.organization_id)
    db.delete(trace)
    db.commit()


@router.get("/analytics/overview")
def analytics_overview(
    project_id: str,
    environment: str | None = None,
    limit_days: int = 14,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    project = db.get(Project, project_id)
    if not project or project.archived_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not_found")
    ensure_org_membership(db, user.id, project.organization_id)

    base_query = db.query(Trace).filter(Trace.project_id == project_id)
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
        .filter(Trace.project_id == project_id)
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
        .filter(Trace.project_id == project_id, Span.type == "llm_call")
        .group_by(Span.provider, Span.model)
        .order_by(func.sum(Span.cost_usd).desc())
        .all()
    )

    flagged = (
        db.query(Trace)
        .filter(Trace.project_id == project_id)
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
