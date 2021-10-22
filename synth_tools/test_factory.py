import logging
from dataclasses import dataclass
from ipaddress import ip_address
from typing import Any, Callable, Dict, List, Optional, Set
from urllib.parse import urlparse

from kentik_api.public import Device, Interface
from validators import domain

from kentik_synth_client.synth_tests import (
    AgentTest,
    DNSGridTest,
    DNSTest,
    HealthSettings,
    HostnameTest,
    IPTest,
    MeshTest,
    NetworkGridTest,
    PageLoadTest,
    PingTask,
    SynTest,
    TraceTask,
    UrlTest,
)
from kentik_synth_client.types import *
from synth_tools.apis import APIs
from synth_tools.matchers import AllMatcher

log = logging.getLogger("test_factory")


def _fail(msg: str) -> None:
    raise RuntimeError(msg)


def _match_or_use(cfg: Dict[str, Any], section: str, fail: Callable[[str], None] = _fail):
    if not (("use" in cfg) ^ ("match" in cfg)):
        fail(f"Exactly one of 'use' or 'match' sections must be specified in '{section}'")


def _use_list_only(cfg: Dict[str, Any], fail: Callable[[str], None] = _fail) -> None:
    if "match" in cfg:
        fail("Test type does not support matching targets with rules")
    if "use" not in cfg:
        fail("Test type requires list of strings to be specified in the 'use' section")


def _get_use_list(
    cfg: Dict[str, Any], section: str, cls: Optional[type] = None, fail: Callable[[str], None] = _fail
) -> Set[str]:
    if "use" not in cfg:
        fail(f"'use' directive missing in '{section}' (cfg: {cfg}")
    use_list = cfg["use"]
    if type(use_list) != list:
        fail("Invalid 'use' specification: must be a simple list")
    if cls:
        try:
            return set(cls(x) for x in use_list)
        except ValueError as exc:
            fail(f"Invalid value in 'use' list in '{section}': cannot convert to '{cls}': '{exc}'")

    return set(use_list)


def device_addresses(key: str, families: List[int], public_only: bool = False) -> Callable[[Any], List[str]]:
    def extract_device_addresses(device: Device) -> List[str]:
        candidates = set()
        val = getattr(device, key)
        if not val:
            log.warning("device_addresses: device: '%s' has no property: '%s'", str(device), key)
        if type(val) == list:
            for a in val:
                candidates.add(ip_address(a))
        else:
            candidates.add(ip_address(val))
        if not candidates:
            log.debug("device_addresses: device id: '%s' ('%s') has no addresses", device.id, device.device_name)
        return [str(a) for a in candidates if (not public_only or a.is_global) and a.version in families]

    log.debug(
        "device_addresses: returning extractor for key: '%s', families: '%s', public_only: '%s'",
        key,
        families,
        public_only,
    )
    return extract_device_addresses


# noinspection PyUnusedLocal
def interface_addresses(key: str, families: List[int], public_only: bool = False) -> Callable[[Any], List[str]]:
    def extract_interface_addresses(ifc: Interface) -> List[str]:
        candidates = set()
        if ifc.interface_ip:
            candidates.add(ip_address(ifc.interface_ip))
        else:
            log.debug(
                "interface_addresses: interface id: '%s' device_id: '%s' ('%s') has no 'interface_ip'",
                ifc.id,
                ifc.device_id,
                ifc.interface_description,
            )
        if ifc.secondary_ips:
            for a in ifc.secondary_ips:
                candidates.add(ip_address(a.address))
        if not candidates:
            log.debug(
                "interface_addresses: interface id: '%s' device_id: '%s' ('%s') has no addresses",
                ifc.id,
                ifc.device_id,
                ifc.interface_description,
            )
        return [
            str(a) for a in candidates if (not public_only or a.is_global) and (not families or a.version in families)
        ]

    log.debug("interface_addresses: returning extractor for families: '%s', public_only: '%s'", families, public_only)
    return extract_interface_addresses


