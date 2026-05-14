from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class AgentRunLog:
    agent_name: str
    merchant_id: str
    run_at: datetime = field(default_factory=datetime.utcnow)
    trigger_condition: str = ""
    trigger_met: bool = False
    reasoning_steps: list[str] = field(default_factory=list)
    recommendations: list[dict] = field(default_factory=list)
    confidence: str = "high"          # "high" | "medium" | "low"
    failure_modes_hit: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "merchant_id": self.merchant_id,
            "run_at": self.run_at.isoformat(),
            "trigger_condition": self.trigger_condition,
            "trigger_met": self.trigger_met,
            "reasoning_steps": self.reasoning_steps,
            "recommendations": self.recommendations,
            "confidence": self.confidence,
            "failure_modes_hit": self.failure_modes_hit,
        }


class BaseAgent(ABC):
    name: str

    @abstractmethod
    def run(self, merchant_id: str, **kwargs) -> AgentRunLog:
        ...
