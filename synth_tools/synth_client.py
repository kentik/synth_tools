import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from .api_transport import KentikAPITransport
from .api_transport_http import SynthHTTPTransport
from .synth_tests import SynTest, TestStatus

log = logging.getLogger("synth_client")


class KentikSynthClient:
    def __init__(
        self,
        credentials: Tuple[str, str],
        transport: Optional[KentikAPITransport] = None,
        url: str = "https://synthetics.api.kentik.com",
    ):
        self._url = url
        if transport:
            # noinspection Mypy
            # noinspection PyCallingNonCallable
            self._transport = transport(credentials, url=url)  # type: ignore
        else:
            self._transport = SynthHTTPTransport(credentials, url=url)

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

    def test(self, test_id: str) -> SynTest:
        return SynTest.test_from_dict(self._transport.req("TestGet", id=test_id))

    def create_test(self, test: SynTest) -> SynTest:
        return SynTest.test_from_dict(self._transport.req("TestCreate", body=test.to_dict()))

    def patch_test(self, test_id: str, test: SynTest, modified: str) -> SynTest:
        body = test.to_dict()
        body["mask"] = modified
        return SynTest.test_from_dict(self._transport.req("TestPatch", id=test_id, body=body))

    def delete_test(self, test_id: str) -> None:
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
