from dataclasses import dataclass, field
from typing import Dict, Optional, List, Type, TypeVar
from kentik_synth_client.types import *
from .base import PingTraceTestSettings, PingTraceTest, HTTPTask


@dataclass
class PageLoadTestSettings(PingTraceTestSettings):
    expiry: int = 0
    pageLoad: dict = field(default_factory=dict)
    http: HTTPTask = field(default_factory=HTTPTask)


PageLoadTestType = TypeVar("PageLoadTestType", bound="PageLoadTest")


@dataclass
class PageLoadTest(PingTraceTest):
    type: TestType = field(init=False, default=TestType.page_load)
    settings: PageLoadTestSettings = field(default_factory=PageLoadTestSettings)

    @classmethod
    def create(
        cls: Type[PageLoadTestType],
        name: str,
        target: str,
        agent_ids: List[str],
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        body: str = "",
        ignore_tls_errors: bool = False,
        ping: bool = False,
        trace: bool = False,
    ) -> PageLoadTestType:
        tasks: List[str] = ["http"]
        if ping:
            tasks.append("ping")
        if trace:
            tasks.append("traceroute")
        return cls(
            name=name,
            settings=PageLoadTestSettings(
                agentIds=agent_ids,
                pageLoad=dict(target=target),
                tasks=["page-load"],
                http=HTTPTask(method=method, body=body, headers=headers or {}, ignoreTlsErrors=ignore_tls_errors),
            ),
        )
