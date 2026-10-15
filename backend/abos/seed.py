"""Development seed: one CEO account with a workspace. `python -m abos.seed` (refuses to run in production)."""

import sys

from sqlalchemy import select

from abos import models  # noqa: F401  (registers all ORM models)
from abos.core.config import get_settings
from abos.core.db import SessionLocal
from abos.identity import service
from abos.identity.deps import ClientMeta
from abos.identity.models import User
from abos.identity.schemas import RegisterIn

DEV_EMAIL = "ceo@abos-dev.example.com"


def main() -> int:
    s = get_settings()
    if s.env == "production":
        print("refusing to seed a production database", file=sys.stderr)
        return 1
    with SessionLocal() as db:
        if db.scalar(select(User.id).where(User.email == DEV_EMAIL)):
            print(f"already seeded: {DEV_EMAIL}")
            return 0
        service.register(db, RegisterIn(email=DEV_EMAIL, password=s.seed_password, full_name="Dana Reyes",
                                        organization_name="Northwind Supplies", job_title="CEO"),
                         ClientMeta(ip=None, user_agent="seed"))
    print(f"seeded {DEV_EMAIL} (password from ABOS_SEED_PASSWORD) with workspace 'Northwind Supplies'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