class AddressSelector:
    @dataclass
    class _AddressSelectorEntry:
        key: str
        source: str
        generator: Callable[[str, List[int], bool], Callable[[Device], List[str]]]

    _ADDRESS_SELECTORS = [
        _AddressSelectorEntry(key="interface_addresses", source="interface", generator=interface_addresses),
        _AddressSelectorEntry(key="sending_ips", source="device", generator=device_addresses),
        _AddressSelectorEntry(key="device_snmp_ip", source="device", generator=device_addresses),
    ]

    def __init__(self, cfg: Dict[str, Any], fail: Callable[[str], None] = _fail):
        if all(e.key not in cfg for e in self._ADDRESS_SELECTORS):
            fail(
                "Address selection missing in 'targets' section. One of '{}' is required".format(
                    ", ".join(e.key for e in self._ADDRESS_SELECTORS)
                )
            )
        self._extractors: Dict[str, Any] = dict(device=[], interface=[])
        for e in self._ADDRESS_SELECTORS:
            if e.key in cfg:
                try:
                    family = IPFamily(cfg[e.key].get("family", "IP_FAMILY_DUAL"))
                except ValueError as exc:
                    family = IPFamily.unspecified
                    fail(
                        "{section}: {error}".format(error=str(exc).replace("IPFamily", "address family"), section=e.key)
                    )

                public_only = cfg[e.key].get("public_only", False)
                if family == IPFamily.dual:
                    families = [4, 6]
                elif family == IPFamily.v4:
                    families = [4]
                elif family == IPFamily.v6:
                    families = [6]
                else:
                    raise RuntimeError(f"Unsupported IPFamily: '{family}'")
                self._extractors[e.source].append(e.generator(e.key, families, public_only))

    @property
    def has_device_extractors(self) -> bool:
        return len(self._extractors["device"]) > 0

    @property
    def has_interface_extractors(self) -> bool:
        return len(self._extractors["interface"]) > 0

    def device_addresses(self, device: Device) -> List[str]:
        addresses = []
        for f in self._extractors["device"]:
            addresses.extend(f(device))
        return addresses

    def interface_addresses(self, ifc: Interface) -> List[str]:
        addresses = []
        for f in self._extractors["interface"]:
            addresses.extend(f(ifc))
        return addresses


def address_targets(api: APIs, cfg: Dict[str, Any], fail: Callable[[str], None] = _fail) -> Set[str]:
    max_targets: Optional[int] = cfg.get("max_matches")
    min_targets: int = cfg.get("min_matches", 1)
    targets: Set[str] = set()

    def is_valid_address(addr: str) -> bool:
        try:
            ip_address(addr)
            return True
        except ValueError:
            log.debug("Invalid address: '%s'", addr)
            return False

    def add_target(a) -> bool:
        if max_targets is None or len(targets) < max_targets:
            targets.add(a)
            return True
        else:
            log.debug("address_targets: target_limit ('%d') reached", max_targets)
            return False

    _match_or_use(cfg, "targets", fail)

    if "use" in cfg:
        addresses = set(_get_use_list(cfg, "targets", fail=fail))
        invalid = [a for a in addresses if not is_valid_address(a)]
        if invalid:
            fail("Invalid addresses in targets: {}".format(", ".join(invalid)))
        return addresses

    cfg = cfg["match"]

    address_selector = AddressSelector(cfg, fail)
    device_matcher = AllMatcher(cfg.get("devices", []))
    log.debug("load_targets: device_matcher: '%s'", device_matcher)
    interface_matcher = AllMatcher(cfg.get("interfaces", []))
    log.debug("load_targets: interface_matcher: '%s'", interface_matcher)

    target_devices = [d for d in api.mgmt.devices.get_all() if device_matcher.match(d)]
    if not target_devices:
        fail("No device matched configuration")

    log.debug("load_targets: target_devices: '%s'", ", ".join([str(d) for d in target_devices]))
    for d in target_devices:
        for a in address_selector.device_addresses(d):
            if not add_target(a):
                return targets
        if (max_targets is None or len(targets) < max_targets) and address_selector.has_interface_extractors:
            for i in api.mgmt.devices.interfaces.get_all(d.id):
                if interface_matcher.match(i):
                    for a in address_selector.interface_addresses(i):
                        if not add_target(a):
                            return targets

    if len(targets) < min_targets:
        fail(f"Only {len(targets)} matched, {min_targets} required")
    return targets


