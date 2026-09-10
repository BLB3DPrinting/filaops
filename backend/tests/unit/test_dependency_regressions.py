"""Regression coverage for the Alembic and Pydantic patch upgrades."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from pydantic import BaseModel, ValidationError
from sqlalchemy import CheckConstraint, Column, Integer, MetaData, Table, create_engine

from app.schemas.scheduling import CapacityCheckRequest


def _check_constraint_diffs(plugin_names: Sequence[str] | None = None) -> list[Any]:
    """Compare identical tables whose target adds one named check constraint."""
    engine = create_engine("sqlite://")

    database_metadata = MetaData()
    Table(
        "widgets",
        database_metadata,
        Column("quantity", Integer, nullable=False),
    )
    database_metadata.create_all(engine)

    target_metadata = MetaData()
    Table(
        "widgets",
        target_metadata,
        Column("quantity", Integer, nullable=False),
        CheckConstraint("quantity >= 0", name="ck_widgets_quantity"),
    )

    options: dict[str, Any] = {"target_metadata": target_metadata}
    if plugin_names is not None:
        options["autogenerate_plugins"] = list(plugin_names)

    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts=options)
        return compare_metadata(context, target_metadata)


def test_alembic_does_not_autogenerate_check_constraints_by_default() -> None:
    """FilaOps uses Alembic's defaults, which must avoid false-positive checks."""
    assert _check_constraint_diffs() == []


@pytest.mark.parametrize(
    "plugin_name",
    [
        "alembic.ext.checkconstraint_byname",
        "alembic.autogenerate.checkconstraint_byname",
    ],
)
def test_alembic_check_constraint_plugin_remains_available_by_explicit_name(
    plugin_name: str,
) -> None:
    """Both the 1.19.2 name and its compatibility alias must opt in cleanly."""
    diffs = _check_constraint_diffs(
        ["alembic.autogenerate.*", plugin_name]
    )

    assert len(diffs) == 1
    operation, constraint = diffs[0]
    assert operation == "add_constraint"
    assert constraint.name == "ck_widgets_quantity"
    assert str(constraint.sqltext) == "quantity >= 0"


class _ValidationRecorder:
    def __init__(self, events: list[Any]) -> None:
        self.events = events

    def on_enter(self, input: Any, **kwargs: Any) -> None:
        self.events.append(input)


class _PydanticPlugin:
    def __init__(self, events: list[Any]) -> None:
        self.events = events

    def new_schema_validator(self, *args: Any, **kwargs: Any) -> tuple[Any, None, None]:
        return _ValidationRecorder(self.events), None, None


@pytest.fixture
def plugin_aware_scheduling_models(monkeypatch: pytest.MonkeyPatch):
    """Build nested FilaOps models while a synthetic Pydantic plugin is active."""
    from pydantic.plugin import _loader

    events: list[Any] = []
    monkeypatch.setattr(_loader, "_plugins", {"filaops-test": _PydanticPlugin(events)})

    class PluginAwareCapacityCheck(CapacityCheckRequest):
        pass

    class SchedulingEnvelope(BaseModel):
        request: PluginAwareCapacityCheck

    return SchedulingEnvelope, PluginAwareCapacityCheck, events


def test_pydantic_reuses_wrapped_validator_for_nested_filaops_model(
    plugin_aware_scheduling_models,
) -> None:
    """A plugin wrapper must not disable reuse of a nested model validator."""
    envelope_model, request_model, events = plugin_aware_scheduling_models
    request_data = {
        "resource_id": "42",
        "start_time": "2026-09-10T08:00:00Z",
        "end_time": "2026-09-10T09:30:00Z",
    }
    payload = {"request": request_data}

    envelope = envelope_model.model_validate(payload)

    assert envelope.request.resource_id == 42
    assert envelope.request.start_time.isoformat() == "2026-09-10T08:00:00+00:00"
    assert envelope.request.is_printer is False
    underlying_validator = (
        envelope_model.__pydantic_validator__.__pydantic_schema_validator__
    )
    assert "PrebuiltValidator" in repr(underlying_validator)
    assert events == [payload]

    events.clear()
    request_model.model_validate(request_data)
    assert events == [request_data]


def test_pydantic_nested_validation_errors_keep_the_full_field_path(
    plugin_aware_scheduling_models,
) -> None:
    """The reused validator must still report invalid nested application data."""
    envelope_model, _, events = plugin_aware_scheduling_models
    payload = {
        "request": {
            "resource_id": "not-an-integer",
            "start_time": "2026-09-10T08:00:00Z",
            "end_time": "2026-09-10T09:30:00Z",
        }
    }

    with pytest.raises(ValidationError) as exc_info:
        envelope_model.model_validate(payload)

    error = exc_info.value.errors()[0]
    assert error["loc"] == ("request", "resource_id")
    assert error["type"] == "int_parsing"
    assert events == [payload]
