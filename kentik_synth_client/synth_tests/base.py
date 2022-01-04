import logging
from dataclasses import dataclass, field, fields
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple, Type, TypeVar

import inflection

from kentik_synth_client.types import *

log = logging.getLogger("synth_tests")


@dataclass
class Defaults:
    period: int = 60
    expiry: int = 5000
    family: IPFamily = IPFamily.dual


_ConfigElementType = TypeVar("_ConfigElementType", bound="_ConfigElement")


@dataclass
class _ConfigElement:
    def to_dict(self) -> dict:
        def value_to_dict(value: Any) -> Any:
            if hasattr(value, "to_dict"):
                return value.to_dict()
            elif type(value) == dict:
                return {_k: value_to_dict(_v) for _k, _v in value.items()}
            elif type(value) == list:
                return [value_to_dict(_v) for _v in value]
            else:
                return value

        ret: Dict[str, dict] = dict()
        for k, v in [(f.name, self.__getattribute__(f.name)) for f in fields(self) if f.name[0] != "_"]:
            ret[k] = value_to_dict(v)
        return ret

    @classmethod
    def from_dict(cls: Type[_ConfigElementType], d: dict) -> _ConfigElementType:
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
        inst = cls(**args)  # type: ignore
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
class _MonitoringTask(_ConfigElement):
    expiry: int

    @property
    def task_name(self):
        return ""


@dataclass
class PingTask(_MonitoringTask):
    count: int = 5
    expiry: int = 3000  # a.k.a. timeout
    delay: int = 0  # inter-probe delay
    protocol: Protocol = Protocol.icmp
    port: int = 0

    @property
    def task_name(self):
        return "ping"


@dataclass
class TraceTask(_MonitoringTask):
    count: int = 3
    expiry: int = 22500  # a.k.a. timeout
    limit: int = 30  # max. hop count
    delay: int = 0  # inter-probe delay
    protocol: Protocol = Protocol.icmp
    port: int = 33434

    @property
    def task_name(self):
        return "traceroute"


class _DefaultList(list):
    _values: Tuple

    def __init__(self):
        super().__init__()
        for v in self._values:
            self.append(v)

    def to_dict(self):
        return list(self._values)


class DefaultHTTPValidCodes(_DefaultList):
    _values = (200, 201)


class DefaultDNSValidCodes(_DefaultList):
    _values = (1, 2, 3)


@dataclass
class HealthSettings(_ConfigElement):
    latencyCritical: float = 0.0
    latencyWarning: float = 0.0
    latencyCriticalStddev: float = 0.0
    latencyWarningStddev: float = 0.0
    packetLossCritical: int = 0
    packetLossWarning: int = 0
    jitterCritical: float = 0.0
    jitterWarning: float = 0.0
    jitterCriticalStddev: float = 0.0
    jitterWarningStddev: float = 0.0
    httpLatencyCritical: float = 0.0
    httpLatencyWarning: float = 0.0
    httpLatencyCriticalStddev: float = 0.0
    httpLatencyWarningStddev: float = 0.0
    httpValidCodes: List[int] = field(default_factory=list)
    dnsValidCodes: List[int] = field(default_factory=list)
    unhealthySubtestThreshold: int = 1


class DefaultTasks(_DefaultList):
    _values = ("ping", "traceroute")


@dataclass
class MonitoringSettings(_ConfigElement):
    activationGracePeriod: str = "2"
    activationTimeUnit: str = "m"
    activationTimeWindow: str = "5"
    activationTimes: str = "3"
    notificationChannels: List = field(default_factory=list)


@dataclass
class SynTestSettings(_ConfigElement):
    family: IPFamily = Defaults.family
    period: int = Defaults.period
    agentIds: List[str] = field(default_factory=list)
    tasks: List[str] = field(default_factory=DefaultTasks)
    healthSettings: HealthSettings = field(default_factory=HealthSettings)
    notificationChannels: List[str] = field(default_factory=list)

    @classmethod
    def task_name(cls) -> Optional[str]:
        return None

    def to_dict(self) -> dict:
        def _id(i: str) -> str:
            try:
                return f"{int(i):010}"
            except ValueError:
                return i

        self.agentIds.sort(key=lambda x: _id(x))
        return super().to_dict()


@dataclass
class UserInfo(_ConfigElement):
    id: str = ""
    email: str = ""
    fullName: str = ""

    def __str__(self):
        if all(not x for x in (self.__dict__.values())):
            return "<empty>"
        if self.fullName:
            return f"{self.fullName} user_id: {self.id} e-mail: {self.email}"
        else:
            return f"user_id: {self.id} e-mail: {self.email}"


@dataclass
class SynTest(_ConfigElement):
    name: str
    type: TestType = field(init=False, default=TestType.none)
    status: TestStatus = field(default=TestStatus.active)
    settings: SynTestSettings = field(default_factory=SynTestSettings)
    _id: str = field(default="0", init=False)
    _cdate: str = field(default_factory=str, init=False)
    _edate: str = field(default_factory=str, init=False)
    _createdBy: UserInfo = field(default_factory=UserInfo, init=False)
    _lastUpdatedBy: UserInfo = field(default_factory=UserInfo, init=False)

    @property
    def id(self) -> str:
        return self._id

    @property
    def deployed(self) -> bool:
        return self.id != "0"

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

    @property
    def created_by(self) -> Optional[str]:
        return str(self._createdBy)

    @property
    def last_updated_by(self) -> Optional[str]:
        return str(self._lastUpdatedBy)

    @property
    def targets(self) -> List[str]:
        type_label = inflection.camelize(self.type.value, False)
        try:
            d = getattr(self.settings, type_label)
            if "target" in d:
                return [d["target"]]
            if "targets" in d:
                return sorted(d["targets"])
        except AttributeError:
            pass
        log.debug("'%s' (type: '%s'): Test has no targets", self.name, self.type.value)
        return []

    @property
    def configured_tasks(self) -> Set[str]:
        tasks = set(
            f.name
            for f in fields(self.settings)
            if f.name
            and hasattr(f.type, "task_name")
            and self.settings.__getattribute__(f.name).task_name in self.settings.tasks
        )
        n = self.settings.task_name()
        if n:
            tasks.add(n)
        return tasks

    def undeploy(self):
        self._id = "0"

    def to_dict(self) -> dict:
        return {"test": super(SynTest, self).to_dict()}

    def set_period(self, period_seconds: int):
        self.settings.period = period_seconds

    def set_timeout(self, timeout_seconds: float):
        if hasattr(self.settings, "expiry"):
            setattr(self.settings, "expiry", timeout_seconds * 1000)


@dataclass
class PingTraceTestSettings(SynTestSettings):
    ping: PingTask = field(default_factory=PingTask)
    trace: TraceTask = field(default_factory=TraceTask)


@dataclass
class PingTraceTest(SynTest):
    settings: PingTraceTestSettings = field(default_factory=PingTraceTestSettings)

    def set_timeout(self, timeout_seconds: float, tasks: Optional[List[str]] = None):
        for t in self.configured_tasks:
            if not tasks or t in tasks:
                self.settings.__getattribute__(t).expiry = int(timeout_seconds * 1000)  # API wants it in millis
