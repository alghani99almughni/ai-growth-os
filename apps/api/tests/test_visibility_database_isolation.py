"""Regression tests proving visibility data is isolated from the platform database."""
from sqlalchemy import create_engine, inspect

import app.main  # noqa: F401 - register platform routes/dependencies first
from app.db import Base as PlatformBase
from app.visibility_db import VisibilityBase
from app import models_visibility  # noqa: F401 - register visibility tables


def test_visibility_tables_use_separate_metadata_from_platform_database():
    visibility_tables = set(VisibilityBase.metadata.tables)
    platform_tables = set(PlatformBase.metadata.tables)

    assert {
        "visibility_brands",
        "visibility_competitors",
        "visibility_queries",
        "visibility_check_runs",
        "visibility_observations",
        "visibility_audits",
        "visibility_audit_findings",
    }.issubset(visibility_tables)
    assert visibility_tables.isdisjoint(platform_tables)


def test_visibility_tenant_ids_are_opaque_and_have_no_cross_database_foreign_keys():
    for table in VisibilityBase.metadata.tables.values():
        if "tenant_id" in table.c:
            assert not list(table.c.tenant_id.foreign_keys)
        for column in table.columns:
            for foreign_key in column.foreign_keys:
                target_table = foreign_key.target_fullname.split(".", 1)[0]
                assert target_table in VisibilityBase.metadata.tables


def test_visibility_schema_can_be_created_without_platform_tables():
    engine = create_engine("sqlite://")
    try:
        VisibilityBase.metadata.create_all(bind=engine)
        names = set(inspect(engine).get_table_names())
        assert "visibility_brands" in names
        assert "visibility_queries" in names
        assert "visibility_audits" in names
        assert "tenants" not in names
        assert "users" not in names
    finally:
        engine.dispose()
