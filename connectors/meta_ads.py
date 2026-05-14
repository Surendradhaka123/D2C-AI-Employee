import json
import os
from datetime import datetime
from typing import Any

from connectors.base import BaseConnector, ConnectorRegistry
from db.models import AdSpend

USE_MOCK = os.getenv("USE_MOCK_DATA", "true").lower() == "true"


@ConnectorRegistry.register
class MetaAdsConnector(BaseConnector):
    source_name = "meta_ads"
    capabilities = ["read_ad_spends"]

    def __init__(self):
        self.app_id = os.getenv("META_APP_ID", "")
        self.app_secret = os.getenv("META_APP_SECRET", "")
        self.access_token = os.getenv("META_ACCESS_TOKEN", "")
        self.ad_account_id = os.getenv("META_AD_ACCOUNT_ID", "")

    def fetch_raw(self, merchant_id: str, since: datetime) -> list[dict[str, Any]]:
        if USE_MOCK:
            from mock_data import generate_meta_ad_spends
            return generate_meta_ad_spends()

        try:
            from facebook_business.api import FacebookAdsApi
            from facebook_business.adobjects.adaccount import AdAccount
            from facebook_business.adobjects.adsinsights import AdsInsights
        except ImportError:
            raise ImportError("Run: pip install facebook-business")

        FacebookAdsApi.init(self.app_id, self.app_secret, self.access_token)
        account = AdAccount(self.ad_account_id)

        fields = [
            AdsInsights.Field.campaign_id,
            AdsInsights.Field.campaign_name,
            AdsInsights.Field.adset_id,
            AdsInsights.Field.spend,
            AdsInsights.Field.impressions,
            AdsInsights.Field.clicks,
            AdsInsights.Field.actions,
            AdsInsights.Field.purchase_roas,
            AdsInsights.Field.website_purchase_roas,
            AdsInsights.Field.date_start,
        ]
        params = {
            "level": "adset",
            "time_range": {
                "since": since.strftime("%Y-%m-%d"),
                "until": datetime.utcnow().strftime("%Y-%m-%d"),
            },
            "time_increment": 1,
        }
        insights = account.get_insights(fields=fields, params=params)
        return [dict(i) for i in insights]

    def normalize(self, raw: dict[str, Any], merchant_id: str) -> list[AdSpend]:
        actions = {a["action_type"]: float(a["value"]) for a in raw.get("actions", [])}
        conversions = int(actions.get("purchase", actions.get("omni_purchase", 0)))
        revenue = float(raw.get("website_purchase_roas", 0) or 0)

        source_id = f"{raw.get('campaign_id')}_{raw.get('ad_set_id', raw.get('adset_id', ''))}_{raw.get('date_start')}"

        return [AdSpend(
            merchant_id=merchant_id,
            source=self.source_name,
            source_id=source_id,
            fetched_at=datetime.utcnow(),
            raw_json=json.dumps(raw),
            campaign_id=raw.get("campaign_id"),
            campaign_name=raw.get("campaign_name"),
            ad_set_id=raw.get("ad_set_id") or raw.get("adset_id"),
            date=raw.get("date_start"),
            spend=float(raw.get("spend", 0) or 0),
            impressions=int(raw.get("impressions", 0) or 0),
            clicks=int(raw.get("clicks", 0) or 0),
            conversions=conversions,
            revenue_attributed=revenue,
        )]
