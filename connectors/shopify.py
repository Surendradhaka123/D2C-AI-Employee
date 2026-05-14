import json
import os
from datetime import datetime
from typing import Any

import httpx

from connectors.base import BaseConnector, ConnectorRegistry
from db.models import Order

USE_MOCK = os.getenv("USE_MOCK_DATA", "true").lower() == "true"


@ConnectorRegistry.register
class ShopifyConnector(BaseConnector):
    source_name = "shopify"
    capabilities = ["read_orders"]

    def __init__(self):
        self.shop_url = os.getenv("SHOPIFY_SHOP_URL", "")
        self.access_token = os.getenv("SHOPIFY_ACCESS_TOKEN", "")

    def fetch_raw(self, merchant_id: str, since: datetime) -> list[dict[str, Any]]:
        if USE_MOCK:
            from mock_data import generate_shopify_orders
            return generate_shopify_orders()

        orders: list[dict] = []
        url = f"https://{self.shop_url}/admin/api/2024-01/orders.json"
        params = {
            "status": "any",
            "updated_at_min": since.isoformat(),
            "limit": 250,
        }
        headers = {"X-Shopify-Access-Token": self.access_token}

        with httpx.Client(timeout=30) as client:
            while url:
                resp = client.get(url, params=params, headers=headers)
                resp.raise_for_status()
                batch = resp.json().get("orders", [])
                orders.extend(batch)

                link = resp.headers.get("Link", "")
                if 'rel="next"' in link:
                    parts = [p.strip() for p in link.split(",")]
                    next_parts = [p for p in parts if 'rel="next"' in p]
                    url = next_parts[0].split(";")[0].strip().strip("<>") if next_parts else None
                    params = {}
                else:
                    url = None

        return orders

    def normalize(self, raw: dict[str, Any], merchant_id: str) -> list[Order]:
        created_raw = raw.get("created_at", "")
        created_at = None
        if created_raw:
            try:
                created_at = datetime.fromisoformat(created_raw.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                pass

        return [Order(
            merchant_id=merchant_id,
            source=self.source_name,
            source_id=str(raw["id"]),
            fetched_at=datetime.utcnow(),
            raw_json=json.dumps(raw),
            order_number=str(raw.get("order_number", "")),
            status=raw.get("financial_status") or raw.get("fulfillment_status") or "pending",
            total_amount=float(raw.get("total_price", 0) or 0),
            currency=raw.get("currency", "INR"),
            customer_email=raw.get("email", ""),
            created_at=created_at,
            item_count=len(raw.get("line_items", [])),
        )]