def url_targets(_: APIs, cfg: Dict[str, Any], fail: Callable[[str], None] = _fail) -> Set[str]:
    def valid_url(url: str) -> bool:
        _u = urlparse(url)
        if _u.scheme not in ("http", "https") or not domain(_u.netloc):
            log.debug("invalid url: %s", _u)
            return False
        return True

    _use_list_only(cfg, fail)
    urls = set(_get_use_list(cfg, "targets", fail=fail))
    invalid = [u for u in urls if not valid_url(u)]
    if invalid:
        fail("List contains invalid URLs: {}".format(", ".join(invalid)))
    return urls


def domain_targets(_: APIs, cfg: Dict[str, Any], fail: Callable[[str], None] = _fail) -> Set[str]:
    _use_list_only(cfg, fail)
    names = set(_get_use_list(cfg, "targets", fail=fail))
    invalid = [n for n in names if not domain(n)]
    if invalid:
        fail("List contains invalid names: {}".format(", ".join(invalid)))
    return names


# noinspection PyUnusedLocal
def dummy_loader(_: APIs, cfg: Dict[str, Any], fail: Callable[[str], None] = _fail) -> Set[str]:
    log.debug("dummy_loader: cfg: '%s'", cfg)
    return set()


def _get_agents(api: APIs, cfg, agent_type: Optional[str] = None, fail: Callable[[str], None] = _fail) -> Set[str]:
    _match_or_use(cfg, "agents", fail)
    if "use" in cfg:
        log.debug("_get_agents: use: %s", cfg["use"])
        return _get_use_list(cfg, "agents", cls=str, fail=fail)

    min_agents = cfg.get("min", 1)
    max_agents = cfg.get("max")
    cfg = cfg["match"]
    log.debug("_get_agents: match: %s (min: %d, max: %s)", cfg, min_agents, max_agents)
    agents_matcher = AllMatcher(cfg, max_matches=max_agents)
    agents = set(
        a["id"] for a in api.syn.agents if (not agent_type or a["agentImpl"] == agent_type) and agents_matcher.match(a)
    )
    if len(agents) < min_agents:
        fail(f"Matched {len(agents)} agents, {min_agents} required")
    return agents


def all_agents(api: APIs, cfg: Dict[str, Any], fail: Callable[[str], None] = _fail) -> Set[str]:
    log.debug("all_agents: cfg '%s'", cfg)
    return _get_agents(api, cfg, fail=fail)


def rust_agents(api: APIs, cfg: Dict[str, Any], fail: Callable[[str], None] = _fail) -> Set[str]:
    log.debug("rust_agents: cfg '%s'", cfg)
    return _get_agents(api, cfg, "IMPLEMENT_TYPE_RUST", fail=fail)


def node_agents(api: APIs, cfg: Dict[str, Any], fail: Callable[[str], None] = _fail) -> Set[str]:
    log.debug("node_agents: cfg '%s'", cfg)
    return _get_agents(api, cfg, "IMPLEMENT_TYPE_NODE", fail=fail)


COMMON_TEST_PARAMS = ("name", "type", "period", "ping", "trace", "healthSettings", "protocol", "family", "port")


