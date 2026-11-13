"""Read-only inventories. Queries deliberately select counts, IDs and cost fields only."""
from collections import defaultdict
from datetime import timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import extract, func, or_
from sqlalchemy.orm import Session

from app import models as m
from app.db import Base
from app.api.schemas_deletion_preview import (
    DeletionCost, DeletionDependency, DeletionMembership, DeletionPreview,
)
from app.domain.services.sampling_service import TERMINAL_STATUSES as SAMPLING_TERMINAL
from app.domain.tasks.execution_budget import usd
from app.domain.tasks.immutability import PROTECTED, statements as immutability_statements


# Tables whose rows a BEFORE DELETE trigger refuses to remove.
DELETE_GUARDED = sorted({sql.split(" ON ")[1].split()[0] for sql in immutability_statements("sqlite") if "BEFORE DELETE" in sql})

LIMITATIONS = [
    "execution_contract_not_approved", "concurrent_changes_can_change_inventory",
    "file_references_not_filesystem_verification", "unknown_costs_are_not_zero",
]


def _count(db: Session, model, predicate) -> int:
    return db.query(func.count()).select_from(model).filter(predicate).scalar()


def _non_cascading(target: str):
    # Derived from metadata: FKs that neither cascade nor null out keep (and block) the parent row.
    return [fk.parent for table in Base.metadata.sorted_tables for fk in table.foreign_keys
            if fk.column.table.name == target and fk.column.name == "id"
            and (fk.constraint.ondelete or "").upper() not in ("CASCADE", "SET NULL")]


def _costs(db: Session, projects) -> list[DeletionCost]:
    result = []
    # PG extract()/datetimes follow the session TimeZone; SQLite stores naive UTC.
    postgres = db.get_bind().dialect.name == "postgresql"
    for model, amount, source in (
        (m.Trace, m.Trace.total_cost_usd, "trace_records"),
        (m.EvaluationRun, m.EvaluationRun.cost_usd, "evaluation_run_records"),
    ):
        created = func.timezone("UTC", model.created_at) if postgres else model.created_at
        year, month = extract("year", created), extract("month", created)
        rows = db.query(year, month, func.sum(amount), func.count() - func.count(amount)).filter(
            model.project_id.in_(projects)).group_by(year, month).order_by(year, month)
        for y, mo, total, unknown in rows:  # PG extract() returns numeric, not int
            result.append(DeletionCost(period=f"{int(y):04d}-{int(mo):02d}", source=source,
                known_cost_usd=total or Decimal(0), unknown_cost_records=unknown))
    totals = defaultdict(lambda: [Decimal(0), 0])
    # Experiment costs live in variant summaries, not in a scalar run column.
    for created_at, variants in db.query(m.ExperimentRun.created_at, m.ExperimentRun.by_variant).filter(
            m.ExperimentRun.project_id.in_(projects)).yield_per(200):
        if created_at.tzinfo is not None:
            created_at = created_at.astimezone(timezone.utc)
        bucket = totals[created_at.strftime("%Y-%m")]
        unknown = not isinstance(variants, dict) or not variants
        for metrics in variants.values() if not unknown else ():
            try:
                value = Decimal(str(metrics["total_cost_usd"]))
                if not value.is_finite() or value < 0:
                    raise ValueError("invalid_cost")
            except (KeyError, TypeError, ValueError, InvalidOperation):
                unknown = True
            else:
                bucket[0] += value
        bucket[1] += unknown  # at most one unknown record per run
    result.extend(DeletionCost(period=period, source="experiment_variant_records",
        known_cost_usd=total, unknown_cost_records=unknown) for period, (total, unknown) in sorted(totals.items()))
    return result


