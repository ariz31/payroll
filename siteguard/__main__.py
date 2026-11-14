import argparse
import getpass
import os
import re
from uuid import uuid4

from .db import control, migrate, transaction
from .security import LOGIN_PATTERN, hash_password, validate_code


def main():
    parser = argparse.ArgumentParser(prog="python -m siteguard")
    commands = parser.add_subparsers(required=True, dest="command")
    migrate_parser = commands.add_parser("migrate", help="Apply PostgreSQL schema migrations")
    migrate_parser.add_argument("--runtime-role", default=os.getenv("SITEGUARD_RUNTIME_ROLE"))
    commands.add_parser("purge-expired-images", help="Remove expired image bytes and stale authentication records")
    bootstrap = commands.add_parser("bootstrap", help="Create an organization and its initial administrator")
    bootstrap.add_argument("--organization", required=True)
    bootstrap.add_argument("--name", required=True)
    bootstrap.add_argument("--login", required=True)
    args = parser.parse_args()
    if args.command == "purge-expired-images":
        from .maintenance import cleanup

        deleted = cleanup()
        print(f"Removed {deleted['scan_images']} scan images and {deleted['badge_images']} badge images.")
        return
    dsn = os.getenv("MIGRATION_DATABASE_URL")
    if not dsn:
        parser.error("MIGRATION_DATABASE_URL must be set")
    if args.command == "migrate":
        migrate(dsn, args.runtime_role)
        print("Migrations applied.")
        return
    slug = args.organization.lower()
    if not validate_code(slug):
        parser.error("Organization must be a valid code")
    if not re.fullmatch(LOGIN_PATTERN, args.login):
        parser.error("Initial login must be a username or email address")
    if not args.name.strip() or len(args.name.strip()) > 120:
        parser.error("Organization name must contain 1 to 120 characters")
    password = getpass.getpass("Initial administrator password: ")
    if not 12 <= len(password) <= 256:
        parser.error("Password must contain 12 to 256 characters")
    org_id, admin_id = uuid4(), uuid4()
    with transaction(dsn) as db:
        created = db.execute(
            "INSERT INTO organizations (id,slug,name) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING RETURNING id",
            (org_id, slug, args.name),
        ).fetchone()
        if not created:
            parser.error("Organization already exists")
        db.execute(
            """INSERT INTO staff (id,org_id,login,name,role,password_hash)
            VALUES (%s,%s,%s,%s,'admin',%s)""",
            (admin_id, org_id, args.login.lower(), args.name, hash_password(password)),
        )
        control(db, org_id, admin_id, "organization.created", slug)
    print(f"Organization {slug} created.")


if __name__ == "__main__":
    main()
