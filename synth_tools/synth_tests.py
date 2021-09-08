import logging
from dataclasses import dataclass, field, fields
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Type, TypeVar

log = logging.getLogger("synth_tests")


class SerializableEnum(Enum):
    @classmethod
    def from_dict(cls, value: str):
        return cls(value)

    def to_dict(self):
        return self.value


class TestType(SerializableEnum):
    none = "<invalid>"
    hostname = "hostname"
    ip = "ip"
    mesh = "application_mesh"
    network_grid = "network_grid"
    dns_grid = "dns_grid"


class TestStatus(SerializableEnum):
    none = "<invalid>"
    active = "TEST_STATUS_ACTIVE"
    paused = "TEST_STATUS_PAUSED"


class IPFamily(SerializableEnum):
    unspecified = "IP_FAMILY_UNSPECIFIED"
    dual = "IP_FAMILY_DUAL"
    v4 = "IP_FAMILY_V4"
    v6 = "IP_FAMILY_V6"


class Protocol(SerializableEnum):
    none = ""
    icmp = "icmp"
    udp = "udp"
    tcp = "tcp"


_ConfigElementType = TypeVar("_ConfigElementType", bound="_ConfigElement")


@dataclass
class _ConfigElement:
    def to_dict(self) -> dict:
        ret: Dict[str, dict] = dict()
        for k, v in [(f.name, self.__getattribute__(f.name)) for f in fields(self) if f.name[0] != "_"]:
            if hasattr(v, "to_dict"):
                ret[k] = v.to_dict()
            else:
                ret[k] = v
        return ret

    @classmethod
    def from_dict(cls, d: dict) -> _ConfigElementType:
        # noinspection PyProtectedMember
        def get_value(f, v):
            if hasattr(f, "from_dict"):
                return f.from_dict(v)
            else:
                try:
                    return f(v)
                except TypeError:
                    if f._name == "List":
                        return [get_value(type(i), i) for i in v]
                    elif f._name == "Dict":
                        return {_k: get_value(type(_v), _v) for _k, _v in v.items()}
                    else:
                        raise RuntimeError(f"Don't know how to instantiate '{f}' (value: '{v}')")

        _init_fields = {f.name: f for f in fields(cls) if f.init}
        args = {k: get_value(_init_fields[k].type, v) for k, v in d.items() if k in _init_fields.keys()}
        # noinspection PyArgumentList
        inst: _ConfigElementType = cls(**args)
        _other_fields = {f.name: f for f in fields(cls) if not f.init}
        for n, f in _other_fields.items():
            if n[0] == "_":
                k = n.split("_")[1]
            else:
                k = n
            if k in d:
                setattr(inst, n, get_value(f.type, d[k]))
        return inst


@dataclass
class PingTask(_ConfigElement):
    period: int = 60
    count: int = 5
    expiry: int = 3000


@dataclass
class TraceTask(_ConfigElement):
    period: int = 60
    count: int = 3
    protocol: Protocol = Protocol.icmp
    port: int = 0
    expiry: int = 22500
    limit: int = 30


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
    latencyCritical: int = 1
    latencyWarning: int = 2
    packetLossCritical: int = 3
    packetLossWarning: int = 4
    jitterCritical: int = 5
    jitterWarning: int = 6
    httpLatencyCritical: int = 7
    httpLatencyWarning: int = 8
    httpValidCodes: List[int] = field(default_factory=list)
    dnsValidCodes: List[int] = field(default_factory=list)


class DefaultTasks(_DefaultList):
    _values = ("ping", "trace")


@dataclass
class MonitoringSettings(_ConfigElement):
    activationGracePeriod: str = "2"
    activationTimeUnit: str = "m"
    activationTimeWindow: str = "5"
    activationTimes: str = "3"
    notificationChannels: List = field(default_factory=list)


@dataclass
class SynTestSettings(_ConfigElement):
    agentIds: List[str] = field(default_factory=list)
    tasks: List[str] = field(default_factory=DefaultTasks)
    healthSettings: HealthSettings = field(default_factory=HealthSettings)
    monitoringSettings: MonitoringSettings = field(default_factory=MonitoringSettings)
    port: int = 0
    period: int = 0
    protocol: Protocol = field(init=False, default=Protocol.none)
    family: IPFamily = IPFamily.unspecified
    rollupLevel: int = field(init=False, default=1)
    servers: List[str] = field(default_factory=list)


