"""task foundations

Revision ID: 0014_task_foundations
Revises: 0013_user_credential_version
Create Date: 2026-11-10 10:43:33.331491

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0014_task_foundations'
down_revision: Union[str, Sequence[str], None] = '0013_user_credential_version'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('experiment_runs') as batch_op:
        batch_op.create_unique_constraint('uq_experiment_run_project', ['id', 'project_id'])
    with op.batch_alter_table('datasets') as batch_op:
        batch_op.create_unique_constraint('uq_dataset_project', ['id', 'project_id'])
    op.create_table('model_versions',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('project_id', sa.String(length=64), nullable=False),
    sa.Column('access_label', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('version_ref', sa.String(length=255), nullable=False),
    sa.Column('content_hash', sa.String(length=80), nullable=False),
    sa.Column('content', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'project_id', name='uq_model_version_project'),
    sa.UniqueConstraint('project_id', 'name', 'version_ref', name='uq_model_version_identity')
    )
    with op.batch_alter_table('model_versions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_model_versions_project_id'), ['project_id'], unique=False)

    op.create_table('service_principals',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('project_id', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('owner_user_id', sa.String(length=64), nullable=False),
    sa.Column('disabled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'project_id', name='uq_principal_project')
    )
    with op.batch_alter_table('service_principals', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_service_principals_project_id'), ['project_id'], unique=False)

    op.create_table('task_receipts',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('project_id', sa.String(length=64), nullable=False),
    sa.Column('actor_id', sa.String(length=64), nullable=False),
    sa.Column('method', sa.String(length=16), nullable=False),
    sa.Column('path', sa.String(length=512), nullable=False),
    sa.Column('key', sa.String(length=128), nullable=False),
    sa.Column('body_hash', sa.String(length=80), nullable=False),
    sa.Column('resource_ref', sa.String(length=128), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('project_id', 'actor_id', 'method', 'path', 'key', name='uq_task_receipt')
    )
    op.create_table('dataset_snapshots',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('project_id', sa.String(length=64), nullable=False),
    sa.Column('access_label', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('dataset_id', sa.String(length=64), nullable=False),
    sa.Column('content_hash', sa.String(length=80), nullable=False),
    sa.Column('item_count', sa.Integer(), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('created_by', sa.String(length=64), nullable=False),
    sa.ForeignKeyConstraint(['dataset_id', 'project_id'], ['datasets.id', 'datasets.project_id']),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'project_id', name='uq_snapshot_project')
    )
    with op.batch_alter_table('dataset_snapshots', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_dataset_snapshots_project_id'), ['project_id'], unique=False)

    op.create_table('prediction_sets',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('project_id', sa.String(length=64), nullable=False),
    sa.Column('access_label', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('snapshot_id', sa.String(length=64), nullable=False),
    sa.Column('model_version_id', sa.String(length=64), nullable=False),
    sa.Column('environment', sa.String(length=16), nullable=False),
    sa.Column('content_hash', sa.String(length=80), nullable=False),
    sa.Column('producer_manifest', sa.JSON(), nullable=False),
    sa.Column('provenance', sa.String(length=16), nullable=False),
    sa.CheckConstraint("environment IN ('dev','staging','prod')", name='ck_prediction_environment'),
    sa.ForeignKeyConstraint(['model_version_id', 'project_id'], ['model_versions.id', 'model_versions.project_id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.ForeignKeyConstraint(['snapshot_id', 'project_id'], ['dataset_snapshots.id', 'dataset_snapshots.project_id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'project_id', name='uq_prediction_project'),
    sa.UniqueConstraint('id', 'snapshot_id', name='uq_prediction_snapshot'),
    sa.UniqueConstraint('project_id', 'snapshot_id', 'model_version_id', 'content_hash', name='uq_prediction_content')
    )
    with op.batch_alter_table('prediction_sets', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_prediction_sets_project_id'), ['project_id'], unique=False)

    op.create_table('snapshot_items',
    sa.Column('snapshot_id', sa.String(length=64), nullable=False),
    sa.Column('sample_id', sa.String(length=255), nullable=False),
    sa.Column('content', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['snapshot_id'], ['dataset_snapshots.id'], ),
    sa.PrimaryKeyConstraint('snapshot_id', 'sample_id')
    )
    op.create_table('predictions',
    sa.Column('set_id', sa.String(length=64), nullable=False),
    sa.Column('sample_id', sa.String(length=255), nullable=False),
    sa.Column('snapshot_id', sa.String(length=64), nullable=False),
    sa.Column('content', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['set_id', 'snapshot_id'], ['prediction_sets.id', 'prediction_sets.snapshot_id'], ),
    sa.ForeignKeyConstraint(['snapshot_id', 'sample_id'], ['snapshot_items.snapshot_id', 'snapshot_items.sample_id'], ),
    sa.PrimaryKeyConstraint('set_id', 'sample_id')
    )
    op.create_table('task_evaluations',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('project_id', sa.String(length=64), nullable=False),
    sa.Column('access_label', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('prediction_set_id', sa.String(length=64), nullable=False),
    sa.Column('environment', sa.String(length=16), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('decision', sa.String(length=16), nullable=True),
    sa.Column('decision_reasons', sa.JSON(), nullable=False),
    sa.Column('result', sa.JSON(), nullable=False),
    sa.Column('created_by', sa.String(length=64), nullable=False),
    sa.CheckConstraint("decision IS NULL OR decision IN ('pass','fail','review','inconclusive')", name='ck_task_decision'),
    sa.CheckConstraint("status IN ('queued','running','succeeded','failed','cancelled','timed_out','uncertain')", name='ck_task_status'),
    sa.CheckConstraint("(status IN ('queued','running') AND decision IS NULL) OR (status NOT IN ('queued','running') AND decision IS NOT NULL)", name='ck_task_terminal_decision'),
    sa.ForeignKeyConstraint(['prediction_set_id', 'project_id'], ['prediction_sets.id', 'prediction_sets.project_id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'project_id', name='uq_task_evaluation_project')
    )
    with op.batch_alter_table('task_evaluations', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_task_evaluations_project_id'), ['project_id'], unique=False)

    op.create_table('experiment_run_evaluations',
    sa.Column('project_id', sa.String(length=64), nullable=False),
    sa.Column('run_id', sa.String(length=64), nullable=False),
    sa.Column('variant_name', sa.String(length=255), nullable=False),
    sa.Column('task_evaluation_id', sa.String(length=64), nullable=False),
    sa.ForeignKeyConstraint(['run_id', 'project_id'], ['experiment_runs.id', 'experiment_runs.project_id'], ),
    sa.ForeignKeyConstraint(['task_evaluation_id', 'project_id'], ['task_evaluations.id', 'task_evaluations.project_id'], ),
    sa.PrimaryKeyConstraint('run_id', 'variant_name')
    )
    op.create_table('metric_facts',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('task_evaluation_id', sa.String(length=64), nullable=False),
    sa.Column('definition_id', sa.String(length=128), nullable=False),
    sa.Column('definition_version', sa.String(length=32), nullable=False),
    sa.Column('scope', sa.String(length=32), nullable=False),
    sa.Column('scope_key', sa.Text(), nullable=False),
    sa.Column('content', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['task_evaluation_id'], ['task_evaluations.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('task_evaluation_id', 'definition_id', 'definition_version', 'scope', 'scope_key', name='uq_metric_definition_scope')
    )
    with op.batch_alter_table('api_keys', schema=None) as batch_op:
        batch_op.add_column(sa.Column('service_principal_id', sa.String(length=64), nullable=True))
        batch_op.create_foreign_key('fk_key_principal_project', 'service_principals', ['service_principal_id', 'project_id'], ['id', 'project_id'])

    with op.batch_alter_table('dataset_items', schema=None) as batch_op:
        batch_op.add_column(sa.Column('access_label', sa.JSON(), nullable=True))

    with op.batch_alter_table('datasets', schema=None) as batch_op:
        batch_op.add_column(sa.Column('task_type', sa.String(length=32), server_default='text', nullable=False))
        batch_op.add_column(sa.Column('task_schema', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('access_label', sa.JSON(), nullable=True))

    with op.batch_alter_table('experiment_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('kind', sa.String(length=32), server_default='legacy_synthetic', nullable=False))
        batch_op.add_column(sa.Column('decision', sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column('decision_reasons', sa.JSON(), server_default='[]', nullable=False))
        batch_op.create_check_constraint('ck_run_decision', "decision IS NULL OR decision IN ('pass','fail','review','inconclusive')")
        batch_op.create_check_constraint('ck_run_kind_decision', "(kind = 'legacy_synthetic' AND decision IS NULL) OR (kind = 'task_comparison' AND passed IS NULL AND (status = 'running' OR decision IS NOT NULL))")

    with op.batch_alter_table('experiments', schema=None) as batch_op:
        batch_op.add_column(sa.Column('kind', sa.String(length=32), server_default='legacy_synthetic', nullable=False))
        batch_op.add_column(sa.Column('snapshot_id', sa.String(length=64), nullable=True))
        batch_op.alter_column('rubric_id',
               existing_type=sa.VARCHAR(length=64),
               nullable=True)
        batch_op.create_foreign_key('fk_experiment_snapshot', 'dataset_snapshots', ['snapshot_id', 'project_id'], ['id', 'project_id'])
        batch_op.create_check_constraint('ck_experiment_kind', "(kind = 'legacy_synthetic' AND rubric_id IS NOT NULL) OR (kind = 'task_comparison' AND snapshot_id IS NOT NULL)")


    with op.batch_alter_table('experiment_runs') as batch_op:
        batch_op.alter_column('decision_reasons', existing_type=sa.JSON(), existing_nullable=False, server_default=None)

    guards = {'sqlite': ['CREATE TRIGGER immutable_model_versions BEFORE UPDATE OF '
                'id,project_id,created_at,name,version_ref,content_hash,content ON model_versions BEGIN SELECT '
                "RAISE(ABORT, 'immutable_task_resource'); END",
                'CREATE TRIGGER immutable_dataset_snapshots BEFORE UPDATE OF '
                'id,project_id,created_at,dataset_id,content_hash,item_count,content,created_by ON '
                "dataset_snapshots BEGIN SELECT RAISE(ABORT, 'immutable_task_resource'); END",
                'CREATE TRIGGER immutable_snapshot_items BEFORE UPDATE OF snapshot_id,sample_id,content ON '
                "snapshot_items BEGIN SELECT RAISE(ABORT, 'immutable_task_resource'); END",
                'CREATE TRIGGER immutable_prediction_sets BEFORE UPDATE OF '
                'id,project_id,created_at,snapshot_id,model_version_id,environment,content_hash,producer_manifest,provenance '
                "ON prediction_sets BEGIN SELECT RAISE(ABORT, 'immutable_task_resource'); END",
                'CREATE TRIGGER immutable_predictions BEFORE UPDATE OF set_id,sample_id,snapshot_id,content ON '
                "predictions BEGIN SELECT RAISE(ABORT, 'immutable_task_resource'); END",
                'CREATE TRIGGER immutable_task_evaluations BEFORE UPDATE OF '
                'id,project_id,created_at,prediction_set_id,environment,status,decision,decision_reasons,result,created_by '
                "ON task_evaluations WHEN (OLD.status NOT IN ('queued','running')) BEGIN SELECT RAISE(ABORT, "
                "'immutable_task_resource'); END",
                'CREATE TRIGGER immutable_experiment_runs BEFORE UPDATE OF '
                'id,project_id,experiment_id,kind,status,passed,decision,decision_reasons,by_variant,comparisons,criteria_failures,run_metadata,started_at,completed_at,created_at '
                "ON experiment_runs WHEN (OLD.kind = 'task_comparison' AND OLD.status IN ('completed','error')) "
                "BEGIN SELECT RAISE(ABORT, 'immutable_task_resource'); END",
                'CREATE TRIGGER immutable_metric_facts BEFORE UPDATE OF '
                'id,task_evaluation_id,definition_id,definition_version,scope,scope_key,content ON metric_facts '
                "BEGIN SELECT RAISE(ABORT, 'immutable_task_resource'); END"],
     'postgresql': ['CREATE OR REPLACE FUNCTION evalops_immutable_task_row() RETURNS trigger LANGUAGE plpgsql AS '
                    "$$ BEGIN RAISE EXCEPTION 'immutable_task_resource'; END; $$",
                    'CREATE TRIGGER immutable_model_versions BEFORE UPDATE OF '
                    'id,project_id,created_at,name,version_ref,content_hash,content ON model_versions FOR EACH '
                    'ROW EXECUTE FUNCTION evalops_immutable_task_row()',
                    'CREATE TRIGGER immutable_dataset_snapshots BEFORE UPDATE OF '
                    'id,project_id,created_at,dataset_id,content_hash,item_count,content,created_by ON '
                    'dataset_snapshots FOR EACH ROW EXECUTE FUNCTION evalops_immutable_task_row()',
                    'CREATE TRIGGER immutable_snapshot_items BEFORE UPDATE OF snapshot_id,sample_id,content ON '
                    'snapshot_items FOR EACH ROW EXECUTE FUNCTION evalops_immutable_task_row()',
                    'CREATE TRIGGER immutable_prediction_sets BEFORE UPDATE OF '
                    'id,project_id,created_at,snapshot_id,model_version_id,environment,content_hash,producer_manifest,provenance '
                    'ON prediction_sets FOR EACH ROW EXECUTE FUNCTION evalops_immutable_task_row()',
                    'CREATE TRIGGER immutable_predictions BEFORE UPDATE OF set_id,sample_id,snapshot_id,content '
                    'ON predictions FOR EACH ROW EXECUTE FUNCTION evalops_immutable_task_row()',
                    'CREATE TRIGGER immutable_task_evaluations BEFORE UPDATE OF '
                    'id,project_id,created_at,prediction_set_id,environment,status,decision,decision_reasons,result,created_by '
                    "ON task_evaluations FOR EACH ROW WHEN (OLD.status NOT IN ('queued','running')) EXECUTE "
                    'FUNCTION evalops_immutable_task_row()',
                    'CREATE TRIGGER immutable_experiment_runs BEFORE UPDATE OF '
                    'id,project_id,experiment_id,kind,status,passed,decision,decision_reasons,by_variant,comparisons,criteria_failures,run_metadata,started_at,completed_at,created_at '
                    "ON experiment_runs FOR EACH ROW WHEN (OLD.kind = 'task_comparison' AND OLD.status IN "
                    "('completed','error')) EXECUTE FUNCTION evalops_immutable_task_row()",
                    'CREATE TRIGGER immutable_metric_facts BEFORE UPDATE OF '
                    'id,task_evaluation_id,definition_id,definition_version,scope,scope_key,content ON '
                    'metric_facts FOR EACH ROW EXECUTE FUNCTION evalops_immutable_task_row()']}
    for statement in guards.get(op.get_bind().dialect.name, []):
        op.execute(statement)


def downgrade() -> None:
    # Never erase task evidence or turn principal credentials into unrestricted legacy keys.
    bind = op.get_bind()
    for table in ('task_receipts', 'experiment_run_evaluations', 'metric_facts', 'task_evaluations', 'predictions', 'prediction_sets', 'snapshot_items', 'dataset_snapshots', 'model_versions', 'service_principals'):
        if bind.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar():
            raise RuntimeError("task_foundations_downgrade_requires_empty_task_tables")
    for table in ('experiments', 'experiment_runs'):
        if bind.execute(sa.text(f"SELECT COUNT(*) FROM {table} WHERE kind = 'task_comparison'")).scalar():
            raise RuntimeError("task_foundations_downgrade_requires_empty_task_tables")
    op.execute("DROP TRIGGER IF EXISTS immutable_experiment_runs" + (" ON experiment_runs" if op.get_bind().dialect.name == "postgresql" else ""))
    with op.batch_alter_table('experiments', schema=None) as batch_op:
        batch_op.drop_constraint('ck_experiment_kind', type_='check')
        batch_op.drop_constraint('fk_experiment_snapshot', type_='foreignkey')
        batch_op.alter_column('rubric_id',
               existing_type=sa.VARCHAR(length=64),
               nullable=False)
        batch_op.drop_column('snapshot_id')
        batch_op.drop_column('kind')

    with op.batch_alter_table('experiment_runs', schema=None) as batch_op:
        batch_op.drop_constraint('ck_run_kind_decision', type_='check')
        batch_op.drop_constraint('ck_run_decision', type_='check')
        batch_op.drop_column('decision_reasons')
        batch_op.drop_column('decision')
        batch_op.drop_column('kind')

    with op.batch_alter_table('datasets', schema=None) as batch_op:
        batch_op.drop_column('access_label')
        batch_op.drop_column('task_schema')
        batch_op.drop_column('task_type')

    with op.batch_alter_table('dataset_items', schema=None) as batch_op:
        batch_op.drop_column('access_label')

    with op.batch_alter_table('api_keys', schema=None) as batch_op:
        batch_op.drop_constraint('fk_key_principal_project', type_='foreignkey')
        batch_op.drop_column('service_principal_id')

    op.drop_table('metric_facts')
    op.drop_table('experiment_run_evaluations')
    with op.batch_alter_table('experiment_runs') as batch_op:
        batch_op.drop_constraint('uq_experiment_run_project', type_='unique')
    with op.batch_alter_table('task_evaluations', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_task_evaluations_project_id'))

    op.drop_table('task_evaluations')
    op.drop_table('predictions')
    op.drop_table('snapshot_items')
    with op.batch_alter_table('prediction_sets', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_prediction_sets_project_id'))

    op.drop_table('prediction_sets')
    with op.batch_alter_table('dataset_snapshots', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_dataset_snapshots_project_id'))

    op.drop_table('dataset_snapshots')
    with op.batch_alter_table('datasets') as batch_op:
        batch_op.drop_constraint('uq_dataset_project', type_='unique')
    op.drop_table('task_receipts')
    with op.batch_alter_table('service_principals', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_service_principals_project_id'))

    op.drop_table('service_principals')
    with op.batch_alter_table('model_versions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_model_versions_project_id'))

    op.drop_table('model_versions')
    if op.get_bind().dialect.name == 'postgresql':
        op.execute('DROP FUNCTION IF EXISTS evalops_immutable_task_row()')
