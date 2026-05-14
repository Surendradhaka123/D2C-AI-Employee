"""
Seed the database with ZapBold mock data.

Usage:
    python seed.py
    python seed.py --reset   # drop and recreate tables first
"""

import sys
import os

os.environ.setdefault("USE_MOCK_DATA", "true")

from db.session import init_db, engine
from db.models import Base
import connectors  # triggers self-registration
from connectors.base import ConnectorRegistry
from mock_data import MERCHANT_ID


def seed(reset: bool = False) -> None:
    if reset:
        print("Dropping tables...")
        Base.metadata.drop_all(bind=engine)

    print("Initializing schema...")
    init_db()

    print(f"Syncing connectors for merchant: {MERCHANT_ID}")
    for connector in ConnectorRegistry.all():
        result = connector.sync(MERCHANT_ID)
        print(f"  {result}")
        if result.errors:
            for err in result.errors[:3]:
                print(f"    ⚠ {err}")

    print("Done. Database seeded at d2c.db")


if __name__ == "__main__":
    seed(reset="--reset" in sys.argv)
