"""
seed_dev.py — bootstrap local dev environment.

Creates a user, org, project, and writes apps/web/.env.local with a
long-lived token so the Next.js dashboard can talk to the API.

Usage (from apps/api with venv active):
    python scripts/seed_dev.py
"""

import sys
import os
import pathlib
from datetime import datetime, timedelta, timezone

sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import jwt
from app.db import SessionLocal, Base, engine
from app.models import User, Organization, Membership, Project
from app.security import JWT_SECRET, JWT_ALGORITHM, new_id, hash_api_key, generate_api_key
from app.models import ApiKey

EMAIL = "dev@evalops.local"
NAME  = "Dev User"
ORG_SLUG    = "my-org"
PROJECT_SLUG = "my-project"

TOKEN_DAYS  = 365  # long-lived for dev


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # ── user ─────────────────────────────────────────────────────────
        user = db.query(User).filter(User.email == EMAIL).first()
        if not user:
            user = User(
                id=new_id("usr"),
                email=EMAIL,
                name=NAME,
            )
            db.add(user)
            db.flush()
            print(f"✓ user created: {user.id}")
        else:
            print(f"  user already exists: {user.id}")

        # ── org ──────────────────────────────────────────────────────────
        org = db.query(Organization).filter(Organization.slug == ORG_SLUG).first()
        if not org:
            org = Organization(id=new_id("org"), name="My Org", slug=ORG_SLUG)
            db.add(org)
            db.flush()
            db.add(Membership(user_id=user.id, organization_id=org.id, role="owner"))
            print(f"✓ org created: {org.id}  slug={ORG_SLUG}")
        else:
            print(f"  org already exists: {org.id}  slug={ORG_SLUG}")

        # ── project ───────────────────────────────────────────────────────
        proj = (
            db.query(Project)
            .filter(Project.organization_id == org.id, Project.slug == PROJECT_SLUG)
            .first()
        )
        if not proj:
            proj = Project(
                id=new_id("prj"),
                organization_id=org.id,
                name="My Project",
                slug=PROJECT_SLUG,
            )
            db.add(proj)
            db.flush()
            print(f"✓ project created: {proj.id}  slug={PROJECT_SLUG}")
        else:
            print(f"  project already exists: {proj.id}  slug={PROJECT_SLUG}")

        # ── api key (for SDK ingestion) ────────────────────────────────────
        existing_key = (
            db.query(ApiKey)
            .filter(ApiKey.project_id == proj.id, ApiKey.revoked_at.is_(None))
            .first()
        )
        if not existing_key:
            raw_key, prefix = generate_api_key("dev")
            api_key = ApiKey(
                id=new_id("key"),
                project_id=proj.id,
                prefix=prefix,
                hash=hash_api_key(raw_key),
                name="Dev key",
                environment="dev",
                scopes="ingest,read",
                rate_limit_per_minute=120,
            )
            db.add(api_key)
            print(f"✓ API key created: {raw_key}")
            sdk_key = raw_key
        else:
            print(f"  API key already exists (prefix {existing_key.prefix}…)")
            sdk_key = f"<existing key with prefix {existing_key.prefix}>"

        db.commit()

        # ── long-lived JWT for dashboard ──────────────────────────────────
        now = datetime.now(timezone.utc)
        payload = {
            "sub":   user.id,
            "email": user.email,
            "name":  user.name,
            "iat":   int(now.timestamp()),
            "exp":   int((now + timedelta(days=TOKEN_DAYS)).timestamp()),
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

        # ── write .env.local ──────────────────────────────────────────────
        env_path = pathlib.Path(__file__).parent.parent.parent.parent / "apps" / "web" / ".env.local"
        env_path.write_text(
            f"EVALOPS_API_BASE_URL=http://localhost:8000/v1\n"
            f"EVALOPS_DASHBOARD_BEARER_TOKEN={token}\n",
            encoding="utf-8",
        )

        print()
        print("=" * 60)
        print(f"✓ .env.local written to: {env_path}")
        print()
        print(f"  Dashboard URL:  http://localhost:3000/o/{ORG_SLUG}/p/{PROJECT_SLUG}")
        print(f"  SDK API key:    {sdk_key}")
        print(f"  Token expires:  {TOKEN_DAYS} days from now")
        print("=" * 60)

    finally:
        db.close()


if __name__ == "__main__":
    main()
