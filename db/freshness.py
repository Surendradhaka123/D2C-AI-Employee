"""
Auto-refresh logic for Option B: tools silently re-sync stale data before querying.

Each tool checks MAX(fetched_at) for its source. If older than MAX_DATA_AGE_HOURS,
the connector is called live before the DB query runs. Claude and the user never
see the sync happening — they just always get fresh data.
"""

import os
from datetime import datetime, timedelta
from sqlalchemy import func

from db.models import Order, Shipment, AdSpend
from db.session import get_session

MAX_AGE_HOURS = float(os.getenv("MAX_DATA_AGE_HOURS", "1"))

_SOURCE_MODEL = {
    "shopify":    Order,
    "shiprocket": Shipment,
    "meta_ads":   AdSpend,
}

# Which sources each metric depends on
_METRIC_SOURCES = {
    "total_revenue":      ["shopify"],
    "orders_by_status":   ["shopify"],
    "ndr_rate":           ["shiprocket"],
    "avg_shipping_cost":  ["shiprocket"],
    "total_ad_spend":     ["meta_ads"],
    "roas":               ["meta_ads"],
    "cac":                ["meta_ads"],
}


def is_stale(merchant_id: str, source: str) -> bool:
    model = _SOURCE_MODEL.get(source)
    if not model:
        return False

    with get_session() as session:
        latest = session.query(func.max(model.fetched_at)).filter(
            model.merchant_id == merchant_id,
            model.source == source,
        ).scalar()

    if not latest:
        return True  # no data at all — must sync

    return (datetime.utcnow() - latest) > timedelta(hours=MAX_AGE_HOURS)


def refresh_if_stale(merchant_id: str, *sources: str) -> list[str]:
    """
    Silently syncs any stale sources. Returns list of sources that were refreshed.
    Called by tool handlers before every DB query.
    """
    import connectors  # ensures connectors self-register
    from connectors.base import ConnectorRegistry

    refreshed = []
    for source in sources:
        if is_stale(merchant_id, source):
            ConnectorRegistry.get(source).sync(merchant_id)
            refreshed.append(source)

    return refreshed
