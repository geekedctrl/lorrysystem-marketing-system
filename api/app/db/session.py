from sqlalchemy import URL, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from fastapi import HTTPException

from app.core.config import settings


DATABASE_URL = URL.create(
    drivername="postgresql+psycopg",
    username=settings.postgres_user,
    password=settings.postgres_password,
    host=settings.postgres_host,
    port=settings.postgres_port,
    database=settings.postgres_db,
)


engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)


class WorkspaceSession(Session):
    """Business sessions always run as a restricted role under database RLS."""


@event.listens_for(WorkspaceSession, 'after_begin')
def set_workspace(session, transaction, connection):
    workspace_id = session.info.get('workspace_id')
    if not workspace_id:
        raise RuntimeError('Business database access requires a workspace')
    connection.execute(text('SET LOCAL ROLE marketing_workspace_runtime'))
    connection.execute(text("SELECT set_config('app.workspace_id', :workspace, true)"),
                       {'workspace': str(workspace_id)})


@event.listens_for(WorkspaceSession, 'before_flush')
def assign_workspace(session, flush_context, instances):
    from app.models.workspaces import WorkspaceOwned
    workspace_id = session.info['workspace_id']
    for record in session.new | session.dirty | session.deleted:
        if isinstance(record, WorkspaceOwned):
            if record.workspace_id is None and record in session.new:
                record.workspace_id = workspace_id
            if record.workspace_id != workspace_id:
                raise ValueError('Record belongs to a different workspace')
            principal = session.info.get('principal')
            if principal:
                for name in ('created_by', 'closed_by', 'reviewed_by', 'decided_by'):
                    if hasattr(record, name) and getattr(record, name) is not None:
                        setattr(record, name, principal.actor)
                from app.models.marketing import Event
                if isinstance(record, Event):
                    record.actor_id = principal.actor
                    record.actor_type = 'USER' if principal.user_id else 'SERVICE'
                    record.metadata_json = dict(record.metadata_json or {})
                    for name in ('created_by', 'closed_by', 'reviewed_by', 'decided_by'):
                        if name in record.metadata_json:
                            record.metadata_json[name] = principal.actor


ControlSession = sessionmaker(bind=engine, autoflush=False)

SessionLocal = sessionmaker(
    bind=engine,
    class_=WorkspaceSession,
    autoflush=False,
    autocommit=False,
)


def get_db():
    from app.workspace_context import current_principal
    principal = current_principal.get()
    if principal is None:
        raise HTTPException(401, 'Authentication required')
    db = SessionLocal(info={'workspace_id': principal.workspace_id, 'principal': principal})

    try:
        yield db
    finally:
        db.close()
