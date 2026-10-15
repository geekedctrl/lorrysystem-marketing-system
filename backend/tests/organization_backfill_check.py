"""Disposable database migration/backfill check; never run against an application DB."""
import os
import uuid
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text


def main():
    url = os.environ["DATABASE_URL"]
    if not url.endswith("/marketing_org_backfill_test"):
        raise RuntimeError("Use the dedicated marketing_org_backfill_test database")
    config = Config("alembic.ini")
    command.upgrade(config, "011_executor_ownership_cleanup")
    engine = create_engine(url)
    uid, wid = uuid.uuid4(), uuid.uuid4()
    with engine.begin() as db:
        db.execute(text("INSERT INTO users(id,email,password_hash,active,platform_admin) VALUES (:id,'backfill@example.test','synthetic',true,true)"), {"id": uid})
        db.execute(text("INSERT INTO workspaces(id,name,active,automation_enabled) VALUES (:id,'Legacy fixture',true,false)"), {"id": wid})
        db.execute(text("INSERT INTO memberships(workspace_id,user_id,role) VALUES (:wid,:uid,'ADMIN')"), {"wid": wid, "uid": uid})
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    with engine.connect() as db:
        row = db.execute(text("""SELECT w.organization_id,o.name,om.role,m.role
          FROM workspaces w JOIN organizations o ON o.id=w.organization_id
          JOIN organization_memberships om ON om.organization_id=o.id AND om.user_id=:uid
          JOIN memberships m ON m.workspace_id=w.id AND m.user_id=:uid WHERE w.id=:wid"""),
                         {"uid": uid, "wid": wid}).one()
        assert row == (wid, "Legacy fixture", "OWNER", "ADMIN"), row
        assert db.scalar(text("SELECT count(*) FROM organizations")) == 1
    print("Organization backfill and repeat upgrade passed")


if __name__ == "__main__":
    main()
