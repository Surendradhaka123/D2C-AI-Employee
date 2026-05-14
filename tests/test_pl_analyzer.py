"""Tests for the P&L Analyzer agent."""

import os
os.environ["USE_MOCK_DATA"] = "true"
os.environ.setdefault("DATABASE_URL", "sqlite:///test_d2c.db")

import pytest
from agents.pl_analyzer import PLAnalyzerAgent
from agents.base import AgentRunLog
from db.session import init_db
import connectors


def _ensure_seeded():
    init_db()
    from mock_data import MERCHANT_ID
    import connectors
    from connectors.base import ConnectorRegistry
    for c in ConnectorRegistry.all():
        c.sync(MERCHANT_ID)
    return MERCHANT_ID


class TestPLAnalyzer:
    @pytest.fixture(autouse=True)
    def seed(self):
        self.merchant_id = _ensure_seeded()

    def test_returns_agent_run_log(self):
        agent = PLAnalyzerAgent()
        log = agent.run(self.merchant_id)
        assert isinstance(log, AgentRunLog)
        assert log.agent_name == "pl_analyzer"

    def test_trigger_met(self):
        log = PLAnalyzerAgent().run(self.merchant_id)
        assert log.trigger_met is True

    def test_reasoning_steps_populated(self):
        log = PLAnalyzerAgent().run(self.merchant_id)
        assert len(log.reasoning_steps) >= 7
        assert any("GMV" in s for s in log.reasoning_steps)
        assert any("logistics" in s.lower() for s in log.reasoning_steps)
        assert any("marketing" in s.lower() for s in log.reasoning_steps)

    def test_recommendations_have_savings(self):
        log = PLAnalyzerAgent().run(self.merchant_id)
        assert len(log.recommendations) >= 1
        for rec in log.recommendations:
            assert "estimated_savings_inr" in rec
            assert rec["estimated_savings_inr"] >= 0
            assert "action" in rec
            assert "citations" in rec or rec["type"] == "high_return_sku"

    def test_pl_snapshot_in_log(self):
        log = PLAnalyzerAgent().run(self.merchant_id)
        snap = log.__dict__.get("pl_snapshot", {})
        assert "gmv" in snap
        assert "net_revenue" in snap
        assert "contribution_margin" in snap
        assert snap["gmv"] > 0
        assert snap["net_revenue"] <= snap["gmv"]

    def test_to_dict_serializable(self):
        import json
        log = PLAnalyzerAgent().run(self.merchant_id)
        d = log.to_dict()
        # Should not raise
        json.dumps(d)

    def test_detects_broad_campaign_low_roas(self):
        log = PLAnalyzerAgent().run(self.merchant_id)
        types = [r["type"] for r in log.recommendations]
        assert "low_roas_campaign" in types

    def test_detects_high_return_sku(self):
        log = PLAnalyzerAgent().run(self.merchant_id)
        types = [r["type"] for r in log.recommendations]
        assert "high_return_sku" in types

    def test_failure_modes_documented(self):
        """The agent should document failure modes when triggered."""
        log = PLAnalyzerAgent().run(self.merchant_id)
        # With good seed data, failure_modes_hit should be empty
        # But the mechanism must exist
        assert isinstance(log.failure_modes_hit, list)

    def test_confidence_set(self):
        log = PLAnalyzerAgent().run(self.merchant_id)
        assert log.confidence in ("high", "medium", "low")
