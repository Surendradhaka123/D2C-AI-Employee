"""Tests for connector normalization and registry."""

import os
os.environ["USE_MOCK_DATA"] = "true"
os.environ.setdefault("DATABASE_URL", "sqlite:///test_d2c.db")

import pytest
from datetime import datetime

import connectors  # triggers self-registration
from connectors.base import ConnectorRegistry
from db.models import Order, Shipment, AdSpend


class TestConnectorRegistry:
    def test_all_three_registered(self):
        names = ConnectorRegistry.names()
        assert "shopify" in names
        assert "shiprocket" in names
        assert "meta_ads" in names

    def test_get_by_name(self):
        c = ConnectorRegistry.get("shopify")
        assert c.source_name == "shopify"

    def test_get_unknown_raises(self):
        with pytest.raises(KeyError):
            ConnectorRegistry.get("nonexistent")

    def test_swappable_registration(self):
        """Adding a new connector only requires a new class with decorator."""
        from connectors.base import BaseConnector

        @ConnectorRegistry.register
        class TestConnector(BaseConnector):
            source_name = "test_source"
            def fetch_raw(self, m, s): return []
            def normalize(self, r, m): return []

        assert "test_source" in ConnectorRegistry.names()
        del ConnectorRegistry._registry["test_source"]


class TestShopifyNormalize:
    def setup_method(self):
        self.connector = ConnectorRegistry.get("shopify")

    def test_normalize_basic_order(self):
        raw = {
            "id": 12345,
            "order_number": 1001,
            "financial_status": "paid",
            "total_price": "1299.00",
            "currency": "INR",
            "email": "test@example.com",
            "created_at": "2026-05-01T10:00:00Z",
            "line_items": [{"id": 1, "title": "Sneaker"}],
        }
        rows = self.connector.normalize(raw, "test-merchant")
        assert len(rows) == 1
        order = rows[0]
        assert isinstance(order, Order)
        assert order.source == "shopify"
        assert order.source_id == "12345"
        assert order.total_amount == 1299.0
        assert order.currency == "INR"
        assert order.status == "paid"
        assert order.item_count == 1

    def test_provenance_fields_non_null(self):
        raw = {
            "id": 99999,
            "order_number": 9001,
            "financial_status": "refunded",
            "total_price": "0",
            "currency": "INR",
            "created_at": "2026-04-15T00:00:00Z",
            "line_items": [],
        }
        rows = self.connector.normalize(raw, "merchant-x")
        o = rows[0]
        assert o.merchant_id == "merchant-x"
        assert o.source is not None
        assert o.source_id is not None
        assert o.fetched_at is not None
        assert o.raw_json is not None

    def test_mock_fetch_returns_500_orders(self):
        orders = self.connector.fetch_raw("m1", datetime.utcnow())
        assert len(orders) == 500


class TestShiprocketNormalize:
    def setup_method(self):
        self.connector = ConnectorRegistry.get("shiprocket")

    def test_normalize_ndr_shipment(self):
        raw = {
            "id": 10001,
            "order_id": "5001",
            "courier_name": "DTDC",
            "awb_code": "AWB10001",
            "status": "NDR",
            "delivery_postcode": "400050",
            "freight_charge": 55.0,
            "ndr_reason": "Customer not available",
            "ndr_count": 2,
            "weight": 0.8,
            "created_at": "2026-05-01T10:00:00Z",
        }
        rows = self.connector.normalize(raw, "test-merchant")
        assert len(rows) == 1
        s = rows[0]
        assert isinstance(s, Shipment)
        assert s.is_ndr is True
        assert s.courier == "DTDC"
        assert s.pincode == "400050"
        assert s.shipping_cost == 55.0

    def test_normalize_delivered_shipment(self):
        raw = {
            "id": 10002,
            "order_id": "5002",
            "courier_name": "Delhivery",
            "awb_code": "AWB10002",
            "status": "Delivered",
            "delivery_postcode": "560001",
            "freight_charge": 62.0,
            "ndr_reason": None,
            "ndr_count": 0,
            "weight": 0.5,
            "created_at": "2026-05-02T10:00:00Z",
        }
        rows = self.connector.normalize(raw, "test-merchant")
        s = rows[0]
        assert s.is_ndr is False

    def test_mock_fetch_returns_400_shipments(self):
        shipments = self.connector.fetch_raw("m1", datetime.utcnow())
        assert len(shipments) == 400


class TestMetaAdsNormalize:
    def setup_method(self):
        self.connector = ConnectorRegistry.get("meta_ads")

    def test_normalize_ad_spend(self):
        raw = {
            "id": "20000",
            "campaign_id": "camp_001",
            "campaign_name": "Retargeting",
            "ad_set_id": "adset_001",
            "date_start": "2026-05-01",
            "spend": "500.00",
            "impressions": "12000",
            "clicks": "450",
            "actions": [{"action_type": "purchase", "value": "18"}],
            "website_purchase_roas": "2100.00",
        }
        rows = self.connector.normalize(raw, "test-merchant")
        assert len(rows) == 1
        a = rows[0]
        assert isinstance(a, AdSpend)
        assert a.campaign_name == "Retargeting"
        assert a.spend == 500.0
        assert a.conversions == 18
        assert a.source == "meta_ads"

    def test_mock_fetch_returns_180_records(self):
        records = self.connector.fetch_raw("m1", datetime.utcnow())
        assert len(records) == 180
