"""Tests for Cron Job REST API models and endpoint wiring."""

import pytest
from pydantic import ValidationError

from backend.web.models.panel import CreateCronJobRequest, UpdateCronJobRequest

# ── CreateCronJobRequest ──


class TestCreateCronJobRequest:
    def test_minimal_fields(self):
        req = CreateCronJobRequest(name="nightly-backup", cron_expression="0 2 * * *")
        assert req.name == "nightly-backup"
        assert req.cron_expression == "0 2 * * *"

    def test_defaults(self):
        req = CreateCronJobRequest(name="job", cron_expression="* * * * *")
        assert req.description == ""
        assert req.task_template == "{}"
        assert req.enabled is True

    def test_all_fields(self):
        req = CreateCronJobRequest(
            name="weekly-report",
            description="Generate weekly summary",
            cron_expression="0 9 * * 1",
            task_template='{"title": "Weekly Report"}',
            enabled=False,
        )
        assert req.name == "weekly-report"
        assert req.description == "Generate weekly summary"
        assert req.cron_expression == "0 9 * * 1"
        assert req.task_template == '{"title": "Weekly Report"}'
        assert req.enabled is False

    def test_missing_name_raises(self):
        with pytest.raises(ValidationError):
            CreateCronJobRequest(cron_expression="* * * * *")

    def test_missing_cron_expression_raises(self):
        with pytest.raises(ValidationError):
            CreateCronJobRequest(name="job")


# ── UpdateCronJobRequest ──


class TestUpdateCronJobRequest:
    def test_all_none_by_default(self):
        req = UpdateCronJobRequest()
        assert req.name is None
        assert req.description is None
        assert req.cron_expression is None
        assert req.task_template is None
        assert req.enabled is None

    def test_partial_update_name_only(self):
        req = UpdateCronJobRequest(name="renamed")
        assert req.name == "renamed"
        assert req.cron_expression is None

    def test_partial_update_enabled_only(self):
        req = UpdateCronJobRequest(enabled=False)
        assert req.enabled is False
        assert req.name is None

    def test_model_dump_exclude_none(self):
        req = UpdateCronJobRequest(name="new-name", enabled=True)
        fields = req.model_dump(exclude_none=True)
        assert fields == {"name": "new-name", "enabled": True}
        assert "description" not in fields
        assert "cron_expression" not in fields
        assert "task_template" not in fields

    def test_enabled_bool_to_int_conversion(self):
        """Verify the pattern used in the router: bool -> int for SQLite."""
        req = UpdateCronJobRequest(enabled=True)
        fields = req.model_dump(exclude_none=True)
        if "enabled" in fields:
            fields["enabled"] = int(fields["enabled"])
        assert fields["enabled"] == 1

        req2 = UpdateCronJobRequest(enabled=False)
        fields2 = req2.model_dump(exclude_none=True)
        if "enabled" in fields2:
            fields2["enabled"] = int(fields2["enabled"])
        assert fields2["enabled"] == 0
