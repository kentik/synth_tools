from dataclasses import dataclass, field
from ipaddress import ip_address
from typing import List, Type, TypeVar

from kentik_synth_client.types import *

from .base import PingTraceTest, PingTraceTestSettings, sort_ip_address_list


@dataclass
class GridTestSettings(PingTraceTestSettings):
    networkGrid: dict = field(default_factory=dict)


NetworkGridTestType = TypeVar("NetworkGridTestType", bound="NetworkGridTest")


@dataclass
class NetworkGridTest(PingTraceTest):
    type: TestType = field(init=False, default=TestType.network_grid)
    settings: GridTestSettings = field(default_factory=GridTestSettings)

    @classmethod
    def create(
        cls: Type[NetworkGridTestType], name: str, targets: List[str], agent_ids: List[str]
    ) -> NetworkGridTestType:
        return cls(
            name=name,
            settings=GridTestSettings(agentIds=agent_ids, networkGrid=dict(targets=sort_ip_address_list(targets))),
        )