def get_ping_task_params(cfg: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    _attribute_map = {"timeout": "expiry", "protocol": ""}
    if not cfg:
        return cfg
    out = dict()
    for k, v in cfg.items():
        key = _attribute_map.get(k)
        if key is not None:
            if key:
                out[key] = v
                log.debug("get_ping_task_params: replacing key '%s' with '%s'", k, key)
            else:
                log.debug("get_ping_task_params: ignoring key '%s'", k)
        else:
            out[k] = v
    return out


def get_trace_task_params(cfg: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    _attribute_map = {
        "timeout": "expiry",
    }
    if not cfg:
        return cfg
    out = dict()
    for k, v in cfg.items():
        key = _attribute_map.get(k)
        if key is not None:
            if key:
                out[key] = v
                log.debug("get_trace_task_params: replacing key '%s' with '%s'", k, key)
            else:
                log.debug("get_trace_task_params: ignoring key '%s'", k)
        else:
            out[k] = v
    return out


# noinspection PyUnusedLocal
def make_network_grid_test(
    name: str, targets: List[str], agents: List[str], cfg: dict, fail: Callable[[str], None] = _fail
) -> SynTest:
    return NetworkGridTest.create(name=name, targets=targets, agent_ids=agents)


# noinspection PyUnusedLocal
def make_ip_test(
    name: str, targets: List[str], agents: List[str], cfg: dict, fail: Callable[[str], None] = _fail
) -> SynTest:
    return IPTest.create(name=name, targets=targets, agent_ids=agents)


def make_agent_test(
    name: str, targets: List[str], agents: List[str], cfg: dict, fail: Callable[[str], None] = _fail
) -> SynTest:
    if len(targets) > 1:
        fail(f"{cfg['type']} test accepts only 1 target, {len(targets)} provided ('{targets}')")
    return AgentTest.create(name=name, target=targets[0], agent_ids=agents)


def make_dns_test(
    name: str, targets: List[str], agents: List[str], cfg: dict, fail: Callable[[str], None] = _fail
) -> SynTest:
    if len(targets) > 1:
        fail(f"{cfg['type']} test accepts only 1 target, {len(targets)} provided ('{targets}')")
    servers = cfg.get("servers", [])
    if not servers:
        fail(f"{cfg['type']} requires 'servers' parameter")
    record_type = DNSRecordType(cfg.get("record_type", "DNS_RECORD_A"))
    return DNSTest.create(name=name, target=targets[0], agent_ids=agents, servers=servers, record_type=record_type)


def make_dns_grid_test(
    name: str, targets: List[str], agents: List[str], cfg: dict, fail: Callable[[str], None] = _fail
) -> SynTest:
    servers = cfg.get("servers", [])
    if not servers:
        fail(f"{cfg['type']} requires 'servers' parameter")
    record_type = DNSRecordType(cfg.get("record_type", "DNS_RECORD_A"))
    return DNSGridTest.create(name=name, targets=targets, agent_ids=agents, servers=servers, record_type=record_type)


def make_hostname_test(
    name: str, targets: List[str], agents: List[str], cfg: dict, fail: Callable[[str], None] = _fail
) -> SynTest:
    if len(targets) > 1:
        fail(f"{cfg['type']} test accepts only 1 target, {len(targets)} provided ('{targets}')")
    return HostnameTest.create(name=name, target=targets[0], agent_ids=agents)


# noinspection PyUnusedLocal
def make_mesh_test(
    name: str, targets: List[str], agents: List[str], cfg: dict, fail: Callable[[str], None] = _fail
) -> SynTest:
    return MeshTest.create(name=name, agent_ids=agents)


def get_optional_params(cfg: dict) -> dict:
    return {k: v for k, v in cfg.items() if k not in COMMON_TEST_PARAMS}


def make_page_load_test(
    name: str, targets: List[str], agents: List[str], cfg: dict, fail: Callable[[str], None] = _fail
) -> SynTest:
    if len(targets) > 1:
        fail(f"{cfg['type']} test accepts only 1 target, {len(targets)} provided ('{targets}')")
    optional_params = get_optional_params(cfg)
    ping = "ping" in cfg
    trace = "trace" in cfg
    if ping ^ trace:
        fail(
            "Page_load tests requires both 'ping' and 'trace' to be specified or none ('{}' is missing)".format(
                "ping" if trace else "trace"
            )
        )
    log.debug("make_page_load_test: ping: '%s', trace: '%s'", ping, trace)
    log.debug("make_page_load_test: optional_params: '%s'", ", ".join(f"{k}:{v}" for k, v in optional_params.items()))
    return PageLoadTest.create(name=name, target=targets[0], agent_ids=agents, **optional_params)


def make_url_test(
    name: str, targets: List[str], agents: List[str], cfg: dict, fail: Callable[[str], None] = _fail
) -> SynTest:
    if len(targets) > 1:
        fail(f"{cfg['type']} test accepts only 1 target, {len(targets)} provided ('{targets}')")
    optional_params = get_optional_params(cfg)
    ping = "ping" in cfg
    trace = "trace" in cfg
    if ping ^ trace:
        fail(
            "URL tests requires both 'ping' and 'trace' to be specified or none ('{}' is missing)".format(
                "ping" if trace else "trace"
            )
        )
    log.debug("make_url_test: ping: '%s', trace: '%s'", ping, trace)
    log.debug("make_url_test: optional_params: '%s'", ", ".join(f"{k}:{v}" for k, v in optional_params.items()))
    return UrlTest.create(name=name, target=targets[0], agent_ids=agents, ping=ping, trace=trace, **optional_params)


# noinspection PyUnusedLocal
def set_common_test_params(test: SynTest, cfg: dict, fail: Callable[[str], None] = _fail) -> None:
    if "family" in cfg:
        test.settings.family = IPFamily(cfg.get("family"))
        log.debug("set_common_test_params: test: '%s' family: '%s'", test.name, test.settings.family)
    if "protocol" in cfg:
        test.settings.protocol = Protocol(cfg["protocol"])
        log.debug("set_common_test_params: test: '%s' protocol: '%s'", test.name, test.settings.protocol)
    if "port" in cfg:
        test.settings.port = cfg["port"]
        log.debug("set_common_test_params: test: '%s' port: '%s'", test.name, test.settings.port)
    if "ping" in cfg and type(cfg["ping"]) == dict:
        if "ping" in test.settings.tasks:
            if not hasattr(test.settings, "ping"):
                fail(f"'{test.type.value}' test does not support 'ping'")
            test.settings.ping = PingTask.from_dict(get_ping_task_params(cfg["ping"]))  # type: ignore
            log.debug("set_common_test_params: test: '%s' ping: '%s'", test.name, cfg.get("ping"))
            if "protocol" in cfg["ping"]:
                _global_proto = test.settings.protocol
                test.settings.protocol = Protocol(cfg["ping"]["protocol"])
                log.debug(
                    "set_common_test_params: test: '%s' ping.protocol: '%s' (overrides global: '%s')",
                    test.name,
                    test.settings.protocol,
                    _global_proto,
                )
            if "port" in cfg["ping"]:
                _global_port = test.settings.port
                test.settings.port = cfg["ping"]["port"]
                log.debug(
                    "set_common_test_params: test: '%s' ping.port: '%s'(overrides global: '%s')",
                    test.name,
                    test.settings.port,
                    _global_port,
                )
    # else:
    #     test.settings.ping = None
    if "trace" in cfg and type(cfg["trace"]) == dict:
        if "traceroute" in test.settings.tasks:
            log.debug("set_common_test_params: test: '%s' trace: '%s'", test.name, cfg.get("trace"))
            if not hasattr(test.settings, "trace"):
                fail(f"'{test.type.value} does not support 'trace'")
            test.settings.trace = TraceTask.from_dict(cfg["trace"])  # type: ignore
    # else:
    #     test.settings.trace = None
    if "healthSettings" in cfg:
        log.debug("set_common_test_params: test: '%s' healthSettings: '%s'", test.name, cfg.get("healthSettings"))
        test.settings.healthSettings = HealthSettings.from_dict(cfg["healthSettings"])
    if "period" in cfg:
        log.debug("set_common_test_params: test: '%s' period: '%s'", test.name, cfg.get("period"))
        test.set_period(cfg["period"])
    if "status" in cfg:
        log.debug("set_common_test_params: test: '%s' status: '%s'", test.name, cfg.get("status"))
        log.warning("Test 'status' is ignored on creation. All tests are created in active state.")
        test.status = TestStatus(cfg["status"])


@dataclass
class TestEntry:
    make_test: Callable[[str, List[str], List[str], dict, Callable[[str], None]], SynTest]
    target_loader: Callable[[APIs, Dict[str, Any], Callable[[str], None]], Set[str]]
    agent_loader: Callable[[APIs, Dict[str, Any], Callable[[str], None]], Set[str]]
    requires_targets: bool = True


class TestFactory:
    _MAP: Dict[str, TestEntry] = {
        "network_grid": TestEntry(
            make_test=make_network_grid_test, target_loader=address_targets, agent_loader=rust_agents
        ),
        "ip": TestEntry(make_test=make_ip_test, target_loader=address_targets, agent_loader=rust_agents),
        "agent": TestEntry(make_test=make_agent_test, target_loader=all_agents, agent_loader=rust_agents),
        "dns": TestEntry(make_test=make_dns_test, target_loader=domain_targets, agent_loader=rust_agents),
        "dns_grid": TestEntry(make_test=make_dns_grid_test, target_loader=domain_targets, agent_loader=rust_agents),
        "hostname": TestEntry(make_test=make_hostname_test, target_loader=domain_targets, agent_loader=rust_agents),
        "mesh": TestEntry(
            make_test=make_mesh_test, target_loader=dummy_loader, agent_loader=rust_agents, requires_targets=False
        ),
        "page_load": TestEntry(make_test=make_page_load_test, target_loader=url_targets, agent_loader=node_agents),
        "url": TestEntry(make_test=make_url_test, target_loader=url_targets, agent_loader=rust_agents),
    }

    def create(self, api: APIs, default_name: str, cfg: dict, fail: Callable[[str], None] = _fail) -> SynTest:
        missing = [k for k in ("test", "agents") if k not in cfg]
        if missing:
            fail("Mandatory sections missing in configuration: {}".format(", ".join(missing)))
        test_cfg = cfg["test"]
        test_type = test_cfg.get("type")
        if not test_type:
            fail("No 'test.type' in configuration")
        entry = self._MAP.get(test_type)
        if not entry:
            fail(f"Unsupported test type: {test_type} (supported types: {self._MAP.keys()})")
            raise RuntimeError("Never reached")  # just to make mypy happy :-/

        if entry.requires_targets:
            if "targets" not in cfg:
                fail("Required 'targets' section is missing in configuration")
            targets = entry.target_loader(api, cfg["targets"], fail)
            if not targets:
                fail("No targets matched test configuration")
            log.debug("TestFactory:create: targets: '%s'", ", ".join(targets))
        else:
            if "targets" in cfg:
                log.warning("'targets' section is ignored for '%s' test", test_type)
            targets = set()

        agent_ids = entry.agent_loader(api, cfg["agents"], fail)
        if not agent_ids:
            fail("No agents matched configuration")
        log.debug("TestFactory:create: agent_ids: '%s'", ", ".join([str(a) for a in agent_ids]))

        name = test_cfg.get("name", default_name)
        test = entry.make_test(name, list(targets), list(agent_ids), test_cfg, fail)
        set_common_test_params(test, test_cfg)
        return test
