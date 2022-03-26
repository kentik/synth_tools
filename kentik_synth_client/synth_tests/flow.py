from dataclasses import dataclass, field
from typing import List, Type, TypeVar

from kentik_synth_client.types import *

from .base import PingTraceTest, PingTraceTestSettings


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
        max_ip_targets: int = 10,
        max_providers: int = 3,
        target_refresh_interval_millis: int = 43200000,
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
                    maxIpTargets=max_ip_targets,
                    maxProviders=max_providers,
                    targetRefreshIntervalMillis=target_refresh_interval_millis,
                ),
            ),
        )
