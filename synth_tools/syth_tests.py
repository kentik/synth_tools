from enum import Enum
import logging
from dataclasses import dataclass, field, fields
from typing import Dict, List, Optional, Tuple, Type, TypeVar

log = logging.getLogger("synth_tests")


class TestStatus(Enum):
    active = "TEST_STATUS_ACTIVE"
    paused = "TEST_STATUS_PAUSED"


class IPFamily(Enum):
    dual = "IP_FAMILY_DUAL"
    v4 = "IP_FAMILY_V4"
    v6 = "IP_FAMILY_V6"


@dataclass
class _ConfigElement:
    def to_dict(self) -> dict:
        ret: Dict[str, dict] = dict()
        for k, v in [(f.name, self.__getattribute__(f.name)) for f in fields(self)]:
            if hasattr(v, "to_dict"):
                ret[k] = v.to_dict()
            else:
                ret[k] = v
        return ret


@dataclass
class PingTask(_ConfigElement):
    period: Optional[int] = 60
    count: Optional[int] = 5
    expiry: Optional[int] = 3000


@dataclass
class TraceTask(_ConfigElement):
    period: Optional[int] = 60
    count: Optional[int] = 3
    protocol: Optional[str] = "icmp"
    port: Optional[int] = 0
    expiry: Optional[int] = 22500
    limit: Optional[int] = 30


class _DefaultList(list):
    _values: Tuple

    def __init__(self):
        super().__init__()
        for v in self._values:
            self.append(v)


class DefaultHTTPValidCodes(_DefaultList):
    _values = (200, 201)


class DefaultDNSValidCodes(_DefaultList):
    _values = (1, 2, 3)


@dataclass
class HealthSettings(_ConfigElement):
    latencyCritical: Optional[int] = 1
    latencyWarning: Optional[int] = 2
    packetLossCritical: Optional[int] = 3
    packetLossWarning: Optional[int] = 4
    jitterCritical: Optional[int] = 5
    jitterWarning: Optional[int] = 6
    httpLatencyCritical: Optional[int] = 7
    httpLatencyWarning: Optional[int] = 8
    httpValidCodes: List[int] = field(default_factory=list)
    dnsValidCodes: List[int] = field(default_factory=list)


class DefaultTasks(_DefaultList):
    _values = ("ping", "trace")


@dataclass
class MonitoringSettings(_ConfigElement):
    activationGracePeriod: Optional[str] = "2"
    activationTimeUnit: Optional[str] = "m"
    activationTimeWindow: Optional[str] = "5"
    activationTimes: Optional[str] = "3"
    notificationChannels: List = field(default_factory=list)


@dataclass
class SynTestSettings(_ConfigElement):
    agentIds: List[str]
    tasks: List[str] = field(default_factory=DefaultTasks)
    healthSettings: HealthSettings = field(default_factory=HealthSettings)
    monitoringSettings: MonitoringSettings = field(default_factory=MonitoringSettings)
    port: Optional[int] = 0
    protocol: str = field(init=False, default="icmp")
    family: str = field(default="IP_FAMILY_DUAL")
    rollupLevel: int = field(init=False, default=1)
    ping: PingTask = field(default_factory=PingTask)
    trace: TraceTask = field(default_factory=TraceTask)


@dataclass
class SynTest(_ConfigElement):
    name: str
    settings: SynTestSettings
    type: str = field(init=False, default="")
    status: str = field(default=TestStatus.active.value)
    deviceId: str = field(init=False, default="0")

    def to_dict(self) -> dict:
        return {"test": super(SynTest, self).to_dict()}

    def set_period(self, period_seconds: int, tasks: Optional[List[str]] = None):
        if not tasks:
            tasks = self.settings.tasks
        else:
            # sanity check
            missing = [t for t in tasks if t not in self.settings.tasks]
            if missing:
                raise RuntimeError("tasks '{}' not presents in test '{}'".format(" ".join(missing), self.name))
        for task_name in tasks:
            self.settings.__getattribute__(task_name).period = period_seconds


@dataclass
class HostnameTestSettings(SynTestSettings):
    hostname: dict = field(default_factory=dict)

    def __init__(self, **kwargs):
        base_args = dict(kwargs)
        del base_args["target"]
        super(HostnameTestSettings, self).__init__(**base_args)
        self.hostname = dict(target=kwargs.get("target"))


HostnameTestType = TypeVar("HostnameTestType", bound="HostnameTest")


@dataclass
class HostnameTest(SynTest):
    type: str = field(init=False, default="hostname")

    @classmethod
    def create(cls: Type[HostnameTestType], name: str, target: str, agent_ids: List[str]) -> HostnameTestType:
        return cls(name=name, settings=HostnameTestSettings(agentIds=agent_ids, target=target))


@dataclass
class IPTestSettings(SynTestSettings):
    ip: dict = field(default_factory=dict)

    def __init__(self, **kwargs):
        base_args = dict(kwargs)
        del base_args["targets"]
        super(IPTestSettings, self).__init__(**base_args)
        self.ip = dict(targets=kwargs.get("targets"))


IPTestType = TypeVar("IPTestType", bound="IPTest")


@dataclass
class IPTest(SynTest):
    type: str = field(init=False, default="ip")

    @classmethod
    def create(cls: Type[IPTestType], name: str, targets: List[str], agent_ids: List[str]) -> IPTestType:
        return cls(name=name, settings=IPTestSettings(agentIds=agent_ids, targets=targets))


MeshTestType = TypeVar("MeshTestType", bound="MeshTest")


@dataclass
class MeshTest(SynTest):
    type: str = field(init=False, default="application_mesh")

    @classmethod
    def create(cls: Type[MeshTestType], name: str, agent_ids: List[str]) -> MeshTestType:
        return cls(name=name, settings=SynTestSettings(agentIds=agent_ids))


@dataclass
class GridTestSettings(SynTestSettings):
    networkGrid: dict = field(default_factory=dict)

    def __init__(self, **kwargs):
        base_args = dict(kwargs)
        del base_args["targets"]
        super(GridTestSettings, self).__init__(**base_args)
        self.networkGrid = dict(targets=kwargs.get("targets"))


GridTestType = TypeVar("GridTestType", bound="GridTest")


@dataclass
class GridTest(SynTest):
    type: str = field(init=False, default="network_grid")

    @classmethod
    def create(cls: Type[GridTestType], name: str, targets: List[str], agent_ids: List[str]) -> GridTestType:
        return cls(name=name, settings=GridTestSettings(agentIds=agent_ids, targets=targets))
