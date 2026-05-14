import json
import os
from datetime import datetime
from typing import Any

import httpx

from connectors.base import BaseConnector, ConnectorRegistry
from db.models import Shipment

USE_MOCK = os.getenv("USE_MOCK_DATA", "true").lower() == "true"
API_BASE = "https://apiv2.shiprocket.in/v1/external"


@ConnectorRegistry.register
class ShiprocketConnector(BaseConnector):
    source_name = "shiprocket"
    capabilities = ["read_shipments"]

    def __init__(self):
        self.email = os.getenv("SHIPROCKET_EMAIL", "")
        self.password = os.getenv("SHIPROCKET_PASSWORD", "")
        self._token: str | None = None

    def _get_token(self) -> str:
        if self._token:
            return self._token
        resp = httpx.post(
            f"{API_BASE}/auth/login",
            json={"email": self.email, "password": self.password},
            timeout=15,
        )
        resp.raise_for_status()
        self._token = resp.json()["token"]
        return self._token

    def fetch_raw(self, merchant_id: str, since: datetime) -> list[dict[str, Any]]:
        if USE_MOCK:
            from mock_data import generate_shiprocket_shipments
            return generate_shiprocket_shipments()

        token = self._get_token()
        headers = {"Authorization": f"Bearer {token}"}
        shipments: list[dict] = []
        page = 1

        with httpx.Client(timeout=30) as client:
            while True:
                resp = client.get(
                    f"{API_BASE}/shipments",
                    params={"page": page, "per_page": 100},
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json().get("data", {})
                batch = data.get("data", [])
                if not batch:
                    break
                shipments.extend(batch)
                if page >= data.get("last_page", 1):
                    break
                page += 1

        return shipments

    def normalize(self, raw: dict[str, Any], merchant_id: str) -> list[Shipment]:
        created_raw = raw.get("created_at", "")
        created_at = None
        if created_raw:
            try:
                created_at = datetime.fromisoformat(created_raw.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                pass

        status = str(raw.get("status", "")).upper()
        is_ndr = status in ("NDR", "RTO", "RETURN")

        return [Shipment(
            merchant_id=merchant_id,
            source=self.source_name,
            source_id=str(raw["id"]),
            fetched_at=datetime.utcnow(),
            raw_json=json.dumps(raw),
            order_id=str(raw.get("order_id", "")),
            courier=raw.get("courier_name", ""),
            tracking_number=raw.get("awb_code", ""),
            status=raw.get("status", ""),
            pincode=str(raw.get("delivery_postcode", "")),
            shipping_cost=float(raw.get("freight_charge", 0) or 0),
            is_ndr=is_ndr,
            ndr_reason=raw.get("ndr_reason"),
            ndr_count=int(raw.get("ndr_count", 0) or 0),
            weight_kg=float(raw.get("weight", 0.5) or 0.5),
            created_at=created_at,
        )]
