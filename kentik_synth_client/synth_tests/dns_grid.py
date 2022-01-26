from dataclasses import dataclass, field
from typing import List, Type, TypeVar

from kentik_synth_client.types import *

from .base import SynTest, SynTestSettings


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
        cls: Type[DNSGridTestType],
        name: str,
        targets: List[str],
        agent_ids: List[str],
        servers: List[str],
        record_type: DNSRecordType = DNSRecordType.A,
        timeout: int = 5000,
    ) -> DNSGridTestType:
        return cls(
            name=name,
            settings=DNSGridTestSettings(
                agentIds=agent_ids,
                tasks=["dns"],
                dnsGrid=dict(targets=targets, type=record_type, servers=servers, timeout=timeout),
            ),
        )

    def set_timeout(self, timeout: int):
        self.settings.dnsGrid["dns"]["timeout"] = timeout
