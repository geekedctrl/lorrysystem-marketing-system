from app.models.workspaces import Workspace, User, Membership, LoginSession, Invitation, ServiceCredential, AccessAudit, LoginAttempt
from app.models.discovery_runs import DiscoveryAutomation, DiscoveryRun
from app.models.catalog import ICPProfile, Product
from app.models.companies import Company, Contact
from app.models.discovery import (
    LeadCandidate,
    LeadCandidateSource,
)
from app.models.leads import (
    Lead,
    LeadResearch,
    LeadScore,
    ProductMatch,
    ResearchSource,
)
from app.models.marketing import (
    ApprovalRequest,
    Event,
    MarketingAction,
)


__all__ = [
    "Product",
    "ICPProfile",
    "Company",
    "Contact",
    "LeadCandidate",
    "LeadCandidateSource",
    "Lead",
    "LeadResearch",
    "ResearchSource",
    "LeadScore",
    "ProductMatch",
    "MarketingAction",
    "ApprovalRequest",
    "Event",
]

# Keep the ORM schema aligned with migration 009. Both a record's owner and
# every relationship are checked by the database, independently of API code.
from sqlalchemy import ForeignKeyConstraint, UniqueConstraint

_business_tables = {globals()[name].__table__ for name in __all__}
for _table in _business_tables:
    _table.append_constraint(UniqueConstraint('workspace_id', 'id', name=f'uq_{_table.name}_workspace_id_id'))
    for _foreign_key in list(_table.foreign_key_constraints):
        _columns = list(_foreign_key.columns)
        if len(_columns) == 1 and _foreign_key.referred_table in _business_tables:
            _column = _columns[0].name
            _parent = _foreign_key.referred_table.name
            _target = _foreign_key.elements[0].column.name
            _table.append_constraint(ForeignKeyConstraint(
                ['workspace_id', _column], [f'{_parent}.workspace_id', f'{_parent}.{_target}'],
                name=f'fk_{_table.name}_{_column}_workspace', deferrable=True, initially='DEFERRED',
            ))
