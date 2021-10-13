#!/usr/bin/python3
import json
import logging
import random
import string
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
from pathlib import Path
from time import sleep
from typing import Callable, List, Set

import typer
import yaml

# noinspection Mypy
from kentik_api import KentikAPI
from kentik_api.public import Device, Interface

# noinspection Mypy
from kentik_api.utils import get_credentials

from kentik_synth_client import *
from synth_tools.matchers import *

app = typer.Typer()

api: Optional[KentikAPI] = None
syn_api: Optional[KentikSynthClient] = None


def random_string(str_size, allowed_chars=string.ascii_letters + string.digits):
    return "".join(random.choice(allowed_chars) for _ in range(str_size))


logging.basicConfig(level=logging.INFO)
log = logging.getLogger()


def fail(msg: str) -> None:
    typer.echo(f"FAILED: {msg}", err=True)
    raise typer.Exit(1)


def run_one_shot(test: SynTest, wait_factor: float = 1.0, retries: int = 3, delete: bool = True) -> Optional[dict]:
    def _delete_test(tst: SynTest):
        log.debug("Deleting test '%s' (id: %s)", tst.name, tst.id)
        try:
            syn_api.delete_test(tst.id)
            log.info("Deleted test %s' (id: %s)", tst.name, tst.id)
        except KentikAPIRequestError as ex:
            log.error("Failed to delete test '%s' (id: %s) (%s)", tst.name, tst.id, ex)

    log.debug("creating test '%s'", test.name)
    try:
        t = syn_api.create_test(test)
    except KentikAPIRequestError as ex:
        log.error("Failed to create test '%s' (%s)", test.name, ex)
        return None
    log.info("Created test '%s' (id: %s)", t.name, t.id)
    if t.status != TestStatus.active:
        log.info("Activating test '%s'", t.name)
        try:
            syn_api.set_test_status(t.id, TestStatus.active)
        except KentikAPIRequestError as ex:
            log.error("Failed to activate test '%s' (id: %s) (%s)", t.name, t.id, ex)
            _delete_test(t)
            return None

    wait_time = max(0.0, t.max_period * wait_factor - (datetime.now(tz=timezone.utc) - t.edate).total_seconds())
    start = datetime.now(tz=timezone.utc)
    while retries:
        if wait_time > 0:
            log.info("Waiting for %s seconds for test to accumulate results", wait_time)
            sleep(wait_time)
        wait_time = t.max_period
        now = datetime.now(tz=timezone.utc)
        try:
            health = syn_api.health([t.id], start=now - timedelta(seconds=t.max_period * wait_factor), end=now)
        except KentikAPIRequestError as ex:
            log.error("Failed to retrieve test health (%s). Retrying ...", ex)
            retries -= 1
            continue
        if len(health) < 1:
            log.debug("Health not available after %f seconds", (now - start).total_seconds())
            retries -= 1
            continue
        health_ts = datetime.fromisoformat(health[0]["overallHealth"]["time"].replace("Z", "+00:00"))
        if (health_ts - now).total_seconds() > t.max_period * wait_factor:
            log.info(
                "Stale health data after %f second (timestamp: %s)",
                (now - start).total_seconds(),
                health_ts.isoformat(),
            )
            retries -= 1
            continue
        log.debug("Test '%s' is %s at %s", t.id, health[0]["overallHealth"]["health"], health_ts.isoformat())
        break
    else:
        log.fatal("Failed to get valid health data for test id: %s", t.id)
        health = None

    if delete:
        _delete_test(t)
    else:
        log.info("Pausing test id: %s", t.id)
        syn_api.set_test_status(t.id, TestStatus.paused)

    return health[0] if health else None


def print_health(health: dict, failing_only: bool = False) -> None:
    if not health:
        log.warning("No valid health data")
    results_by_target = defaultdict(list)
    for task in health["tasks"]:
        for agent in task["agents"]:
            for h in agent["health"]:
                if failing_only and h["overallHealth"]["health"] != "failing":
                    continue
                results_by_target[task["task"]["ping"]["target"]].append(
                    dict(
                        time=h["overallHealth"]["time"],
                        agent_id=agent["agent"]["id"],
                        agent_addr=agent["agent"]["ip"],
                        loss=f"{h['packetLoss'] * 100}% ({h['packetLossHealth']})",
                        latency=f"{h['avgLatency']/1000}ms ({h['latencyHealth']})",
                        jitter=f"{h['avgJitter']/1000}ms ({h['jitterHealth']})",
                    )
                )
    for t, data in results_by_target.items():
        typer.echo(f"target: {t}")
        for e in sorted(data, key=lambda x: x["time"]):
            typer.echo("\t {}".format(", ".join(f"{k}: {v}" for k, v in e.items())))


def print_dict(d: dict, indent_level=0) -> None:
    indent = "  " * indent_level
    for k, v in d.items():
        typer.echo(f"{indent}{k}: ", nl=False)
        if type(v) == dict:
            typer.echo("")
            print_dict(v, indent_level + 1)
        else:
            typer.echo(f"{v}")


def print_test(test: SynTest, indent_level=0) -> None:
    data = test.to_dict()["test"]
    if not test.deployed:
        del data["status"]
    print_dict(data, indent_level=indent_level)


def print_agent(agent: dict, indent_level=0) -> None:
    a = agent.copy()
    del a["id"]
    print_dict(a, indent_level=indent_level)


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


def load_targets(cfg: dict) -> Set[str]:
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
    for d in api.devices.get_all():
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
            for i in api.devices.interfaces.get_all(d.id):
                if interface_matcher.match(i):
                    for func in interface_address_extractors:
                        for a in func(i):
                            targets.add(a)
    return targets