@dataclass
class SynTest(_ConfigElement):
    name: str
    type: TestType = field(init=False, default=TestType.none)
    status: TestStatus = field(default=TestStatus.active)
    deviceId: str = field(init=False, default="0")
    _id: str = field(default="0", init=False)
    _cdate: str = field(default_factory=str, init=False)
    _edate: str = field(default_factory=str, init=False)

    @property
    def id(self) -> str:
        return self._id

    @property
    def cdate(self) -> Optional[datetime]:
        try:
            return datetime.fromisoformat(self._cdate.replace("Z", "+00:00"))
        except ValueError:
            return None

    @property
    def edate(self) -> Optional[datetime]:
        try:
            return datetime.fromisoformat(self._edate.replace("Z", "+00:00"))
        except ValueError:
            return None

    def to_dict(self) -> dict:
        return {"test": super(SynTest, self).to_dict()}

    @classmethod
    def test_from_dict(cls, d: dict):
        def class_for_type(test_type: TestType) -> Any:
            return {
                TestType.none: SynTest,
                TestType.hostname: HostnameTest,
                TestType.ip: IPTest,
                TestType.mesh: MeshTest,
                TestType.network_grid: NetworkGridTest,
                TestType.dns_grid: DNSGridTest,
            }.get(test_type)

        try:
            cls_type = class_for_type(TestType(d["type"]))
        except KeyError as ex:
            raise RuntimeError(f"Required attribute '{ex}' missing in test data ('{d}')")
        if cls_type is None or cls_type == cls:
            raise RuntimeError(f"Unsupported test type: {d['type']}")
        return cls_type.from_dict(d)


@dataclass
class PingTraceTestSettings(SynTestSettings):
    ping: PingTask = field(default_factory=PingTask)
    trace: TraceTask = field(default_factory=TraceTask)
    family: IPFamily = IPFamily.dual


@dataclass
class PingTraceTest(SynTest):
    settings: PingTraceTestSettings = field(default_factory=PingTraceTestSettings)

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
        return cls(name=name, settings=IPTestSettings(agentIds=agent_ids, ip=dict(targets=targets)))


MeshTestType = TypeVar("MeshTestType", bound="MeshTest")


@dataclass
class MeshTest(PingTraceTest):
    type: TestType = field(init=False, default=TestType.mesh)

    @classmethod
    def create(cls: Type[MeshTestType], name: str, agent_ids: List[str]) -> MeshTestType:
        return cls(name=name, settings=PingTraceTestSettings(agentIds=agent_ids))


@dataclass
class GridTestSettings(PingTraceTestSettings):
    networkGrid: dict = field(default_factory=dict)


NetworkGridTestType = TypeVar("NetworkGridTestType", bound="NetworkGridTest")


@dataclass
class NetworkGridTest(PingTraceTest):
    type: TestType = field(init=False, default=TestType.network_grid)
    settings: GridTestSettings = field(default=GridTestSettings(agentIds=[]))

    @classmethod
    def create(
        cls: Type[NetworkGridTestType], name: str, targets: List[str], agent_ids: List[str]
    ) -> NetworkGridTestType:
        return cls(name=name, settings=GridTestSettings(agentIds=agent_ids, networkGrid=dict(targets=targets)))


@dataclass
class DNSGridTestSettings(SynTestSettings):
    dnsGrid: dict = field(default_factory=dict)


DNSGridTestType = TypeVar("DNSGridTestType", bound="DNSGridTest")


@dataclass
class DNSGridTest(SynTest):
    type: TestType = field(init=False, default=TestType.dns_grid)
    settings: DNSGridTestSettings = field(default_factory=DNSGridTestSettings)

    @classmethod
    def create(
        cls: Type[DNSGridTestType], name: str, targets: List[str], agent_ids: List[str], servers: List[str]
    ) -> DNSGridTestType:
        return cls(
            name=name,
            settings=DNSGridTestSettings(
                agentIds=agent_ids, dnsGrid=dict(targets=targets), servers=servers, tasks=["dns"], port=53
            ),
        )

    def set_period(self, period_seconds: int, tasks: Optional[List[str]] = None):
        if tasks:
            log.debug("tasks ('%s') ignored for DNSGridTest", ",".join(tasks))
        self.settings.period = period_seconds
