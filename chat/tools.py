"""
Tool definitions and handlers for the Claude tool-use loop.

5 read tools + 3 write tools.
Every handler returns {"data": [...], "citations": [...]} so Claude can cite its answers.
"""

from datetime import datetime
from db.session import get_session
from db.repository import Repository
from db.freshness import refresh_if_stale, _METRIC_SOURCES


TOOL_DEFINITIONS = [
    {
        "name": "query_orders",
        "description": "Query normalized order data from Shopify. Returns orders with provenance citations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "merchant_id": {"type": "string", "description": "Merchant identifier"},
                "status": {"type": "string", "description": "Filter by status: paid, refunded, cancelled, pending"},
                "date_from": {"type": "string", "description": "ISO date string, e.g. 2026-04-01"},
                "date_to": {"type": "string", "description": "ISO date string, e.g. 2026-05-14"},
                "limit": {"type": "integer", "description": "Max rows to return (default 50)"},
            },
            "required": ["merchant_id"],
        },
    },
    {
        "name": "query_shipments",
        "description": "Query shipment data from Shiprocket. Includes NDR (Non-Delivery Report) status, courier, pincode.",
        "input_schema": {
            "type": "object",
            "properties": {
                "merchant_id": {"type": "string"},
                "courier": {"type": "string", "description": "Filter by courier name e.g. DTDC, Delhivery, BlueDart"},
                "is_ndr": {"type": "boolean", "description": "True to return only NDR shipments"},
                "pincode": {"type": "string", "description": "Filter by delivery pincode"},
                "limit": {"type": "integer", "description": "Max rows (default 50)"},
            },
            "required": ["merchant_id"],
        },
    },
    {
        "name": "query_ad_spends",
        "description": "Query Meta Ads campaign spend, impressions, clicks, conversions and attributed revenue.",
        "input_schema": {
            "type": "object",
            "properties": {
                "merchant_id": {"type": "string"},
                "campaign_name": {"type": "string", "description": "Partial campaign name filter"},
                "date_from": {"type": "string", "description": "YYYY-MM-DD"},
                "date_to": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": ["merchant_id"],
        },
    },
    {
        "name": "compute_metric",
        "description": (
            "Compute a pre-defined aggregate metric. "
            "Available metrics: total_revenue, total_ad_spend, ndr_rate, avg_shipping_cost, roas, cac, orders_by_status"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "merchant_id": {"type": "string"},
                "metric": {
                    "type": "string",
                    "enum": ["total_revenue", "total_ad_spend", "ndr_rate", "avg_shipping_cost", "roas", "cac", "orders_by_status"],
                },
            },
            "required": ["merchant_id", "metric"],
        },
    },
    {
        "name": "run_pl_analyzer",
        "description": (
            "Run the D2C P&L Analyzer agent. Computes Revenue (Shopify) - Logistics Cost (Shiprocket) "
            "- Marketing Cost (Meta Ads) = Contribution Margin. Returns ranked profit leaks and recommendations."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "merchant_id": {"type": "string"},
                "period_days": {"type": "integer", "description": "Lookback period in days (default 30)"},
            },
            "required": ["merchant_id"],
        },
    },
    {
        "name": "annotate_entity",
        "description": "Write a note or tag to an order, shipment, or campaign. Stored locally only.",
        "input_schema": {
            "type": "object",
            "properties": {
                "merchant_id": {"type": "string"},
                "entity_type": {"type": "string", "enum": ["order", "shipment", "campaign"]},
                "entity_id": {"type": "string", "description": "The row_id from a previous query result"},
                "note": {"type": "string"},
                "tag": {"type": "string", "description": "Optional short tag e.g. 'high-value', 'review'"},
            },
            "required": ["merchant_id", "entity_type", "entity_id", "note"],
        },
    },
    {
        "name": "flag_ndr_action",
        "description": "Flag a shipment NDR with an action decision. Stored locally — does not trigger Shiprocket.",
        "input_schema": {
            "type": "object",
            "properties": {
                "merchant_id": {"type": "string"},
                "shipment_id": {"type": "string", "description": "row_id from a shipments query"},
                "action": {"type": "string", "enum": ["reattempt", "rto", "hold"]},
                "reason": {"type": "string"},
            },
            "required": ["merchant_id", "shipment_id", "action", "reason"],
        },
    },
    {
        "name": "set_budget_recommendation",
        "description": "Record a budget recommendation for a Meta campaign. Stored locally — does not update Meta.",
        "input_schema": {
            "type": "object",
            "properties": {
                "merchant_id": {"type": "string"},
                "campaign_id": {"type": "string"},
                "recommended_budget": {"type": "number", "description": "Recommended daily budget in INR"},
                "reason": {"type": "string"},
            },
            "required": ["merchant_id", "campaign_id", "recommended_budget", "reason"],
        },
    },
]


def handle_tool(name: str, inputs: dict) -> dict:
    """Dispatch a tool call to the appropriate handler. Returns serializable dict."""
    merchant_id = inputs.get("merchant_id", "")

    with get_session() as session:
        repo = Repository(session)

        if name == "query_orders":
            refresh_if_stale(merchant_id, "shopify")
            date_from = _parse_date(inputs.get("date_from"))
            date_to = _parse_date(inputs.get("date_to"))
            return repo.query_orders(
                merchant_id,
                status=inputs.get("status"),
                date_from=date_from,
                date_to=date_to,
                limit=inputs.get("limit", 50),
            )

        if name == "query_shipments":
            refresh_if_stale(merchant_id, "shiprocket")
            return repo.query_shipments(
                merchant_id,
                courier=inputs.get("courier"),
                is_ndr=inputs.get("is_ndr"),
                pincode=inputs.get("pincode"),
                limit=inputs.get("limit", 50),
            )

        if name == "query_ad_spends":
            refresh_if_stale(merchant_id, "meta_ads")
            return repo.query_ad_spends(
                merchant_id,
                campaign_name=inputs.get("campaign_name"),
                date_from=inputs.get("date_from"),
                date_to=inputs.get("date_to"),
            )

        if name == "compute_metric":
            sources = _METRIC_SOURCES.get(inputs["metric"], [])
            refresh_if_stale(merchant_id, *sources)
            return repo.compute_metric(merchant_id, inputs["metric"])

        if name == "run_pl_analyzer":
            refresh_if_stale(merchant_id, "shopify", "shiprocket", "meta_ads")
            from agents.pl_analyzer import PLAnalyzerAgent
            agent = PLAnalyzerAgent()
            log = agent.run(merchant_id, period_days=inputs.get("period_days", 30))
            return log.to_dict()

        if name == "annotate_entity":
            return repo.annotate_entity(
                merchant_id,
                entity_type=inputs["entity_type"],
                entity_id=inputs["entity_id"],
                note=inputs["note"],
                tag=inputs.get("tag"),
            )

        if name == "flag_ndr_action":
            return repo.flag_ndr_action(
                merchant_id,
                shipment_id=inputs["shipment_id"],
                action=inputs["action"],
                reason=inputs["reason"],
            )

        if name == "set_budget_recommendation":
            return repo.set_budget_recommendation(
                merchant_id,
                campaign_id=inputs["campaign_id"],
                recommended_budget=inputs["recommended_budget"],
                reason=inputs["reason"],
            )

    raise ValueError(f"Unknown tool: {name}")


def _parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None
