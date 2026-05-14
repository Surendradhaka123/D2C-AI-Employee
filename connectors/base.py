from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from sqlalchemy.orm import Session


@dataclass
class SyncResult:
    source: str
    merchant_id: str
    rows_written: int
    errors: list[str] = field(default_factory=list)
    synced_at: datetime = field(default_factory=datetime.utcnow)

    def __str__(self) -> str:
        status = "OK" if not self.errors else f"{len(self.errors)} errors"
        return f"[{self.source}] {self.rows_written} rows written ({status})"


class BaseConnector(ABC):
    source_name: str
    capabilities: list[str] = []

    @abstractmethod
    def fetch_raw(self, merchant_id: str, since: datetime) -> list[dict[str, Any]]:
        """Fetch raw records from the source API (or mock). Returns list of raw dicts."""
        ...

    @abstractmethod
    def normalize(self, raw: dict[str, Any], merchant_id: str) -> list[Any]:
        """Normalize a raw record into one or more SQLAlchemy ORM instances."""
        ...

    def sync(self, merchant_id: str, since: datetime | None = None) -> SyncResult:
        from db.session import get_session

        if since is None:
            since = datetime.utcnow() - timedelta(days=60)

        errors: list[str] = []
        rows: list[Any] = []

        try:
            raws = self.fetch_raw(merchant_id, since)
        except Exception as exc:
            return SyncResult(self.source_name, merchant_id, 0, [f"fetch_raw failed: {exc}"])

        for raw in raws:
            try:
                rows.extend(self.normalize(raw, merchant_id))
            except Exception as exc:
                errors.append(f"normalize error for {raw.get('id', '?')}: {exc}")

        written = 0
        with get_session() as session:
            for row in rows:
                try:
                    self._upsert(session, row)
                    written += 1
                except Exception as exc:
                    errors.append(f"upsert error: {exc}")

        return SyncResult(self.source_name, merchant_id, written, errors)

    def _upsert(self, session: Session, row: Any) -> None:
        """Upsert by (merchant_id, source, source_id). Database-agnostic."""
        model_cls = type(row)
        existing = session.query(model_cls).filter_by(
            merchant_id=row.merchant_id,
            source=row.source,
            source_id=row.source_id,
        ).first()

        if existing:
            # Update mutable fields; keep original id
            for col in model_cls.__table__.columns:
                if col.name not in ("id", "merchant_id", "source", "source_id"):
                    setattr(existing, col.name, getattr(row, col.name, None))
        else:
            session.add(row)


class ConnectorRegistry:
    _registry: dict[str, type[BaseConnector]] = {}

    @classmethod
    def register(cls, connector_cls: type[BaseConnector]) -> type[BaseConnector]:
        cls._registry[connector_cls.source_name] = connector_cls
        return connector_cls

    @classmethod
    def get(cls, name: str) -> BaseConnector:
        if name not in cls._registry:
            raise KeyError(f"No connector for '{name}'. Available: {list(cls._registry)}")
        return cls._registry[name]()

    @classmethod
    def all(cls) -> list[BaseConnector]:
        return [c() for c in cls._registry.values()]

    @classmethod
    def names(cls) -> list[str]:
        return list(cls._registry.keys())
