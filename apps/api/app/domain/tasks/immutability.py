"""Database guards protect materialized evidence, including writes outside the ORM."""
from sqlalchemy import DDL, event

PROTECTED = {
    "organization_execution_budget_revisions": ("id", "organization_id", "version", "content", "content_hash", "created_by", "created_at"),
    "execution_plans": ("id", "project_id", "environment", "runner_id", "policy_revision_id", "organization_budget_revision_id", "manifest_content", "manifest_hash", "created_by", "created_at"),
    "execution_ledger_entries": ("id", "execution_id", "project_id", "organization_id", "attempt_id", "period", "kind", "event_key", "amount_usd", "measurement_source", "pricing_version", "actor_id", "created_at"),
    "execution_policy_revisions": ("id", "project_id", "version", "content", "content_hash", "created_by", "created_at"),
    "runners": ("id", "project_id", "name", "owner_user_id", "capabilities", "created_at"),
    "execution_schedules": ("execution_id", "project_id", "plan_id", "actor_context", "created_at"),
    "executions": ("id", "project_id", "environment", "origin", "mode", "manifest_hash", "manifest_content", "created_by", "created_at"),
    "execution_attempts": ("id", "execution_id", "project_id", "environment", "attempt_number", "result_hash", "result_content", "created_at"),
    "investigation_revisions": ("id", "investigation_id", "project_id", "environment", "revision", "state", "access_label", "author_kind", "author_id", "created_at"),
    "model_versions": ("id", "project_id", "created_at", "name", "version_ref", "content_hash", "content"),
    "dataset_snapshots": ("id", "project_id", "created_at", "dataset_id", "content_hash", "item_count", "content", "created_by"),
    "snapshot_items": ("snapshot_id", "sample_id", "content"),
    "prediction_sets": ("id", "project_id", "created_at", "snapshot_id", "model_version_id", "environment", "content_hash", "producer_manifest", "provenance"),
    "predictions": ("set_id", "sample_id", "snapshot_id", "content"),
    "task_evaluations": ("id", "project_id", "created_at", "prediction_set_id", "environment", "status", "decision", "decision_reasons", "result", "created_by"),
    "experiment_runs": ("id", "project_id", "experiment_id", "kind", "status", "passed", "decision", "decision_reasons", "by_variant", "comparisons", "criteria_failures", "run_metadata", "started_at", "completed_at", "created_at"),
    "metric_facts": ("id", "task_evaluation_id", "definition_id", "definition_version", "scope", "scope_key", "content"),
}
PG_FUNCTION = """CREATE OR REPLACE FUNCTION evalops_immutable_task_row() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'immutable_task_resource'; END; $$"""


def condition(table):
    if table == "task_evaluations":
        return " WHEN (OLD.status NOT IN ('queued','running'))"
    if table == "experiment_runs":
        return " WHEN (OLD.kind = 'task_comparison' AND OLD.status IN ('completed','error'))"
    return ""


def statements(dialect):
    if dialect == "postgresql":
        yield PG_FUNCTION
    for table, columns in PROTECTED.items():
        when = condition(table)
        if dialect == "sqlite":
            yield f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OF {','.join(columns)} ON {table}{when} BEGIN SELECT RAISE(ABORT, 'immutable_task_resource'); END"
        elif dialect == "postgresql":
            yield f"CREATE TRIGGER immutable_{table} BEFORE UPDATE OF {','.join(columns)} ON {table} FOR EACH ROW{when} EXECUTE FUNCTION evalops_immutable_task_row()"

    if dialect == "sqlite":
        yield "CREATE TRIGGER immutable_execution_terminal_status BEFORE UPDATE OF status ON executions WHEN (OLD.status NOT IN ('queued','running')) BEGIN SELECT RAISE(ABORT, 'immutable_task_resource'); END"
    elif dialect == "postgresql":
        yield "CREATE TRIGGER immutable_execution_terminal_status BEFORE UPDATE OF status ON executions FOR EACH ROW WHEN (OLD.status NOT IN ('queued','running')) EXECUTE FUNCTION evalops_immutable_task_row()"

    if dialect == "sqlite":
        yield "CREATE TRIGGER immutable_execution_ledger_delete BEFORE DELETE ON execution_ledger_entries BEGIN SELECT RAISE(ABORT, 'immutable_task_resource'); END"
    elif dialect == "postgresql":
        yield "CREATE TRIGGER immutable_execution_ledger_delete BEFORE DELETE ON execution_ledger_entries FOR EACH ROW EXECUTE FUNCTION evalops_immutable_task_row()"


def register(metadata):
    for dialect in ("sqlite", "postgresql"):
        for statement in statements(dialect):
            if statement == PG_FUNCTION:
                event.listen(metadata, "before_create", DDL(statement).execute_if(dialect=dialect))
            else:
                table = statement.split(" ON ")[1].split()[0]
                event.listen(metadata.tables[table], "after_create", DDL(statement).execute_if(dialect=dialect))
