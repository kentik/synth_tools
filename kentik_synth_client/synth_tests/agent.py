from dataclasses import dataclass, field
from typing import List, Type, TypeVar

from kentik_synth_client.types import *

from .base import PingTraceTest, PingTraceTestSettings


@dataclass
class AgentTestSettings(PingTraceTestSettings):
    agent: dict = field(default_factory=dict)


AgentTestType = TypeVar("AgentTestType", bound="AgentTest")


@dataclass
class AgentTest(PingTraceTest):
    type: TestType = field(init=False, default=TestType.agent)
    settings: AgentTestSettings = field(default_factory=AgentTestSettings)

    @classmethod
    def create(
        cls: Type[AgentTestType], name: str, target: str, agent_ids: List[str], use_private_ips: bool = False
    ) -> AgentTestType:
        return cls(
            name=name,
            settings=AgentTestSettings(agentIds=agent_ids, agent=dict(target=target, useLocalIp=use_private_ips)),
        )
