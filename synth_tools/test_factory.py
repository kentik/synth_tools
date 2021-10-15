import logging
from dataclasses import dataclass
from ipaddress import ip_address
from urllib.parse import urlparse
from typing import Callable, Dict, Union, List, Set

from kentik_api.public import Device, Interface

from kentik_synth_client.synth_tests import *
from synth_tools.apis import APIs
from synth_tools.matchers import *

log = logging.getLogger("test_factory")


def _fail(msg: str) -> None:
    raise RuntimeError(msg)


def device_addresses(key: str, families: List[int], public_only=False) -> Callable[[Device], List[str]]:
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
        return [str(a) for a in candidates if (not public_only or not a.is_private) and a.version in families]

    log.debug(
        "device_addresses: returning extractor for key: '%s', families: '%s', public_only: '%s'",
        key,
        families,
        public_only,
    )
    return extract_device_addresses


# noinspection PyUnusedLocal
def interface_addresses(key: str, families: List[int], public_only=False) -> Callable[[Interface], List[str]]:
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
            str(a)
            for a in candidates
            if (not public_only or not a.is_private) and (not families or a.version in families)
        ]

    log.debug("interface_addresses: returning extractor for families: '%s', public_only: '%s'", families, public_only)
    return extract_interface_addresses


def address_targets(api: APIs, cfg: Union[List, Dict], fail: Callable[[str], None] = _fail) -> Set[str]:
    # support loading plain list addresses
    if type(cfg) == list:
        return set(cfg)

    address_selectors = {
        "interface_addresses": {"source": "interface", "generator": interface_addresses, "key": None},
        "sending_ips": {"source": "device", "generator": device_addresses, "key": "sending_ips"},
        "snmp_ip": {"source": "device", "generator": device_addresses, "key": "device_snmp_ip"},
    }
    if all(k not in cfg for k in address_selectors):
        fail(
            "Address selection directive missing in 'targets' section. One of '{}' is required".format(
                ", ".join(address_selectors.keys())
            )
        )
    for selector, params in address_selectors.items():
        families = []
        if selector in cfg:
            family = cfg[selector].get("family", "any")
            public_only = cfg[selector].get("public_only", False)
            if family == "any":
                families = [4, 6]
            elif family == "ipv4":
                families = [4]
            elif family == "ipv6":
                families = [6]
            else:
                fail(f"Invalid IP address family '{family}'in 'targets.interface_addresses'")
            params["fn"] = params["generator"](key=params["key"], families=families, public_only=public_only)

    log.debug("load_targets: address_selectors: '%s'", address_selectors)
    device_matcher = AllMatcher(cfg.get("devices", []))
    log.debug("load_targets: device_matcher: '%s'", device_matcher)
    interface_matcher = AllMatcher(cfg.get("interfaces", []))
    log.debug("load_targets: interface_matcher: '%s'", interface_matcher)
    target_devices = []
    for d in api.mgmt.devices.get_all():
        if device_matcher.match(d):
            target_devices.append(d)
    if not target_devices:
        log.warning("load_targets: no device matched")
    else:
        log.debug("load_targets: target_devices: '%s'", ", ".join([str(d) for d in target_devices]))
    targets = set()
    device_address_extractors = [
        params["fn"]
        for selector, params in address_selectors.items()
        if "fn" in params and params["source"] == "device"
    ]
    log.debug("load_targets: device_address_extractors: '%s'", device_address_extractors)
    interface_address_extractors = [
        params["fn"]
        for selector, params in address_selectors.items()
        if "fn" in params and params["source"] == "interface"
    ]
    log.debug("load_targets: interface_address_extractors: '%s'", interface_address_extractors)
    for d in target_devices:
        for func in device_address_extractors:
            for a in func(d):
                targets.add(a)
        if interface_address_extractors:
            for i in api.mgmt.devices.interfaces.get_all(d.id):
                if interface_matcher.match(i):
                    for func in interface_address_extractors:
                        for a in func(i):
                            targets.add(a)
    return targets


def targets_list(_: APIs, cfg: Union[List, Dict], fail: Callable[[str], None] = _fail) -> Set[str]:
    if type(cfg) != list:
        fail("Invalid target specification: selected test type requires simple list of verbatim targets")
    return set(cfg)


def dummy_loader(_: APIs, cfg: Union[List, Dict], fail: Callable[[str], None] = _fail) -> Set[str]:
    log.debug("dummy_loader: cfg: '%s'", cfg)
    return set()