def content_preview(db: Session, *, scope: str, target_id: str, organization_id: str) -> DeletionPreview:
    projects = db.query(m.Project.id).filter(m.Project.organization_id == organization_id)
    if scope == "project":
        projects = projects.filter(m.Project.id == target_id)
    traces = db.query(m.Trace.id).filter(m.Trace.project_id.in_(projects))
    spans = db.query(m.Span.id).filter(m.Span.trace_id.in_(traces))
    rubrics = db.query(m.Rubric.id).filter(m.Rubric.project_id.in_(projects))
    versions = db.query(m.RubricVersion.id).filter(m.RubricVersion.rubric_id.in_(rubrics))
    evaluators = db.query(m.EvaluatorRow.id).filter(m.EvaluatorRow.rubric_version_id.in_(versions))
    prompts = db.query(m.Prompt.id).filter(m.Prompt.project_id.in_(projects))
    datasets = db.query(m.Dataset.id).filter(m.Dataset.project_id.in_(projects))
    runs = db.query(m.EvaluationRun.id).filter(m.EvaluationRun.project_id.in_(projects))
    models = (m.ApiKey, m.Trace, m.Rubric, m.EvaluationRun, m.Prompt, m.Dataset,
              m.Experiment, m.ExperimentRun, m.ExportJob, m.Notification,
              m.EvaluationSamplingConfig, m.EvaluationSamplingJob, m.QualityGateConfig,
              m.ServicePrincipal, m.ModelVersion, m.DatasetSnapshot, m.PredictionSet, m.TaskEvaluation, m.TaskReceipt,
              m.ExperimentRunEvaluation, m.Investigation, m.InvestigationRevision, m.Execution, m.ExecutionAttempt,
              m.ExecutionPolicyRevision, m.Runner, m.RunnerCredential, m.ProjectExecutionAccount, m.ExecutionPlan,
              m.ExecutionReservation, m.ExecutionLedgerEntry, m.ExecutionSchedule, m.ExecutionLease, m.ExecutionLateReport)
    # Children without a leading project_id index are scoped through their indexed parent FK.
    executions = db.query(m.Execution.id).filter(m.Execution.project_id.in_(projects))
    via_parent = {
        m.ExecutionAttempt: m.ExecutionAttempt.execution_id.in_(executions),
        m.ExecutionLedgerEntry: m.ExecutionLedgerEntry.execution_id.in_(executions),
        m.ExecutionSchedule: m.ExecutionSchedule.execution_id.in_(executions),
        m.ExecutionLateReport: m.ExecutionLateReport.execution_id.in_(executions),
        m.InvestigationRevision: m.InvestigationRevision.investigation_id.in_(
            db.query(m.Investigation.id).filter(m.Investigation.project_id.in_(projects))),
        m.RunnerCredential: m.RunnerCredential.runner_id.in_(db.query(m.Runner.id).filter(m.Runner.project_id.in_(projects))),
        m.ExperimentRunEvaluation: m.ExperimentRunEvaluation.run_id.in_(
            db.query(m.ExperimentRun.id).filter(m.ExperimentRun.project_id.in_(projects))),
    }

    def in_scope(model):
        return via_parent[model] if model in via_parent else model.project_id.in_(projects)

    counts = {model.__tablename__: _count(db, model, in_scope(model)) for model in models}
    counts["projects"] = projects.count()
    counts["hidden_traces"] = traces.filter(m.Trace.deleted_at.is_not(None)).count()
    counts["archived_projects"] = projects.filter(m.Project.archived_at.is_not(None)).count()
    for model, predicate in (
        (m.Span, m.Span.trace_id.in_(traces)), (m.Event, m.Event.span_id.in_(spans)),
        (m.TraceFlag, m.TraceFlag.trace_id.in_(traces)), (m.HumanFeedback, m.HumanFeedback.trace_id.in_(traces)),
        (m.RubricVersion, m.RubricVersion.rubric_id.in_(rubrics)),
        (m.EvaluatorRow, m.EvaluatorRow.rubric_version_id.in_(versions)),
        (m.EvaluationScore, m.EvaluationScore.run_id.in_(runs)),
        (m.PromptVersion, m.PromptVersion.prompt_id.in_(prompts)),
        (m.DatasetItem, m.DatasetItem.dataset_id.in_(datasets)),
        (m.SnapshotItem, m.SnapshotItem.snapshot_id.in_(db.query(m.DatasetSnapshot.id).filter(m.DatasetSnapshot.project_id.in_(projects)))),
        (m.Prediction, m.Prediction.set_id.in_(db.query(m.PredictionSet.id).filter(m.PredictionSet.project_id.in_(projects)))),
        (m.MetricFact, m.MetricFact.task_evaluation_id.in_(db.query(m.TaskEvaluation.id).filter(m.TaskEvaluation.project_id.in_(projects)))),
    ):
        counts[model.__tablename__] = _count(db, model, predicate)
    for key, model, predicate in (
        ("active_service_principals", m.ServicePrincipal, m.ServicePrincipal.disabled_at.is_(None)),
        ("active_runners", m.Runner, m.Runner.disabled_at.is_(None)),
        ("unrevoked_runner_credentials", m.RunnerCredential, m.RunnerCredential.revoked_at.is_(None)),
    ):
        counts[key] = _count(db, model, in_scope(model) & predicate)
    dependencies = [DeletionDependency(code="execution_contract_not_approved", count=1)]
    for code, model, predicate in (
        ("rubric_evaluation_references", m.EvaluationRun, m.EvaluationRun.rubric_id.in_(rubrics)),
        ("evaluator_score_references", m.EvaluationScore, m.EvaluationScore.evaluator_row_id.in_(evaluators)),
        ("dataset_experiment_references", m.Experiment, m.Experiment.dataset_id.in_(datasets)),
        ("rubric_experiment_references", m.Experiment, m.Experiment.rubric_id.in_(rubrics)),
        ("rubric_sampling_config_references", m.EvaluationSamplingConfig, m.EvaluationSamplingConfig.rubric_id.in_(rubrics)),
        ("rubric_sampling_job_references", m.EvaluationSamplingJob, m.EvaluationSamplingJob.rubric_id.in_(rubrics)),
    ):
        count = _count(db, model, predicate)
        if count:
            dependencies.append(DeletionDependency(code=code, count=count))
    # Statuses as written by eval_service, routes_phase5, export_service and sampling_service.
    for code, model, predicate in (
        ("evaluation_runs_in_flight", m.EvaluationRun, m.EvaluationRun.status == "running"),
        ("experiment_runs_in_flight", m.ExperimentRun, m.ExperimentRun.status == "running"),
        ("export_jobs_in_flight", m.ExportJob, m.ExportJob.status.in_(["pending", "running"])),
        ("evaluation_sampling_jobs_in_flight", m.EvaluationSamplingJob,
         m.EvaluationSamplingJob.status.not_in(SAMPLING_TERMINAL)),
        ("evaluation_sampling_jobs_possible_charge", m.EvaluationSamplingJob, m.EvaluationSamplingJob.status == "uncertain"),
        ("replay_in_flight", m.Trace, m.Trace.metadata_json["replay_status"].as_string().in_(["queued", "running"])),
        # Task/execution statuses per their CHECK constraints; uncertain/unknown may hide spend.
        ("executions_in_flight", m.Execution, m.Execution.status.in_(["queued", "running"])),
        ("executions_possible_charge", m.Execution, m.Execution.status == "uncertain"),
        ("task_evaluations_in_flight", m.TaskEvaluation, m.TaskEvaluation.status.in_(["queued", "running"])),
        ("execution_reservations_held", m.ExecutionReservation, m.ExecutionReservation.state == "reserved"),
        ("execution_reservations_unknown", m.ExecutionReservation, m.ExecutionReservation.state == "unknown"),
        ("execution_leases_active", m.ExecutionLease, m.ExecutionLease.state == "active"),
    ):
        count = _count(db, model, model.project_id.in_(projects) & predicate)
        if count:
            dependencies.append(DeletionDependency(code=code, count=count))
    revoked = _count(db, m.ApiKey, m.ApiKey.project_id.in_(projects) & m.ApiKey.revoked_at.is_not(None))
    principal_keys = m.ApiKey.project_id.in_(projects) & m.ApiKey.service_principal_id.is_not(None)
    api_keys = {"total": counts["api_keys"], "revoked": revoked, "unrevoked": counts["api_keys"] - revoked,
                "service_principal_total": _count(db, m.ApiKey, principal_keys),
                "service_principal_revoked": _count(db, m.ApiKey, principal_keys & m.ApiKey.revoked_at.is_not(None))}
    files = db.query(func.count(func.distinct(m.ExportJob.file_path))).filter(
        m.ExportJob.project_id.in_(projects), m.ExportJob.file_path.is_not(None), m.ExportJob.file_path != "").scalar()
    costs = _costs(db, projects)
    excluded = ["other_organizations", "personal_identities", "downloads_and_third_party_copies", "backups"]
    if scope == "organization":
        for model in (m.Membership, m.OrganizationInvitation, m.Subscription, m.UsageCounter, m.AuditLog,
                      m.OrganizationExecutionBudgetRevision, m.OrganizationExecutionAccount):
            counts[model.__tablename__] = _count(db, model, model.organization_id == organization_id)
        accounts = db.query(m.OrganizationExecutionAccount.period, m.OrganizationExecutionAccount.spent_units).filter(
            m.OrganizationExecutionAccount.organization_id == organization_id)
        for period, total, replay in db.query(m.UsageCounter.period, m.UsageCounter.cost_usd, m.UsageCounter.replay_cost_usd).filter(
                m.UsageCounter.organization_id == organization_id).order_by(m.UsageCounter.period):
            costs.extend([
                DeletionCost(period=period, source="organization_usage_counter", known_cost_usd=total),
                DeletionCost(period=period, source="organization_replay_counter", known_cost_usd=replay),
            ])
        dependencies.append(DeletionDependency(code="organization_finance_audit_policy_unresolved", count=1))
        invitations = _count(db, m.OrganizationInvitation, (m.OrganizationInvitation.organization_id == organization_id)
                             & m.OrganizationInvitation.status.in_(["pending", "sending"]))
        if invitations:
            dependencies.append(DeletionDependency(code="invitations_in_flight", count=invitations))
        # Delivered, unexpired invitations can still be accepted and create memberships.
        open_invitations = _count(db, m.OrganizationInvitation, (m.OrganizationInvitation.organization_id == organization_id)
                                  & (m.OrganizationInvitation.status == "sent") & m.OrganizationInvitation.revoked_at.is_(None)
                                  & (m.OrganizationInvitation.expires_at > m.utcnow()))
        if open_invitations:
            dependencies.append(DeletionDependency(code="invitations_open", count=open_invitations))
    else:
        excluded.extend(["other_projects", "organization_memberships", "organization_finance_and_audit"])
        accounts = db.query(m.ProjectExecutionAccount.period, func.sum(m.ProjectExecutionAccount.spent_units)).filter(
            m.ProjectExecutionAccount.project_id.in_(projects)).group_by(m.ProjectExecutionAccount.period)
    # Settled execution spend is booked per UTC period in execution accounts, never in usage_counters.
    costs.extend(DeletionCost(period=period, source="execution_account_spent", known_cost_usd=usd(spent or 0))
                 for period, spent in sorted(accounts))
    # UPDATE guards and DELETE guards protect different sets of evidence.
    conditional = {
        "task_evaluations": m.TaskEvaluation.project_id.in_(projects) & m.TaskEvaluation.status.not_in(["queued", "running"]),
        "experiment_runs": m.ExperimentRun.project_id.in_(projects) & (m.ExperimentRun.kind == "task_comparison")
                           & m.ExperimentRun.status.in_(["completed", "error"]),
    }
    immutable = sum(counts.get(table, 0) for table in PROTECTED if table not in conditional)
    immutable += _count(db, m.TaskEvaluation, conditional["task_evaluations"]) + _count(db, m.ExperimentRun, conditional["experiment_runs"])
    ledger = counts["execution_ledger_entries"]
    references = [("non_cascading_project_references",
                   sum(_count(db, column.table, column.in_(projects)) for column in _non_cascading("projects")))]
    if scope == "organization":
        references.append(("non_cascading_organization_references",
                           sum(_count(db, column.table, column == organization_id) for column in _non_cascading("organizations"))))
    for code, count in (("immutable_records", immutable), ("delete_blocked_records", sum(counts[t] for t in DELETE_GUARDED)),
                        (f"{scope}_delete_blocked_by_ledger", ledger), *references):
        if count:
            dependencies.append(DeletionDependency(code=code, count=count))
    return DeletionPreview(scope=scope, target_id=target_id, resource_counts=counts, api_keys=api_keys,
        managed_file_references=files, dependencies=dependencies, known_costs=costs,
        excluded_scopes=excluded, limitations=LIMITATIONS + ["cost_sources_overlap_do_not_sum", "period_uses_record_created_at_utc",
                                                             "execution_reserved_units_are_not_costs"])


