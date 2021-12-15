from dataclasses import dataclass, field
from typing import List, Type, TypeVar

from kentik_synth_client.types import *

from .base import PingTraceTest, PingTraceTestSettings


@dataclass
class HostnameTestSettings(PingTraceTestSettings):
    hostname: dict = field(default_factory=dict)


HostnameTestType = TypeVar("HostnameTestType", bound="HostnameTest")


@dataclass
class HostnameTest(PingTraceTest):
    type: TestType = field(init=False, default=TestType.hostname)
    settings: HostnameTestSettings = field(default_factory=HostnameTestSettings)

    @classmethod
    def create(cls: Type[HostnameTestType], name: str, target: str, agent_ids: List[str]) -> HostnameTestType:
        return cls(name=name, settings=HostnameTestSettings(agentIds=agent_ids, hostname=dict(target=target)))
