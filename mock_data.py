"""
Mock API responses for ZapBold — a fictional D2C footwear brand.

The data is designed to tell a clear story:
  - DTDC has 28% NDR vs Delhivery's 8% → switch saves ~₹30k/month
  - Broad Meta campaign has ROAS 1.3 → pause saves ₹40k/month
  - SKU Sneaker-BLK-42 has 18% return rate → ₹12k/month impact
"""

import random
from datetime import datetime, timedelta

random.seed(42)  # deterministic

MERCHANT_ID = "zapbold-001"
BASE_DATE = datetime.utcnow() - timedelta(days=60)

COURIERS = [
    {"name": "Delhivery",  "share": 0.48, "ndr_rate": 0.08, "cost": 62.0},
    {"name": "BlueDart",   "share": 0.24, "ndr_rate": 0.05, "cost": 87.0},
    {"name": "DTDC",       "share": 0.20, "ndr_rate": 0.28, "cost": 55.0},
    {"name": "Xpressbees", "share": 0.08, "ndr_rate": 0.12, "cost": 58.0},
]

DTDC_PINCODES = ["400050", "400051", "400052", "411001", "411002", "411028"]
OTHER_PINCODES = [
    "560001", "560002", "560034", "110001", "110011", "110020",
    "500001", "500032", "600001", "600040", "700001", "700013",
    "380001", "395001", "226001", "302001",
]

SKUS = [
    {"id": "SKU-SNKR-BLK-42", "name": "Sneaker Black 42", "price": 1499.0, "return_rate": 0.18},
    {"id": "SKU-SNDL-BRN-38", "name": "Sandal Brown 38",  "price": 899.0,  "return_rate": 0.08},
    {"id": "SKU-LFRS-WHT-44", "name": "Loafer White 44",  "price": 1299.0, "return_rate": 0.05},
    {"id": "SKU-BOOT-BLK-41", "name": "Boot Black 41",    "price": 1899.0, "return_rate": 0.06},
    {"id": "SKU-SPRT-RED-40", "name": "Sport Red 40",     "price": 1199.0, "return_rate": 0.07},
]

CAMPAIGNS = [
    {
        "id": "camp_retargeting_001",
        "name": "Retargeting — Past Visitors",
        "daily_spend": 500.0,
        "roas": 4.2,
    },
    {
        "id": "camp_lookalike_001",
        "name": "Lookalike — 1% LTV",
        "daily_spend": 833.0,
        "roas": 2.1,
    },
    {
        "id": "camp_broad_001",
        "name": "Broad — Awareness",
        "daily_spend": 667.0,
        "roas": 1.3,
    },
]

NDR_REASONS = [
    "Customer not available",
    "Wrong address",
    "Customer refused delivery",
    "Address not found",
    "Out of delivery area",
]


def _days_ago(n: int) -> datetime:
    return BASE_DATE + timedelta(days=n)


def generate_shopify_orders() -> list[dict]:
    orders = []
    for i in range(500):
        day = random.randint(0, 59)
        sku = random.choices(SKUS, weights=[s["return_rate"] + 0.1 for s in SKUS])[0]
        is_returned = random.random() < sku["return_rate"]
        is_cancelled = (not is_returned) and random.random() < 0.08

        if is_returned:
            status = "refunded"
        elif is_cancelled:
            status = "cancelled"
        else:
            status = "paid"

        orders.append({
            "id": 5000 + i,
            "order_number": 1000 + i,
            "financial_status": status,
            "fulfillment_status": "fulfilled" if status == "paid" else None,
            "total_price": str(sku["price"]),
            "currency": "INR",
            "email": f"customer{i}@example.com",
            "created_at": _days_ago(day).isoformat() + "Z",
            "line_items": [
                {
                    "id": 9000 + i,
                    "product_id": sku["id"],
                    "title": sku["name"],
                    "quantity": 1,
                    "price": str(sku["price"]),
                }
            ],
        })
    return orders


def generate_shiprocket_shipments() -> list[dict]:
    shipments = []
    shipment_id = 10000

    # Only ship paid orders (status == 'paid')
    orders = generate_shopify_orders()
    shippable = [o for o in orders if o["financial_status"] == "paid"]

    for order in shippable[:400]:  # ship 400 of ~335 paid orders (some overlap)
        courier_cfg = random.choices(
            COURIERS, weights=[c["share"] for c in COURIERS]
        )[0]

        is_ndr = random.random() < courier_cfg["ndr_rate"]
        # DTDC NDR concentrated in specific pincodes
        if courier_cfg["name"] == "DTDC":
            pincode = random.choice(DTDC_PINCODES)
        else:
            pincode = random.choice(OTHER_PINCODES)

        order_date = datetime.fromisoformat(order["created_at"].replace("Z", ""))
        shipped_at = order_date + timedelta(days=random.randint(1, 3))

        shipments.append({
            "id": shipment_id,
            "order_id": str(order["id"]),
            "courier_name": courier_cfg["name"],
            "awb_code": f"AWB{shipment_id}",
            "status": "NDR" if is_ndr else "Delivered",
            "delivery_postcode": pincode,
            "freight_charge": courier_cfg["cost"],
            "is_return": is_ndr,
            "ndr_reason": random.choice(NDR_REASONS) if is_ndr else None,
            "ndr_count": random.randint(1, 3) if is_ndr else 0,
            "weight": round(random.uniform(0.3, 1.5), 2),
            "created_at": shipped_at.isoformat() + "Z",
        })
        shipment_id += 1

    return shipments


def generate_meta_ad_spends() -> list[dict]:
    records = []
    record_id = 20000

    for day in range(60):
        date_str = _days_ago(day).strftime("%Y-%m-%d")
        for camp in CAMPAIGNS:
            spend = camp["daily_spend"] * random.uniform(0.92, 1.08)
            revenue = spend * camp["roas"] * random.uniform(0.9, 1.1)
            clicks = int(spend / 3.5 * random.uniform(0.8, 1.2))
            impressions = clicks * random.randint(8, 15)
            conversions = int(revenue / 1200)

            records.append({
                "id": str(record_id),
                "campaign_id": camp["id"],
                "campaign_name": camp["name"],
                "ad_set_id": f"adset_{camp['id']}_{day}",
                "date_start": date_str,
                "spend": round(spend, 2),
                "impressions": impressions,
                "clicks": clicks,
                "actions": [{"action_type": "purchase", "value": str(conversions)}],
                "purchase_roas": [{"action_type": "omni_purchase", "value": str(round(camp["roas"] * random.uniform(0.9, 1.1), 2))}],
                "website_purchase_roas": round(revenue, 2),
            })
            record_id += 1

    return records
