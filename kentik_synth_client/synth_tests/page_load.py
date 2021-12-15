from dataclasses import dataclass, field
from typing import Dict, List, Optional, Type, TypeVar

from kentik_synth_client.types import *

from .base import PingTraceTest, PingTraceTestSettings


@dataclass
class PageLoadTestSettings(PingTraceTestSettings):
    pageLoad: dict = field(default_factory=dict)

    @classmethod
    def task_name(cls) -> Optional[str]:
        return "page-load"


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
        expiry: int = 5000,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        body: str = "",
        ignore_tls_errors: bool = False,
        ping: bool = False,
        trace: bool = False,
    ) -> PageLoadTestType:
        tasks: List[str] = [PageLoadTestSettings.task_name()]  # type:ignore
        if ping:
            tasks.append("ping")
        if trace:
            tasks.append("traceroute")
        return cls(
            name=name,
            settings=PageLoadTestSettings(
                agentIds=agent_ids,
                pageLoad=dict(
                    expiry=expiry,
                    target=target,
                    http=dict(method=method, body=body, headers=headers or {}, ignoreTlsErrors=ignore_tls_errors),
                ),
                tasks=tasks,
            ),
        )
