from dataclasses import dataclass, field
from typing import Dict, List, Optional, Type, TypeVar

from kentik_synth_client.types import *

from .base import PingTask, PingTraceTest, PingTraceTestSettings, TraceTask


@dataclass
class PageLoadTestSettings(PingTraceTestSettings):
    pageLoad: dict = field(default_factory=dict)
    ping: PingTask = field(default_factory=PingTask)
    trace: TraceTask = field(default_factory=TraceTask)

    @classmethod
    def task_name(cls) -> Optional[str]:
        return "page-load"


PageLoadTestType = TypeVar("PageLoadTestType", bound="PageLoadTest")


@dataclass
class PageLoadTest(PingTraceTest):
    type: TestType = field(init=False, default=TestType.page_load)
    settings: PageLoadTestSettings = field(default_factory=PageLoadTestSettings)

    @classmethod
    def validate_http_timeout(cls: Type[PageLoadTestType], timeout: int):
        if timeout < 5000:
            raise RuntimeError(f"Invalid parameter value ({timeout}): {cls.type.value} test timeout must be >= 5000ms")

    @classmethod
    def create(
        cls: Type[PageLoadTestType],
        name: str,
        target: str,
        agent_ids: List[str],
        timeout: int = 5000,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        css_selectors: Optional[Dict[str, str]] = None,
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
        cls.validate_http_timeout(timeout)
        return cls(
            name=name,
            settings=PageLoadTestSettings(
                agentIds=agent_ids,
                pageLoad=dict(
                    target=target,
                    timeout=timeout,
                    headers=headers or {},
                    css_selectors=css_selectors or {},
                    ignoreTlsErrors=ignore_tls_errors,
                ),
                tasks=tasks,
            ),
        )

    def set_timeout(self, timeout: int):
        self.validate_http_timeout(timeout)
        self.settings.pageLoad["timeout"] = timeout
