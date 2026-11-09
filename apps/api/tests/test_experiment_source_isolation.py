"""Source enrichment must not cross projects or revive hidden traces."""
from datetime import datetime, timezone

import pytest

from app.db import SessionLocal
from app.domain.services.experiment_service import _build_variant_context, execute_experiment
from app.models import Dataset, DatasetItem, Experiment, Rubric, Span, Trace


@pytest.mark.parametrize("source_project,hidden", [("own", False), ("foreign", False), ("own", True)])
def test_source_enrichment_requires_active_trace_in_dataset_project(source_project, hidden):
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        dataset = Dataset(id="dataset", project_id="own", slug="cases")
        item = DatasetItem(id="item", dataset_id="dataset", input={"text": "dataset copy"},
                           expected_output={"text": "copied answer"}, metadata_json={"source_trace_id": "source"})
        trace = Trace(id="source", project_id=source_project, organization_id=source_project,
                      name="original", environment="prod", status="ok", started_at=now,
                      ended_at=now, duration_ms=1, metadata_json={"private": "source-only"},
                      deleted_at=now if hidden else None)
        span = Span(id="span", trace_id="source", type="tool", name="private-tool", status="ok",
                    started_at=now, ended_at=now, duration_ms=1, output={"secret": "span-only"})
        db.add_all([dataset, item, trace, span])
        db.commit()
        context = _build_variant_context(item, {"name": "baseline"}, "synthetic answer", db)
        if source_project == "own" and not hidden:
            assert context["trace"]["id"] == "source"
            assert context["trace"]["metadata"]["private"] == "source-only"
            assert len(context["trace"]["spans"]) == 1
        else:
            assert "id" not in context["trace"]
            assert "spans" not in context["trace"]
            assert "source-only" not in str(context)
            assert "span-only" not in str(context)
        assert context["trace"]["input"]["text"] == "dataset copy"
        assert context["trace"]["output"]["text"] == "synthetic answer"
        assert context["dataset_item"]["expected_output"] == {"text": "copied answer"}
        db.refresh(item)
        assert item.input == {"text": "dataset copy"}
        assert item.metadata_json == {"source_trace_id": "source"}


def test_experiment_cannot_enrich_from_another_projects_dataset():
    with SessionLocal() as db:
        db.add_all([Dataset(id="dataset", project_id="foreign", slug="cases"),
                    Rubric(id="rubric", project_id="own", slug="check")])
        db.commit()
        experiment = Experiment(id="experiment", project_id="own", name="comparison",
                                dataset_id="dataset", rubric_id="rubric", variants=[])
        with pytest.raises(ValueError, match="dataset_project_mismatch"):
            execute_experiment(experiment, db)
