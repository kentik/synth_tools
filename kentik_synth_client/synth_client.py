import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse

from .api_transport import KentikAPITransport
from .api_transport_http import SynthHTTPTransport
from .synth_tests import SynTest, TestStatus

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

    @property
    def agents(self) -> List[Dict]:
        return self._transport.req("AgentsList")

    def agent(self, agent_id: str) -> Dict:
        return self._transport.req("AgentGet", id=agent_id)

    def patch_agent(self, agent_id: str, data: dict, modified: str) -> None:
        return self._transport.req("AgentPatch", id=agent_id, body=dict(agent=data, mask=modified))

    @property
    def tests(self) -> List[SynTest]:
        return [SynTest.test_from_dict(t) for t in self._transport.req("TestsList")]

    def list_tests(self, presets: bool = False, raw: bool = False) -> Any:
        r = self._transport.req("TestsList", params=dict(presets=presets))
        if raw:
            return r
        else:
            return [SynTest.test_from_dict(t) for t in r]

    def test(self, test: Union[str, SynTest]) -> SynTest:
        if isinstance(test, SynTest):
            test_id = test.id
        else:
            test_id = test
        return SynTest.test_from_dict(self._transport.req("TestGet", id=test_id))

    def create_test(self, test: SynTest) -> SynTest:
        return SynTest.test_from_dict(self._transport.req("TestCreate", body=test.to_dict()))

    def patch_test(self, test: SynTest, modified: str) -> SynTest:
        if test.id == 0:
            raise RuntimeError(f"test '{test.name}' has not been created yet (id=0). Cannot patch")
        body = test.to_dict()
        body["mask"] = modified
        return SynTest.test_from_dict(self._transport.req("TestPatch", id=test.id, body=body))

    def delete_test(self, test: Union[str, SynTest]) -> None:
        if isinstance(test, SynTest):
            test_id = test.id
        else:
            test_id = test
        return self._transport.req("TestDelete", id=test_id)

    def set_test_status(self, test_id: str, status: TestStatus) -> dict:
        return self._transport.req("TestStatusUpdate", id=test_id, body=dict(id=test_id, status=status.value))

    def health(
        self,
        test_ids: List[str],
        start: datetime,
        end: datetime,
        augment: bool = False,
        agent_ids: Optional[List[str]] = None,
        task_ids: Optional[List[str]] = None,
    ) -> List[Dict]:
        return self._transport.req(
            "GetHealthForTests",
            body=dict(
                ids=test_ids,
                startTime=start.isoformat(),
                endTime=end.isoformat(),
                augment=augment,
                agentIds=agent_ids if agent_ids else [],
                taskIds=task_ids if task_ids else [],
            ),
        )

    def trace(
        self,
        test_id: str,
        start: datetime,
        end: datetime,
        agent_ids: Optional[List[str]] = None,
        ips: Optional[List[str]] = None,
    ):
        return self._transport.req(
            "GetTraceForTest",
            id=test_id,
            body=dict(
                id=test_id,
                startTime=start.isoformat(),
                endTime=end.isoformat(),
                agentIds=agent_ids if agent_ids else [],
                targetIps=ips if ips else [],
            ),
        )
