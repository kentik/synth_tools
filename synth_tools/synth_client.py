import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from kentik_api import KentikAPI

from .syth_tests import SynTest, TestStatus

# from generated.kentik.synthetics.v202101beta1.synthetics_pb2_grpc import SyntheticsAdminService, SyntheticsDataService
# import generated.kentik.synthetics.v202101beta1.synthetics_pb2


log = logging.getLogger("synth_client")


class KentikAPITransport(ABC):
    @abstractmethod
    def __init__(self, credentials: Tuple[str, str], url: str):
        ...

    @abstractmethod
    def req(self, op: str, **kwargs) -> Any:
        return NotImplementedError


class SynthHTTPTransport(KentikAPITransport):
    OPS: Dict[str, Dict[str, Any]] = dict(
        AgentsList=dict(ep="agents", method="get", resp="agents"),
        AgentGet=dict(ep="agents", method="get", params="{id}", resp="agent"),
        AgentPatch=dict(ep="agents", method="patch", params="{id}", body="agent", resp="agent"),
        AgentDelete=dict(ep="agents", method="delete", params="{id}"),
        TestsList=dict(ep="tests", method="get", resp="tests"),
        TestGet=dict(ep="tests", method="get", params="{id}", resp="test"),
        TestCreate=dict(ep="tests", method="post", body="test", resp="test"),
        TestDelete=dict(ep="tests", method="delete", params="{id}"),
        TestPatch=dict(ep="tests", method="patch", params="{id}", body="test", resp="test"),
        TestStatusUpdate=dict(ep="tests", method="put", params="{id}/status", body="test_status"),
        GetHealthForTests=dict(ep="health", method="post", body="health_request", resp="health"),
        GetTraceForTest=dict(ep="health", method="post", params="{id}/results/trace", body="trace_request", resp="*"),
    )
    END_POINTS = dict(
        agents="/synthetics/v202101beta1/agents",
        tests="/synthetics/v202101beta1/tests",
        health="/synthetics/v202101beta1/health/tests",
    )

    def __init__(self, credentials: Tuple[str, str], url: str = "https://synthetics.api.kentik.com"):
        # noinspection PyProtectedMember
        self._session = KentikAPI(*credentials).query._api_connector._session
        self._url = url
        self._methods = dict(
            get=self._session.get,
            put=self._session.put,
            post=self._session.post,
            patch=self._session.patch,
            delete=self._session.delete,
        )

    def _ep(self, fn: str, path: Optional[str] = None) -> str:
        try:
            p = self._url + self.END_POINTS[fn]
            if path:
                return "/".join([p, path])
            else:
                return p
        except KeyError:
            raise RuntimeError(f"No end-point for function '{fn}'")

    def req(self, op: str, **kwargs) -> Any:
        try:
            svc = self.OPS[op]
        except KeyError:
            raise RuntimeError(f"Invalid operation '{op}'")
        try:
            method = self._methods[svc["method"]]
        except KeyError as ex:
            raise RuntimeError(f"Invalid method ({ex}) for operation '{op}'")
        params = svc.get("params")
        if params:
            try:
                path = params.format(**kwargs)
                log.debug("path: %s", path)
            except KeyError as ex:
                raise RuntimeError(f"Missing required parameter '{ex}' for operation '{op}'")
        else:
            path = None
        url = self._ep(svc["ep"], path)
        log.debug("url: %s", url)
        if svc.get("body"):
            try:
                json = kwargs["body"]
            except KeyError as ex:
                raise RuntimeError(f"'{ex}' is required for '{op}'")
            log.debug("body: %s", " ".join([f"{k}:{v}" for k, v in json.items()]))
        else:
            json = None
        r = method(url, json=json)
        if r.status_code != 200:
            raise RuntimeError(f"{svc['method'].upper()} failed - status: {r.status_code} error: {r.content}")
        resp = svc.get("resp")
        if resp:
            if resp == "*":
                return r.json()
            else:
                return r.json()[resp]
        else:
            return None


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
            self._transport = transport(credentials, url=url)
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
    def tests(self) -> List[Dict]:
        return self._transport.req("TestsList")

    def test(self, test_id: str) -> Dict:
        return self._transport.req("TestGet", id=test_id)

    def create_test(self, test: SynTest) -> None:
        return self._transport.req("TestCreate", body=test.to_dict())

    def patch_test(self, test_id: str, test: SynTest, modified: str) -> None:
        body = test.to_dict()
        body["mask"] = modified
        return self._transport.req("TestPatch", id=test_id, body=body)

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
