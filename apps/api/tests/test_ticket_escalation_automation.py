from sqlalchemy.dialects import postgresql

from app.models_ai import Department
from app.ticket_escalation_automation import TicketAutoEscalationClaim, _department_for_category


class QueryCapture:
    def __init__(self):
        self.statement = None

    def scalar(self, statement):
        self.statement = statement
        return None


def test_category_department_lookup_is_active_and_tenant_scoped():
    db = QueryCapture()

    assert _department_for_category(db, "tenant-a", "billing") is None

    sql = str(db.statement.compile(dialect=postgresql.dialect())).lower()
    assert "departments.tenant_id" in sql
    assert "departments.is_active" in sql
    assert "departments.name ilike" in sql
    assert "tenant-a" not in sql  # value remains a bound parameter, not SQL text


def test_auto_escalation_claim_has_tenant_ticket_unique_constraint():
    constraints = [
        constraint for constraint in TicketAutoEscalationClaim.__table__.constraints
        if getattr(constraint, "name", None) == "uq_ticket_auto_escalation_tenant_ticket"
    ]

    assert len(constraints) == 1
    assert {column.name for column in constraints[0].columns} == {"tenant_id", "ticket_id"}


def test_escalation_claim_table_is_registered_for_schema_creation():
    assert TicketAutoEscalationClaim.__tablename__ == "ticket_auto_escalation_claims"
    assert Department.__tablename__ == "departments"