def account_preview(db: Session, user: m.User) -> DeletionPreview:
    memberships = []
    dependencies = [DeletionDependency(code="account_identity_and_attribution_policy_unresolved", count=1)]
    for org_id, role in db.query(m.Membership.organization_id, m.Membership.role).filter(
            m.Membership.user_id == user.id).order_by(m.Membership.organization_id):
        owners = _count(db, m.Membership, (m.Membership.organization_id == org_id) & (m.Membership.role == "owner"))
        last_owner = role == "owner" and owners == 1
        memberships.append(DeletionMembership(organization_id=org_id, role=role, last_owner=last_owner))
        if last_owner:
            dependencies.append(DeletionDependency(code="last_owner_transfer_required", count=1, organization_id=org_id))
    counts = {"users": 1, "memberships": len(memberships)}
    for model, predicate in (
        (m.PasswordReset, m.PasswordReset.user_id == user.id),
        (m.PromptVersion, m.PromptVersion.created_by == user.id),
        (m.RubricVersion, m.RubricVersion.created_by == user.id),
        (m.ExportJob, m.ExportJob.created_by == user.id),
        (m.TraceFlag, m.TraceFlag.user_id == user.id),
        (m.AuditLog, m.AuditLog.actor_user_id == user.id),
        (m.OrganizationInvitation, or_(m.OrganizationInvitation.invited_by_user_id == user.id,
                                      func.lower(m.OrganizationInvitation.email) == user.email.lower())),
    ):
        counts[model.__tablename__] = _count(db, model, predicate)
        if model in (m.PromptVersion, m.RubricVersion, m.ExportJob, m.AuditLog) and counts[model.__tablename__]:
            dependencies.append(DeletionDependency(code=f"{model.__tablename__}_user_references", count=counts[model.__tablename__]))
    counts["task_receipts"] = _count(db, m.TaskReceipt, m.TaskReceipt.actor_id == user.id)
    for model in (m.Runner, m.ServicePrincipal):  # required owner FK
        counts[model.__tablename__] = _count(db, model, model.owner_user_id == user.id)
        if counts[model.__tablename__]:
            dependencies.append(DeletionDependency(code=f"{model.__tablename__}_user_references", count=counts[model.__tablename__]))
    # Attribution columns covered by immutability triggers cannot be rewritten (e.g. anonymized).
    immutable = counts["runners"] + sum(_count(db, model, predicate) for model, predicate in (
        (m.Execution, m.Execution.created_by == user.id), (m.ExecutionPlan, m.ExecutionPlan.created_by == user.id),
        (m.DatasetSnapshot, m.DatasetSnapshot.created_by == user.id),
        # Same trigger condition as immutable_records: only terminal task evaluations are frozen.
        (m.TaskEvaluation, (m.TaskEvaluation.created_by == user.id) & m.TaskEvaluation.status.not_in(["queued", "running"])),
        (m.ExecutionPolicyRevision, m.ExecutionPolicyRevision.created_by == user.id),
        (m.OrganizationExecutionBudgetRevision, m.OrganizationExecutionBudgetRevision.created_by == user.id),
        (m.InvestigationRevision, m.InvestigationRevision.author_id == user.id),
        (m.ExecutionLedgerEntry, m.ExecutionLedgerEntry.actor_id == user.id),
    ))
    if immutable:
        dependencies.append(DeletionDependency(code="immutable_user_attribution", count=immutable))
    return DeletionPreview(scope="account", target_id=user.id, resource_counts=counts,
        memberships=memberships, dependencies=dependencies,
        excluded_scopes=["collective_content", "project_api_keys", "organization_costs", "other_users", "backups", "third_party_copies"],
        limitations=LIMITATIONS + ["sessions_not_enumerable_by_user", "personal_data_in_payloads_not_scanned",
                                   "account_scan_unindexed"])
