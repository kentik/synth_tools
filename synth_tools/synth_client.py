from datetime import datetime, timezone, timedelta
import logging
from kentik_api import KentikAPI
from typing import Any, List, Dict, Optional, Tuple, Union
# from generated.kentik.synthetics.v202101beta1.synthetics_pb2_grpc import SyntheticsAdminService, SyntheticsDataService
# import generated.kentik.synthetics.v202101beta1.synthetics_pb2


log = logging.getLogger("synth_client")


class SynthHTTPTransport:
    OPS: Dict[str, Dict[str, Any]] = dict(
        AgentsList=dict(ep="agents", method="get", params=None, resp="agents"),
        AgentGet=dict(ep="agents", method="get", params=["id"], resp="agent"),
        AgentPatch=dict(ep="agents", method="patch", params=["id"], data="agent", resp="agent"),
        AgentDelete=dict(ep="agents", method="delete", params=["id"]),
        TestsList=dict(ep="tests", method="get", params=None, resp="tests"),
        TestGet=dict(ep="tests", method="get", params=["id"], resp="test"),
        TestCreate=dict(ep="tests", method="post", params=None, data="test", resp="test"),
        TestDelete=dict(ep="tests", method="delete", params=["id"]),
        TestPatch=dict(ep="tests", method="patch", params=["id"], resp="test"),
        TestStatusUpdate=dict(ep="tests", method="put", params=["id", "suffix"], data="test_status")
        )
    END_POINTS = dict(
        agents="/synthetics/v202101beta1/agents",
        tests="/synthetics/v202101beta1/tests",
        health="/synthetics/v202101beta1/health/tests"
        )

    def __init__(self, api_client: KentikAPI, url: str = "https://synthetics.api.kentik.com"):
        # noinspection PyProtectedMember
        self._session = api_client.query._api_connector._session
        self._url = url
        self._methods = dict(
            get=self._session.get,
            put=self._session.put,
            post=self._session.post,
            patch=self._session.patch,
            delete=self._session.delete)

    def _ep(self, fn: str, params: Optional[List[str]] = None) -> str:
        try:
            p = self._url + self.END_POINTS[fn]
            if params:
                return "/".join([p] + params)
            else:
                return p
        except KeyError:
            raise RuntimeError(f"No end-point for function '{fn}'")

    def req(self, op, **kwargs) -> Any:
        try:
            svc = self.OPS[op]
        except KeyError:
            raise RuntimeError(f"Invalid operation '{op}'")
        try:
            method = self._methods[svc["method"]]
        except KeyError as ex:
            raise RuntimeError(f"Invalid method ({ex}) for operation '{op}'")
        if svc["params"]:
            try:
                params = [kwargs[p] for p in svc["params"]]
                log.debug("params: %s", params)
                for p in svc["params"]:
                    del kwargs[p]
            except KeyError as ex:
                raise RuntimeError(f"Missing required parameter '{ex}' for operation '{op}'")
        else:
            params = []
        url = self._ep(svc["ep"], params)
        log.debug("url: %s", url)
        log.debug("kwargs: %s", " ".join([f"{k}={v}" for k, v in kwargs.items()]))
        r = method(url, **kwargs)
        if r.status_code != 200:
            raise RuntimeError(f"{svc['method'].upper()} failed - status: {r.status_code} error: {r.content}")
        resp = svc.get("resp")
        if resp:
            return r.json()[resp]
        else:
            return None


class KentikSynthClient:
    def __init__(self, credentials: Tuple[str, str], url: str ="https://synthetics.api.kentik.com"):
        self._credentials = credentials
        self._url = url
        self._transport = SynthHTTPTransport(KentikAPI(*credentials), url=url)

    @property
    def agents(self) -> List[Dict]:
        return self._transport.req("AgentsList")

    def agent(self, agent_id: str) -> Dict:
        return self._transport.req("AgentGet", id=agent_id)

    def patch_agent(self, agent_id: str, data: dict, modified: str) -> None:
        return self._transport.req("AgentPatch", id=agent_id, json=dict(agent=data, mask=modified))

    @property
    def tests(self) -> List[Dict]:
        return self._transport.req("TestsList")

    def test(self, test_id: str) -> Dict:
        return self._transport.req("TestGet", id=test_id)

    def create_test(self, data: dict) -> None:
        return self._transport.req("TestCreate", json=data)

    def patch_test(self, test_id: str, data: dict, modified: str) -> None:
        return self._transport.req("TestPatch", id=test_id, json=dict(test=data, mask=modified))

    def delete_test(self, test_id: str) -> None:
        return self._transport.req("TestDelete", id=test_id)

    def set_test_status(self, test_id: str, status: str) -> dict:
        return self._transport.req("TestStatusUpdate", id=test_id, suffix="status", json=dict(id=test_id, status=status))

    def health(self, tests: List[str],
               start: datetime,
               end: datetime,
               augment: bool = False,
               agents: Optional[List[str]] = None,
               tasks: Optional[List[str]] = None) -> List[Dict]:
        raise NotImplementedError("method is not yet implemented")
