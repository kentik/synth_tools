from dataclasses import dataclass, field
from typing import List, Type, TypeVar

from kentik_synth_client.types import *

from .base import PingTraceTest, PingTraceTestSettings


@dataclass
class NetworkMeshTestSettings(PingTraceTestSettings):
    networkMesh: dict = field(default_factory=dict)


NetworkMeshTestType = TypeVar("NetworkMeshTestType", bound="NetworkMeshTest")


@dataclass
class NetworkMeshTest(PingTraceTest):
    type: TestType = field(init=False, default=TestType.network_mesh)
    settings: NetworkMeshTestSettings = field(default_factory=NetworkMeshTestSettings)

    @classmethod
    def create(
        cls: Type[NetworkMeshTestType], name: str, agent_ids: List[str], use_private_ips: bool = False
    ) -> NetworkMeshTestType:
        return cls(
            name=name,
            settings=NetworkMeshTestSettings(agentIds=agent_ids, networkMesh=dict(useLocalIp=use_private_ips)),
        )