def load_test(file: Path) -> SynTest:
    test_type_to_class = {"network_grid": NetworkGridTest}

    if file.exists():
        if not file.is_file():
            fail(f"Test configuration '{file.as_posix()}' is not a file")
    else:
        fail(f"Test configuration file '{file.as_posix()}' does not exist")
    log.info("Loading test configuration from '%s'", file.as_posix())
    cfg = dict()
    with file.open() as f:
        cfg = yaml.safe_load(f)
    if not cfg:
        fail("No test config, no fun")
    test_type = cfg.get("type", "grid")
    test_class = test_type_to_class.get(test_type)
    if not test_class:
        fail(f"Test type '{test_type}' is not supported")
    log.debug("load_test: type: '%s' class: '%s'", test_type, test_class.__class__)
    missing = [k for k in ("targets", "agents") if k not in cfg]
    if missing:
        fail("Test configuration is missing mandatory sections: {}".format(", ".join(missing)))
    targets_cfg = cfg["targets"]
    if type(targets_cfg) == list:
        targets = targets_cfg
    else:
        targets = load_targets(targets_cfg)
    log.debug("load_test: targets: '%s'", ", ".join(targets))
    if not targets:
        fail("No targets matched test configuration")

    agents_matcher = AllMatcher(cfg["agents"])
    agent_ids = [a["id"] for a in syn_api.agents if agents_matcher.match(a)]
    if not agent_ids:
        fail("No agents matched configuration")
    log.debug("load_test: agent_ids: '%s'", ", ".join(agent_ids))
    now = datetime.now(tz=timezone.utc).replace(second=0, microsecond=0).isoformat()
    test = test_class.create(
        name=cfg.get("name", f"__auto__{file.stem}_{now}"),
        targets=list(targets),
        agent_ids=agent_ids,
    )
    if "period" in cfg:
        test.set_period(cfg["period"])
    log.debug("loaded '%s' test, params: '%s'", test_type, ", ".join(f"{k}:{v}" for k, v in test.to_dict().items()))
    return test


@app.command()
def one_shot(
    test_config: Path = typer.Argument(..., help="Path to test config file"),
    wait_factor: float = typer.Option(1.0, help="Multiplier for test period for computing wait time for test results"),
    retries: int = typer.Option(3, help="Number retries waiting for test results"),
    json_out: str = typer.Option("", help="Path to file to store test results in JSON format"),
    failing_only: bool = typer.Option(False, help="Print only failing results to stdout"),
    delete: bool = typer.Option(True, help="Delete test after retrieving results"),
    print_config: bool = typer.Option(False, help="Print complete test configuration")
) -> None:
    test = load_test(test_config)
    if print_config:
        print_test(test)
    health = run_one_shot(test, wait_factor=wait_factor, retries=retries, delete=delete)

    if not health:
        fail("Test did not produce any health data")

    if json_out:
        log.info("Writing health data to '%s'", json_out)
        with open(json_out, "w") as f:
            json.dump(health, f, indent=2)

    print_health(health, failing_only)


@app.command("create")
def create_test(test_config: Path = typer.Argument(..., help="Path to test config file"),
                dry_run: bool = typer.Option(False, help="Only construct and print test data")) -> None:
    test = load_test(test_config)
    if dry_run:
        print_test(test)
    else:
        test = syn_api.create_test(test)
        typer.echo(f"Created new test: id {test.id}")
        print_test(test)


@app.command("delete")
def delete_test(test_id: str = typer.Argument(..., help="ID of the test to delete")) -> None:
    syn_api.delete_test(test_id)
    typer.echo(f"Deleted test: id: {test_id}")


@app.command("list")
def list_tests() -> None:
    for t in syn_api.tests:
        typer.echo(f"id: {t.id}")
        print_test(t, indent_level=1)
        typer.echo("")


@app.command("get")
def get_test(test_id: str) -> None:
    t = syn_api.test(test_id)
    print_test(t)


@app.command("pause")
def pause_test(test_id: str) -> None:
    syn_api.set_test_status(test_id, TestStatus.paused)
    typer.echo(f"test id: {test_id} has been paused")


@app.command("resume")
def pause_test(test_id: str) -> None:
    syn_api.set_test_status(test_id, TestStatus.active)
    typer.echo(f"test id: {test_id} has been resumed")


@app.command("agents")
def list_agents() -> None:
    for a in syn_api.agents:
        typer.echo(f"id: {a['id']}")
        print_agent(a, indent_level=1)
        typer.echo("")


@app.command("get-agent")
def get_agent(agent_ids: List[str]) -> None:
    for i in agent_ids:
        typer.echo(f"id: {i}")
        a = syn_api.agent(i)
        print_agent(a, indent_level=1)
        typer.echo("")


@app.callback()
def main(
    profile: str = typer.Option(..., help="Credential profile for the monitoring account"),
    target_profile: Optional[str] = typer.Option(
        None, help="Credential profile for the target account (default: same as profile)"
    ),
    debug: bool = typer.Option(False, "-d", "--debug", help="Debug output"),
    proxy: Optional[str] = typer.Option(None, "--proxy", help="Proxy to use to connect to Kentik API"),
) -> None:
    """
    Tool for creating Kentik synthetic tests
    """
    global api
    global syn_api

    if debug:
        log.setLevel(logging.DEBUG)
        log.debug("Debug output enabled")
    if proxy:
        log.debug("Using proxy: %s", proxy)
    log.debug("Monitoring credential profile: %s", profile)
    if target_profile is None:
        target_profile = profile

    api = KentikAPI(*get_credentials(target_profile), proxy=proxy)
    syn_api = KentikSynthClient(get_credentials(profile), proxy=proxy)
    log.debug("api: %s", api)
    log.debug("syn_api: %s", syn_api)


if __name__ == "__main__":
    app()
