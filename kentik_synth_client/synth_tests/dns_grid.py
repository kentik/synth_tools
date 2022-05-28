import logging
from dataclasses import dataclass, field
from typing import List, Optional, Type, TypeVar

from kentik_synth_client.types import *

from .base import SynTest, SynTestSettings
from .dns import DNSTest

log = logging.getLogger()


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
        target: str,
        agent_ids: List[str],
        servers: List[str],
        record_type: DNSRecordType = DNSRecordType.A,
        timeout: Optional[int] = None,
        port: int = 53,
    ) -> DNSGridTestType:
        if timeout:
            log.warning("The 'timeout' attribute has been deprecated for 'dns_grid' tests")
        return cls(
            name=name,
            settings=DNSGridTestSettings(
                agentIds=agent_ids,
                tasks=["dns"],
                dnsGrid=dict(target=target, recordType=record_type, servers=servers, port=port),
            ),
        )

    def set_timeout(self, timeout: int):
        self.settings.dnsGrid["timeout"] = timeout
