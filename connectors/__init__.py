from connectors.base import BaseConnector, ConnectorRegistry, SyncResult  # noqa: F401

# Import connectors so they self-register
import connectors.shopify      # noqa: F401
import connectors.shiprocket   # noqa: F401
import connectors.meta_ads     # noqa: F401