def all_agents(api: APIs, cfg: List[Dict]) -> List[str]:
    agents_matcher = AllMatcher(cfg)
    return [a["id"] for a in api.syn.agents if agents_matcher.match(a)]


def rust_agents(api: APIs, cfg: List[Dict]) -> List[str]:
    agents_matcher = AllMatcher(cfg)
    return [a["id"] for a in api.syn.agents if a["agentImpl"] == "IMPLEMENT_TYPE_RUST" and agents_matcher.match(a)]


def node_agents(api: APIs, cfg: List[Dict]) -> List[str]:
    agents_matcher = AllMatcher(cfg)
    return [a["id"] for a in api.syn.agents if a["agentImpl"] == "IMPLEMENT_TYPE_NODE" and agents_matcher.match(a)]


COMMON_TEST_PARAMS = ("name", "type", "period", "ping", "trace", "healthSettings", "protocol", "family", "port")


def make_network_grid_test(
    name: str, targets: List[str], agents: List[str], cfg: dict, fail: Callable[[str], None] = _fail
) -> SynTest:
    return NetworkGridTest.create(name=name, targets=targets, agent_ids=agents)


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
    servers = cfg.get("servers")
    if not servers:
        fail(f"{cfg['type']} requires 'servers' parameter")
    return DNSTest.create(name=name, target=targets[0], agent_ids=agents, servers=servers)


def make_dns_grid_test(
    name: str, targets: List[str], agents: List[str], cfg: dict, fail: Callable[[str], None] = _fail
) -> SynTest:
    servers = cfg.get("servers")
    if not servers:
        fail(f"{cfg['type']} requires 'servers' parameter")
    return DNSGridTest.create(name=name, targets=targets, agent_ids=agents, servers=servers)


def make_hostname_test(
    name: str, targets: List[str], agents: List[str], cfg: dict, fail: Callable[[str], None] = _fail
) -> SynTest:
    if len(targets) > 1:
        fail(f"{cfg['type']} test accepts only 1 target, {len(targets)} provided ('{targets}')")
    return HostnameTest.create(name=name, target=targets[0], agent_ids=agents)


def make_mesh_test(
    name: str, targets: List[str], agents: List[str], cfg: dict, fail: Callable[[str], None] = _fail
) -> SynTest:
    return MeshTest.create(name=name, agent_ids=agents)


def validate_url(url: str) -> bool:
    _u = urlparse(url)
    if _u.scheme not in ("http", "https") or not _u.netloc:
        log.debug("validate_url: invalid url: %s", _u)
        return False
    return True


def get_optional_params(cfg: dict) -> dict:
    return {k: v for k, v in cfg.items() if k not in COMMON_TEST_PARAMS}


def make_page_load_test(
    name: str, targets: List[str], agents: List[str], cfg: dict, fail: Callable[[str], None] = _fail
) -> SynTest:
    if len(targets) > 1:
        fail(f"{cfg['type']} test accepts only 1 target, {len(targets)} provided ('{targets}')")
    if not validate_url(targets[0]):
        fail(f"Invalid URL: {targets[0]}")
    optional_params = get_optional_params(cfg)
    log.debug("make_page_load_test: optional_params: '%s'", ", ".join(f"{k}:{v}" for k, v in optional_params.items()))
    return PageLoadTest.create(name=name, target=targets[0], agent_ids=agents, **optional_params)


def make_url_test(
    name: str, targets: List[str], agents: List[str], cfg: dict, fail: Callable[[str], None] = _fail
) -> SynTest:
    if len(targets) > 1:
        fail(f"{cfg['type']} test accepts only 1 target, {len(targets)} provided ('{targets}')")
    if not validate_url(targets[0]):
        fail(f"Invalid URL: {targets[0]}")
    optional_params = get_optional_params(cfg)
    log.debug("make_url_test: optional_params: '%s'", ", ".join(f"{k}:{v}" for k, v in optional_params.items()))
    ping = "ping" in cfg
    trace = "trace" in cfg
    return UrlTest.create(name=name, target=targets[0], agent_ids=agents, ping=ping, trace=trace, **optional_params)


