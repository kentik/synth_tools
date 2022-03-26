from dataclasses import dataclass, field
from ipaddress import ip_address
from typing import List, Type, TypeVar

from kentik_synth_client.types import *

from .base import PingTraceTest, PingTraceTestSettings


@dataclass
class IPTestSettings(PingTraceTestSettings):
    ip: dict = field(default_factory=dict)


IPTestType = TypeVar("IPTestType", bound="IPTest")


@dataclass
class IPTest(PingTraceTest):
    type: TestType = field(init=False, default=TestType.ip)
    settings: IPTestSettings = field(default_factory=IPTestSettings)

    @classmethod
    def create(cls: Type[IPTestType], name: str, targets: List[str], agent_ids: List[str]) -> IPTestType:
        addresses = [ip_address(a) for a in targets]
        return cls(
            name=name, settings=IPTestSettings(agentIds=agent_ids, ip=dict(targets=[str(a) for a in sorted(addresses)]))
        )
