from dataclasses import dataclass, field
from typing import List, Type, TypeVar
from kentik_synth_client.types import *
from .base import PingTraceTestSettings, PingTraceTest


@dataclass
class FlowTestSettings(PingTraceTestSettings):
    flow: dict = field(default_factory=dict)


FlowTestType = TypeVar("FlowTestType", bound="FlowTest")


@dataclass
class FlowTest(PingTraceTest):
    type: TestType = field(init=False, default=TestType.flow)
    settings: FlowTestSettings = field(default=FlowTestSettings(agentIds=[]))

    # noinspection PyShadowingBuiltins
    @classmethod
    def create(
        cls: Type[FlowTestType],
        name: str,
        target: str,
        agent_ids: List[str],
        target_type: FlowTestSubType,
        direction: DirectionType,
        inet_direction: DirectionType,
        max_tasks: int = 5,
        target_refresh_interval: int = 43200000,
    ) -> FlowTestType:
        return cls(
            name=name,
            settings=FlowTestSettings(
                agentIds=agent_ids,
                flow=dict(
                    target=target,
                    type=target_type,
                    direction=direction,
                    inetDirection=inet_direction,
                    maxTasks=max_tasks,
                    targetRefreshIntervalMillis=target_refresh_interval,
                ),
            ),
        )

    @property
    def targets(self) -> List[str]:
        d = self.settings.flow
        return [f"{d['direction']}:{d['type']}:{d['target']}"]