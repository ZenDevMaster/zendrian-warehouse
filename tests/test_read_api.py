"""Tests for the authenticated read-only stocktake API."""

import os
import tempfile
import unittest
from datetime import datetime

from app import create_app
from config import Config
from models import LocationInventory, StocktakeSession, User, db


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SECRET_KEY = "test"


class ReadApiTests(unittest.TestCase):
    def setUp(self):
        os.environ["STOCKTAKE_READ_API_TOKEN"] = "test-token"
        self.app = create_app(TestConfig)
        self.client = self.app.test_client()
        with self.app.app_context():
            user = User.query.first()
            user.username = "niel"
            session = StocktakeSession(
                session_code="1234",
                operator_id=user.id,
                owner="niel",
                started_at=datetime(2026, 8, 10, 9, 0),
                last_scan_at=datetime(2026, 8, 10, 10, 0),
                closed_at=datetime(2026, 8, 10, 10, 0),
                is_open=False,
                total_scans=3,
            )
            db.session.add(session)
            db.session.flush()
            db.session.add_all(
                [
                    LocationInventory(session_id=session.id, location="A.1.1", sku="ZX6", quantity=2),
                    LocationInventory(session_id=session.id, location="B.1.1", sku="ZX6", quantity=3),
                    LocationInventory(session_id=session.id, location="A.1.1", sku="ZX9", quantity=1),
                ]
            )
            db.session.commit()
            second = StocktakeSession(
                session_code="5678",
                operator_id=user.id,
                owner="niel",
                started_at=datetime(2026, 8, 10, 13, 0),
                last_scan_at=datetime(2026, 8, 10, 13, 30),
                closed_at=datetime(2026, 8, 10, 13, 30),
                is_open=False,
                total_scans=1,
            )
            db.session.add(second)
            db.session.flush()
            db.session.add(
                LocationInventory(session_id=second.id, location="C.1.1", sku="ZX9", quantity=4)
            )
            db.session.commit()

    def tearDown(self):
        os.environ.pop("STOCKTAKE_READ_API_TOKEN", None)

    def auth(self):
        return {"Authorization": "Bearer test-token"}

    def test_requires_bearer_token(self):
        response = self.client.get("/api/v1/sessions")
        self.assertEqual(response.status_code, 401)

    def test_lists_owner_sessions(self):
        response = self.client.get(
            "/api/v1/sessions?owner=NIEL&closed_only=true", headers=self.auth()
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [session["session_code"] for session in response.json["sessions"]],
            ["5678", "1234"],
        )

    def test_latest_inventory_has_location_rows_and_sku_totals(self):
        response = self.client.get(
            "/api/v1/inventory/latest?owner=niel&closed_only=true", headers=self.auth()
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json["sku_totals"],
            [{"quantity": 4, "sku": "ZX9"}],
        )
        self.assertEqual(len(response.json["inventory"]), 1)

    def test_rejects_invalid_since(self):
        response = self.client.get(
            "/api/v1/sessions?since=not-a-date", headers=self.auth()
        )
        self.assertEqual(response.status_code, 400)

    def test_inventory_by_date_combines_split_count_sessions(self):
        response = self.client.get(
            "/api/v1/inventory/by-date?owner=niel&closed_only=true&date=2026-08-10",
            headers=self.auth(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json["sessions"]), 2)
        self.assertEqual(
            response.json["sku_totals"],
            [{"quantity": 5, "sku": "ZX6"}, {"quantity": 5, "sku": "ZX9"}],
        )


if __name__ == "__main__":
    unittest.main()
