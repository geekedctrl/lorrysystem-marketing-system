import argparse, getpass
from sqlalchemy import select
from .db import Session
from .models import User, Workspace, Membership
from .auth import hash_password


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["bootstrap", "add-member", "migration"])
    parser.add_argument("migration_mode", nargs="?", choices=["export", "dry-run", "apply", "reconcile", "final-delta"])
    parser.add_argument("--email")
    parser.add_argument("--workspace", default="LorrySystem")
    parser.add_argument(
        "--role",
        choices=["ADMIN", "OPERATOR", "REVIEWER", "VIEWER"],
        default="OPERATOR",
    )
    args = parser.parse_args()
    if args.command == "migration":
        from .migration_cli import main as migration_main
        raise SystemExit(migration_main([args.migration_mode] if args.migration_mode else []))
    if not args.email:
        raise SystemExit("--email is required for account commands")
    email = args.email.strip().lower()
    if "@" not in email or len(email) > 254:
        raise SystemExit("Invalid email")
    with Session() as db:
        actor = db.scalar(select(User).where(User.email == email))
        if args.command == "bootstrap" and db.scalar(select(User.id).limit(1)):
            raise SystemExit("Bootstrap only works on an empty database")
        if not actor:
            password = getpass.getpass("Password (at least12 characters): ")
            if len(password) < 12 or len(password) > 256:
                raise SystemExit("Password must be12–256 characters")
            actor = User(
                email=email,
                password_hash=hash_password(password),
                platform_admin=args.command == "bootstrap",
            )
            db.add(actor)
            db.flush()
        workspace = db.scalar(select(Workspace).where(Workspace.name == args.workspace))
        if not workspace and args.command == "bootstrap":
            workspace = Workspace(name=args.workspace)
            db.add(workspace)
            db.flush()
        if not workspace:
            raise SystemExit("Workspace not found")
        member = db.get(Membership, (workspace.id, actor.id))
        if member:
            raise SystemExit("Membership already exists; no role changed")
        db.add(
            Membership(
                workspace_id=workspace.id,
                user_id=actor.id,
                role="ADMIN" if args.command == "bootstrap" else args.role,
            )
        )
        db.commit()
        print("Account and workspace access configured")


if __name__ == "__main__":
    main()
