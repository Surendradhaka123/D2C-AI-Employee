from datetime import datetime
from typing import Any
from sqlalchemy import func
from sqlalchemy.orm import Session

from db.models import Order, Shipment, AdSpend, Annotation


def _cite(row: Any) -> dict:
    return {
        "source": row.source,
        "source_id": row.source_id,
        "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
        "row_id": row.id,
    }


class Repository:
    def __init__(self, session: Session):
        self.session = session

    # ── Orders ──────────────────────────────────────────────────────────────

    def query_orders(
        self,
        merchant_id: str,
        status: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 50,
    ) -> dict:
        q = self.session.query(Order).filter(Order.merchant_id == merchant_id)
        if status:
            q = q.filter(Order.status == status)
        if date_from:
            q = q.filter(Order.created_at >= date_from)
        if date_to:
            q = q.filter(Order.created_at <= date_to)
        rows = q.order_by(Order.created_at.desc()).limit(limit).all()
        return {
            "data": [
                {
                    "order_number": r.order_number,
                    "status": r.status,
                    "total_amount": r.total_amount,
                    "currency": r.currency,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "item_count": r.item_count,
                    "row_id": r.id,
                }
                for r in rows
            ],
            "citations": [_cite(r) for r in rows],
        }

    # ── Shipments ────────────────────────────────────────────────────────────

    def query_shipments(
        self,
        merchant_id: str,
        courier: str | None = None,
        is_ndr: bool | None = None,
        pincode: str | None = None,
        limit: int = 50,
    ) -> dict:
        q = self.session.query(Shipment).filter(Shipment.merchant_id == merchant_id)
        if courier:
            q = q.filter(Shipment.courier == courier)
        if is_ndr is not None:
            q = q.filter(Shipment.is_ndr == is_ndr)
        if pincode:
            q = q.filter(Shipment.pincode == pincode)
        rows = q.limit(limit).all()
        return {
            "data": [
                {
                    "courier": r.courier,
                    "status": r.status,
                    "pincode": r.pincode,
                    "shipping_cost": r.shipping_cost,
                    "is_ndr": r.is_ndr,
                    "ndr_reason": r.ndr_reason,
                    "row_id": r.id,
                }
                for r in rows
            ],
            "citations": [_cite(r) for r in rows],
        }

    # ── Ad Spends ────────────────────────────────────────────────────────────

    def query_ad_spends(
        self,
        merchant_id: str,
        campaign_name: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 100,
    ) -> dict:
        q = self.session.query(AdSpend).filter(AdSpend.merchant_id == merchant_id)
        if campaign_name:
            q = q.filter(AdSpend.campaign_name.ilike(f"%{campaign_name}%"))
        if date_from:
            q = q.filter(AdSpend.date >= date_from)
        if date_to:
            q = q.filter(AdSpend.date <= date_to)
        rows = q.order_by(AdSpend.date.desc()).limit(limit).all()
        return {
            "data": [
                {
                    "campaign_name": r.campaign_name,
                    "date": r.date,
                    "spend": r.spend,
                    "impressions": r.impressions,
                    "clicks": r.clicks,
                    "conversions": r.conversions,
                    "revenue_attributed": r.revenue_attributed,
                    "roas": round(r.revenue_attributed / r.spend, 2) if r.spend else 0,
                    "row_id": r.id,
                }
                for r in rows
            ],
            "citations": [_cite(r) for r in rows],
        }

    # ── Metrics ──────────────────────────────────────────────────────────────

    def compute_metric(self, merchant_id: str, metric: str) -> dict:
        s = self.session

        if metric == "total_revenue":
            rows = s.query(Order).filter(
                Order.merchant_id == merchant_id,
                Order.status.notin_(["cancelled", "refunded"]),
            ).all()
            value = sum(r.total_amount or 0 for r in rows)
            return {
                "metric": metric,
                "value": round(value, 2),
                "unit": "INR",
                "based_on_rows": len(rows),
                "citations": [_cite(r) for r in rows[:10]],
                "note": f"Sum of {len(rows)} non-cancelled orders. Showing first 10 citations.",
            }

        if metric == "total_ad_spend":
            rows = s.query(AdSpend).filter(AdSpend.merchant_id == merchant_id).all()
            value = sum(r.spend or 0 for r in rows)
            return {
                "metric": metric,
                "value": round(value, 2),
                "unit": "INR",
                "based_on_rows": len(rows),
                "citations": [_cite(r) for r in rows[:10]],
                "note": f"Sum of {len(rows)} ad spend records. Showing first 10 citations.",
            }

        if metric == "ndr_rate":
            total = s.query(func.count(Shipment.id)).filter(Shipment.merchant_id == merchant_id).scalar() or 0
            ndrs = s.query(func.count(Shipment.id)).filter(
                Shipment.merchant_id == merchant_id,
                Shipment.is_ndr == True,
            ).scalar() or 0
            ndr_rows = s.query(Shipment).filter(
                Shipment.merchant_id == merchant_id,
                Shipment.is_ndr == True,
            ).limit(10).all()
            rate = ndrs / total if total else 0
            return {
                "metric": metric,
                "value": round(rate * 100, 2),
                "unit": "%",
                "ndr_count": ndrs,
                "total_shipments": total,
                "citations": [_cite(r) for r in ndr_rows],
                "note": f"{ndrs} NDR out of {total} shipments. Showing 10 NDR citations.",
            }

        if metric == "avg_shipping_cost":
            rows = s.query(Shipment).filter(Shipment.merchant_id == merchant_id).all()
            if not rows:
                return {"metric": metric, "value": 0, "unit": "INR", "citations": []}
            avg = sum(r.shipping_cost or 0 for r in rows) / len(rows)
            return {
                "metric": metric,
                "value": round(avg, 2),
                "unit": "INR",
                "based_on_rows": len(rows),
                "citations": [_cite(r) for r in rows[:10]],
            }

        if metric == "roas":
            spends = s.query(AdSpend).filter(AdSpend.merchant_id == merchant_id).all()
            total_spend = sum(r.spend or 0 for r in spends)
            total_rev = sum(r.revenue_attributed or 0 for r in spends)
            roas = total_rev / total_spend if total_spend else 0
            return {
                "metric": metric,
                "value": round(roas, 2),
                "total_spend_inr": round(total_spend, 2),
                "total_revenue_attributed_inr": round(total_rev, 2),
                "citations": [_cite(r) for r in spends[:10]],
            }

        if metric == "cac":
            spends = s.query(AdSpend).filter(AdSpend.merchant_id == merchant_id).all()
            total_spend = sum(r.spend or 0 for r in spends)
            total_conv = sum(r.conversions or 0 for r in spends)
            cac = total_spend / total_conv if total_conv else 0
            return {
                "metric": metric,
                "value": round(cac, 2),
                "unit": "INR",
                "total_spend_inr": round(total_spend, 2),
                "total_conversions": total_conv,
                "citations": [_cite(r) for r in spends[:10]],
            }

        if metric == "orders_by_status":
            rows = s.query(Order.status, func.count(Order.id)).filter(
                Order.merchant_id == merchant_id
            ).group_by(Order.status).all()
            sample = s.query(Order).filter(Order.merchant_id == merchant_id).limit(5).all()
            return {
                "metric": metric,
                "value": {status: count for status, count in rows},
                "citations": [_cite(r) for r in sample],
            }

        raise ValueError(f"Unknown metric '{metric}'. Valid: total_revenue, total_ad_spend, ndr_rate, avg_shipping_cost, roas, cac, orders_by_status")

    # ── Writes ───────────────────────────────────────────────────────────────

    def annotate_entity(
        self,
        merchant_id: str,
        entity_type: str,
        entity_id: str,
        note: str,
        tag: str | None = None,
        created_by: str = "chat",
    ) -> dict:
        ann = Annotation(
            merchant_id=merchant_id,
            entity_type=entity_type,
            entity_id=entity_id,
            note=note,
            tag=tag,
            created_by=created_by,
        )
        self.session.add(ann)
        self.session.flush()
        return {"annotation_id": ann.id, "status": "created"}

    def flag_ndr_action(
        self,
        merchant_id: str,
        shipment_id: str,
        action: str,
        reason: str,
    ) -> dict:
        return self.annotate_entity(
            merchant_id=merchant_id,
            entity_type="shipment",
            entity_id=shipment_id,
            note=f"NDR action: {action}. Reason: {reason}",
            tag=f"ndr:{action}",
            created_by="chat",
        )

    def set_budget_recommendation(
        self,
        merchant_id: str,
        campaign_id: str,
        recommended_budget: float,
        reason: str,
    ) -> dict:
        return self.annotate_entity(
            merchant_id=merchant_id,
            entity_type="campaign",
            entity_id=campaign_id,
            note=f"Recommended budget: ₹{recommended_budget:,.0f}/day. Reason: {reason}",
            tag="budget_recommendation",
            created_by="chat",
        )
