from dataclasses import dataclass, field
from typing import List, Optional, Type, TypeVar

from kentik_synth_client.types import *

from .base import SynTest, SynTestSettings


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
        targets: List[str],
        agent_ids: List[str],
        servers: List[str],
        record_type: DNSRecordType = DNSRecordType.A,
        timeout: int = 5000,
    ) -> DNSTestType:
        return cls(
            name=name,
            settings=DNSTestSettings(
                agentIds=agent_ids,
                tasks=["dns"],
                dns=dict(targets=targets, type=record_type, servers=servers, timeout=timeout),
            ),
        )

    def set_timeout(self, timeout: int):
        self.settings.dns["dns"]["timeout"] = timeout
