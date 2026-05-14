import uuid
from datetime import datetime
from sqlalchemy import String, Float, Boolean, DateTime, Text, Integer, UniqueConstraint, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)

    # Provenance — non-nullable on every row
    merchant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)       # 'shopify'
    source_id: Mapped[str] = mapped_column(String(200), nullable=False)   # shopify order id
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    raw_json: Mapped[str] = mapped_column(Text, nullable=False)

    # Normalized fields
    order_number: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str | None] = mapped_column(String(50))
    total_amount: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    customer_email: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime | None] = mapped_column(DateTime)
    item_count: Mapped[int] = mapped_column(Integer, default=1)

    __table_args__ = (
        UniqueConstraint("merchant_id", "source", "source_id", name="uq_order_src"),
        Index("ix_orders_merchant_created", "merchant_id", "created_at"),
    )


class Shipment(Base):
    __tablename__ = "shipments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)

    # Provenance
    merchant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)       # 'shiprocket'
    source_id: Mapped[str] = mapped_column(String(200), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    raw_json: Mapped[str] = mapped_column(Text, nullable=False)

    # Normalized fields
    order_id: Mapped[str | None] = mapped_column(String(200))
    courier: Mapped[str | None] = mapped_column(String(100))
    tracking_number: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str | None] = mapped_column(String(50))
    pincode: Mapped[str | None] = mapped_column(String(20))
    shipping_cost: Mapped[float] = mapped_column(Float, default=0.0)
    is_ndr: Mapped[bool] = mapped_column(Boolean, default=False)
    ndr_reason: Mapped[str | None] = mapped_column(String(200))
    ndr_count: Mapped[int] = mapped_column(Integer, default=0)
    weight_kg: Mapped[float] = mapped_column(Float, default=0.5)
    created_at: Mapped[datetime | None] = mapped_column(DateTime)

    __table_args__ = (
        UniqueConstraint("merchant_id", "source", "source_id", name="uq_shipment_src"),
        Index("ix_shipments_merchant_courier", "merchant_id", "courier"),
    )


class AdSpend(Base):
    __tablename__ = "ad_spends"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)

    # Provenance
    merchant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)       # 'meta_ads'
    source_id: Mapped[str] = mapped_column(String(200), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    raw_json: Mapped[str] = mapped_column(Text, nullable=False)

    # Normalized fields
    campaign_id: Mapped[str | None] = mapped_column(String(200))
    campaign_name: Mapped[str | None] = mapped_column(String(200))
    ad_set_id: Mapped[str | None] = mapped_column(String(200))
    date: Mapped[str | None] = mapped_column(String(20))      # YYYY-MM-DD
    spend: Mapped[float] = mapped_column(Float, default=0.0)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    conversions: Mapped[int] = mapped_column(Integer, default=0)
    revenue_attributed: Mapped[float] = mapped_column(Float, default=0.0)

    __table_args__ = (
        UniqueConstraint("merchant_id", "source", "source_id", name="uq_adspend_src"),
        Index("ix_adspends_merchant_date", "merchant_id", "date"),
    )


class Annotation(Base):
    """Write target for the chat layer — local DB only, never pushed upstream."""
    __tablename__ = "annotations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    merchant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)   # 'order'|'shipment'|'campaign'
    entity_id: Mapped[str] = mapped_column(String(200), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    tag: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    created_by: Mapped[str] = mapped_column(String(50), default="chat")    # 'chat'|'agent'
