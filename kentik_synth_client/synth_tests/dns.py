from dataclasses import dataclass, field
from typing import List, Optional, Type, TypeVar

from kentik_synth_client.types import *

from .base import PingTask, SynTest, SynTestSettings, TraceTask


@dataclass
class DNSTestSettings(SynTestSettings):
    dns: dict = field(default_factory=dict)

    @classmethod
    def task_name(cls) -> Optional[str]:
        return "dns"


DNSTestType = TypeVar("DNSTestType", bound="DNSTest")


@dataclass
class DNSTest(SynTest):
    type: TestType = field(init=False, default=TestType.dns)
    settings: DNSTestSettings = field(default_factory=DNSTestSettings)

    @classmethod
    def create(
        cls: Type[DNSTestType],
        name: str,
        target: str,
        agent_ids: List[str],
        servers: List[str],
        record_type: DNSRecordType = DNSRecordType.A,
        timeout: int = 5000,
        server_port: int = 53,
    ) -> DNSTestType:
        return cls(
            name=name,
            settings=DNSTestSettings(
                agentIds=agent_ids,
                tasks=["dns"],
                dns=dict(target=target, recordType=record_type, servers=servers, timeout=timeout, port=server_port),
            ),
        )

    def set_timeout(self, timeout: int):
        self.settings.dns["dns"]["timeout"] = timeout
