import logging
from typing import Any, Dict

from kentik_synth_client.types import TestType

from .agent import AgentTest
from .base import HealthSettings, PingTask, SynTest, TraceTask
from .dns import DNSTest
from .dns_grid import DNSGridTest
from .flow import FlowTest
from .hostname import HostnameTest
from .ip import IPTest
from .mesh import MeshTest
from .network_grid import NetworkGridTest
from .page_load import PageLoadTest
from .url import UrlTest

log = logging.getLogger("synth_tests")


def make_synth_test(d: Dict[str, Any]) -> SynTest:
    def _cls_from_type(test_type: TestType) -> Any:
        return {
            TestType.none: SynTest,
            TestType.agent: AgentTest,
            TestType.bgp_monitor: SynTest,
            TestType.dns: DNSTest,
            TestType.dns_grid: DNSGridTest,
            TestType.flow: FlowTest,
            TestType.hostname: HostnameTest,
            TestType.ip: IPTest,
            TestType.mesh: MeshTest,
            TestType.network_grid: NetworkGridTest,
            TestType.page_load: PageLoadTest,
            TestType.url: UrlTest,
        }.get(test_type)

    try:
        cls = _cls_from_type(TestType(d["type"]))
    except KeyError as ex:
        raise RuntimeError(f"Required attribute '{ex}' missing in test data ('{d}')")
    if cls is None:
        raise RuntimeError(f"Unsupported test type: {d['type']}")
    if cls == SynTest:
        log.debug("'%s' tests are not fully supported in the API. Test will have incomplete attributes", d["type"])
    return cls.from_dict(d)
