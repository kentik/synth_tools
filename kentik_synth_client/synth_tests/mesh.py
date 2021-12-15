from dataclasses import dataclass, field
from typing import List, Type, TypeVar

from kentik_synth_client.types import *

from .base import PingTraceTest, PingTraceTestSettings

MeshTestType = TypeVar("MeshTestType", bound="MeshTest")


@dataclass
class MeshTest(PingTraceTest):
    type: TestType = field(init=False, default=TestType.mesh)

    @classmethod
    def create(cls: Type[MeshTestType], name: str, agent_ids: List[str]) -> MeshTestType:
        return cls(name=name, settings=PingTraceTestSettings(agentIds=agent_ids))

    @property
    def targets(self) -> List[str]:
        return self.settings.agentIds
