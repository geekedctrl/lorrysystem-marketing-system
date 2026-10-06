"""Initialize the known DEV connection once; preserve administrator changes."""
import json
import os
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.session import ControlSession, SessionLocal
from app.models.discovery_runs import DiscoveryAutomation
from app.models.workspaces import Workspace
from app.routers.discovery_runs import AutomationConfig


def main():
    filename = os.getenv('DISCOVERY_BOOTSTRAP_FILE')
    if not filename:
        if os.getenv('APP_ENV', 'development') != 'development':
            return
        filename = 'discovery.dev.json'
    path = Path(filename)
    if not path.is_file():
        return
    values = json.loads(path.read_text(encoding='utf-8'))
    workspace_id = UUID(values.pop('workspace_id'))
    config = AutomationConfig(**values)
    with ControlSession() as control:
        workspace = control.get(Workspace, workspace_id)
        if not workspace or not workspace.active:
            return
    with SessionLocal(info={'workspace_id': workspace_id}) as db:
        if db.scalar(select(DiscoveryAutomation)) is not None:
            return
        db.add(DiscoveryAutomation(**config.model_dump()))
        try:
            db.commit()
        except IntegrityError:
            # Another starting API replica may have initialized the same row.
            db.rollback()
            return
    print('Initialized the DEV workspace discovery connection.')


if __name__ == '__main__':
    main()
