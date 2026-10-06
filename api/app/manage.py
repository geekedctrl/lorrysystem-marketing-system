"""Run inside the API container; passwords are read without command-line exposure."""
import argparse
import getpass
import sys

from sqlalchemy import delete, select, text

from app.auth import password_hash
from app.db.session import ControlSession
from app.models.workspaces import AccessAudit, LoginSession, Membership, User
from app.routers.workspaces import normalize_email
from app.workspace_context import LORRYSYSTEM_WORKSPACE_ID


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['bootstrap-admin', 'reset-password'])
    parser.add_argument('--email', required=True)
    parser.add_argument('--password-stdin', action='store_true')
    args = parser.parse_args()
    account_email = normalize_email(args.email)
    password = sys.stdin.readline().rstrip('\r\n') if args.password_stdin else getpass.getpass('Password (12+ characters): ')
    encoded = password_hash(password)
    with ControlSession() as db:
        db.execute(text('LOCK TABLE users IN EXCLUSIVE MODE'))
        user = db.scalar(select(User).where(User.email == account_email))
        if args.command == 'bootstrap-admin':
            if db.scalar(select(User.id).limit(1)):
                raise SystemExit('An account already exists. Bootstrap is only for the first administrator.')
            user = User(email=account_email, password_hash=encoded, platform_admin=True)
            db.add(user)
            db.flush()
            db.add(Membership(workspace_id=LORRYSYSTEM_WORKSPACE_ID, user_id=user.id, role='ADMIN'))
        else:
            if user is None:
                raise SystemExit('Account not found.')
            user.password_hash = encoded
            db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
        db.add(AccessAudit(actor='server-administrator', action=args.command, detail={'email': account_email}))
        db.commit()
    print('Account updated successfully. No password was logged.')


if __name__ == '__main__':
    main()
