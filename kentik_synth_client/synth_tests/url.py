from dataclasses import dataclass, field
from typing import Dict, List, Optional, Type, TypeVar

from kentik_synth_client.types import *

from .base import PingTask, SynTest, SynTestSettings, TraceTask


@dataclass
class UrlTestSettings(SynTestSettings):
    url: dict = field(default_factory=dict)
    ping: PingTask = field(default_factory=PingTask)
    trace: TraceTask = field(default_factory=TraceTask)

    @classmethod
    def task_name(cls) -> Optional[str]:
        return "http"


UrlTestType = TypeVar("UrlTestType", bound="UrlTest")


@dataclass
class UrlTest(SynTest):
    type: TestType = field(init=False, default=TestType.url)
    settings: UrlTestSettings = field(default_factory=UrlTestSettings)

    @classmethod
    def create(
        cls: Type[UrlTestType],
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
    ) -> UrlTestType:
        tasks: List[str] = ["http"]
        if ping:
            tasks.append("ping")
        if trace:
            tasks.append("traceroute")
        return cls(
            name=name,
            settings=UrlTestSettings(
                agentIds=agent_ids,
                url=dict(
                    expiry=expiry,
                    target=target,
                    http=dict(method=method, body=body, headers=headers or {}, ignoreTlsErrors=ignore_tls_errors),
                ),
                tasks=tasks,
            ),
        )