def set_common_test_params(test: SynTest, cfg: dict) -> None:
    if "family" in cfg:
        test.settings.family = IPFamily(cfg.get("family"))
        log.debug("set_common_test_params: test: '%s' family: '%s'", test.name, cfg.get("family"))
    if "tasks" in cfg:
        test.settings.tasks = cfg.get("tasks")
        log.debug("set_common_test_params: test: '%s' tasks: '%s'", test.name, cfg.get("tasks"))
    if "protocol" in cfg:
        log.debug("set_common_test_params: test: '%s' protocol: '%s'", test.name, cfg.get("protocol"))
        test.settings.protocol = Protocol(cfg.get("protocol"))
    if "port" in cfg:
        log.debug("set_common_test_params: test: '%s' port: '%s'", test.name, cfg.get("port"))
        test.settings.port = cfg.get("port")
    if "ping" in cfg and type(cfg["ping"]) == dict:
        if "ping" in test.settings.tasks:
            test.settings.ping = PingTask.from_dict(cfg.get("ping"))
            log.debug("set_common_test_params: test: '%s' ping: '%s'", test.name, cfg.get("ping"))
    if "trace" in cfg and type(cfg["trace"]) == dict:
        if "traceroute" in test.settings.tasks:
            log.debug("set_common_test_params: test: '%s' trace: '%s'", test.name, cfg.get("trace"))
            test.settings.trace = TraceTask.from_dict(cfg.get("trace"))
    if "healthSettings" in cfg:
        log.debug("set_common_test_params: test: '%s' healthSettings: '%s'", test.name, cfg.get("healthSettings"))
        test.settings.healthSettings = HealthSettings.from_dict(cfg.get("healthSettings"))
    if "period" in cfg:
        log.debug("set_common_test_params: test: '%s' period: '%s'", test.name, cfg.get("period"))
        test.set_period(cfg["period"])


@dataclass
class TestEntry:
    create: Callable[[str, List[str], List[str], dict], SynTest]
    target_loader: Callable[[APIs, Union[List, Dict], Callable[[str], None]], Set[str]]
    agent_loader: Callable[[APIs, List[Dict], Callable[[str], None]], List[str]]
    requires_targets: bool = True


class TestFactory:
    _MAP: Dict[str, TestEntry] = {
        "network_grid": TestEntry(
            create=make_network_grid_test, target_loader=address_targets, agent_loader=rust_agents
        ),
        "ip": TestEntry(create=make_ip_test, target_loader=address_targets, agent_loader=rust_agents),
        "agent": TestEntry(create=make_agent_test, target_loader=all_agents, agent_loader=rust_agents),
        "dns": TestEntry(create=make_dns_test, target_loader=targets_list, agent_loader=rust_agents),
        "dns_grid": TestEntry(create=make_dns_grid_test, target_loader=targets_list, agent_loader=rust_agents),
        "hostname": TestEntry(create=make_hostname_test, target_loader=targets_list, agent_loader=rust_agents),
        "mesh": TestEntry(
            create=make_mesh_test, target_loader=dummy_loader, agent_loader=rust_agents, requires_targets=False
        ),
        "page_load": TestEntry(create=make_page_load_test, target_loader=targets_list, agent_loader=node_agents),
        "url": TestEntry(create=make_url_test, target_loader=targets_list, agent_loader=rust_agents),
    }

    def create(self, api: APIs, default_name: str, cfg: dict, fail: Callable[[str], None] = _fail) -> SynTest:
        missing = [k for k in ("test", "targets", "agents") if k not in cfg]
        if missing:
            fail("Test configuration is missing mandatory sections: {}".format(", ".join(missing)))
        test_cfg = cfg["test"]
        test_type = test_cfg.get("type", "network_grid")
        entry = self._MAP.get(test_type)
        if not entry:
            fail(f"Unsupported test type: {test_type} (supported types: {self._MAP.keys()})")

        targets = entry.target_loader(api, cfg["targets"], fail)
        if not targets and entry.requires_targets:
            fail("No targets matched test configuration")
        log.debug("TestFactory:create: targets: '%s'", ", ".join(targets))

        agent_ids = entry.agent_loader(api, cfg["agents"])
        if not agent_ids:
            fail("No agents matched configuration")
        log.debug("TestFactory:create: agent_ids: '%s'", ", ".join(agent_ids))

        name = test_cfg.get("name", default_name)
        test = entry.create(name, list(targets), agent_ids, test_cfg)
        set_common_test_params(test, test_cfg)
        return test
