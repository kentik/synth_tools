import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse

from .api_transport import KentikAPITransport
from .api_transport_http import SynthHTTPTransport
from .synth_tests import SynTest, make_synth_test
from .types import TestStatus

log = logging.getLogger("synth_client")


class KentikSynthClient:
    def __init__(
        self,
        credentials: Tuple[str, str],
        transport: Optional[KentikAPITransport] = None,
        url: Optional[str] = None,
        proxy: Optional[str] = None,
    ):
        if url:
            u = urlparse(url)
            dns_path = u.netloc.split(".")
            if dns_path[0] == "api":
                dns_path.insert(0, "synthetics")
                log.debug("Setting url to: %s (input: %s)", u._replace(netloc=".".join(dns_path)).geturl(), url)
                self._url = u._replace(netloc=".".join(dns_path)).geturl()
            else:
                self._url = url
        else:
            self._url = "https://synthetics.api.kentik.com"
        if transport:
            # noinspection Mypy
            # noinspection PyCallingNonCallable
            self._transport = transport(credentials, url=self._url, proxy=proxy)  # type: ignore
        else:
            self._transport = SynthHTTPTransport(credentials, url=self._url, proxy=proxy)

    def list_agents(self) -> List[Dict]:
        return self._transport.req("AgentsList")

    @property
    def agents(self) -> List[Dict]:
        return self.list_agents()

    def agent(self, agent_id: str) -> Dict:
        return self._transport.req("AgentGet", id=agent_id)

    def update_agent(self, agent_id: str, data: dict) -> None:
        return self._transport.req("AgentUpdate", id=agent_id, body=dict(agent=data))

    def delete_agent(self, agent_id: str) -> Dict:
        return self._transport.req("AgentDelete", id=agent_id)

    @property
    def tests(self) -> List[SynTest]:
        return self.list_tests()

    def list_tests(self, presets: bool = False, raw: bool = False) -> Any:
        r = self._transport.req("TestsList", params=dict(presets=presets))
        if raw:
            return r
        else:
            return [make_synth_test(t) for t in r]

    def test(self, test: Union[str, SynTest]) -> SynTest:
        if isinstance(test, SynTest):
            test_id = test.id
        else:
            test_id = test
        return make_synth_test(self._transport.req("TestGet", id=test_id))

    def test_raw(self, test_id: str) -> Any:
        return self._transport.req("TestGet", id=test_id)

    def create_test(self, test: SynTest) -> SynTest:
        return make_synth_test(self._transport.req("TestCreate", body=test.to_dict()))

    def update_test(self, test: SynTest, tid: Optional[str] = None) -> SynTest:
        if not test.deployed:
            if not tid:
                raise RuntimeError(f"test '{test.name}' has not been deployed yet (id=0) and no test id specified")
        else:
            tid = test.id
        body = test.to_dict()
        return make_synth_test(self._transport.req("TestUpdate", id=tid, body=body))

    def delete_test(self, test: Union[str, SynTest]) -> None:
        if isinstance(test, SynTest):
            test_id = test.id
        else:
            test_id = test
        self._transport.req("TestDelete", id=test_id)
        if isinstance(test, SynTest):
            test.undeploy()

    def set_test_status(self, test_id: str, status: TestStatus) -> dict:
        return self._transport.req("SetTestStatus", id=test_id, body=dict(id=test_id, status=status.value))

    def get_results(
        self,
        test_ids: List[str],
        start: datetime,
        end: datetime,
        agent_ids: Optional[List[str]] = None,
        task_ids: Optional[List[str]] = None,
    ) -> List[Dict]:
        return self._transport.req(
            "GetResultsForTests",
            body=dict(
                ids=test_ids,
                startTime=start.isoformat(),
                endTime=end.isoformat(),
                agentIds=agent_ids if agent_ids else [],
                taskIds=task_ids if task_ids else [],
            ),
        )

    def results(
        self,
        test: SynTest,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        periods: int = 3,
        **kwargs,
    ) -> List[dict]:
        if not test.deployed:
            raise RuntimeError(f"Test '{test.name}[id: {test.id}] is not deployed yet")
        if not end:
            end = datetime.now(tz=timezone.utc)
        if not start:
            start = end - timedelta(seconds=periods * test.settings.period)
        return self.get_results([test.id], start=start, end=end, **kwargs)

    def trace(
        self,
        test: Union[str, SynTest],
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        periods: int = 3,
        agent_ids: Optional[List[str]] = None,
        ips: Optional[List[str]] = None,
    ):
        if isinstance(test, SynTest):
            t = test
        else:
            t = self.test(test)
        if not t.deployed:
            raise RuntimeError(f"Test '{t.name}[id: {t.id}] is not deployed yet")
        if not end:
            end = datetime.now(tz=timezone.utc)
        if not start:
            start = end - timedelta(seconds=periods * t.settings.period)
        return self._transport.req(
            "GetTraceForTest",
            id=t.id,
            body=dict(
                id=t.id,
                startTime=start.isoformat(),
                endTime=end.isoformat(),
                agentIds=agent_ids if agent_ids else [],
                targetIps=ips if ips else [],
            ),
        )
