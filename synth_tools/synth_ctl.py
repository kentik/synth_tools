#!/usr/bin/python3
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import List, Optional

import typer

# noinspection Mypy
from kentik_api import KentikAPI

from kentik_synth_client import KentikSynthClient, SynTest, TestStatus
from synth_tools.core import APIs, load_test, run_one_shot

app = typer.Typer()
tests_app = typer.Typer()
app.add_typer(tests_app, name="test")
agents_app = typer.Typer()
app.add_typer(agents_app, name="agent")

api = Optional[APIs]

logging.basicConfig(level=logging.INFO)
log = logging.getLogger()


def fail(msg: str) -> None:
    typer.echo(f"FAILED: {msg}", err=True)
    raise typer.Exit(1)


def print_dict(d: dict, indent_level=0) -> None:
    indent = "  " * indent_level
    for k, v in d.items():
        typer.echo(f"{indent}{k}: ", nl=False)
        if type(v) == dict:
            typer.echo("")
            print_dict(v, indent_level + 1)
        else:
            typer.echo(f"{v}")


def print_health(
    health: dict, raw_out: Optional[str] = None, failing_only: bool = False, json_out: bool = False
) -> None:
    if not health:
        log.warning("No valid health data")
        return

    if raw_out:
        log.info("Writing health data to '%s'", raw_out)
        with open(raw_out, "w") as f:
            json.dump(health, f, indent=2)

    results_by_target = defaultdict(list)
    for task in health["tasks"]:
        for agent in task["agents"]:
            for h in agent["health"]:
                if failing_only and h["overallHealth"]["health"] != "failing":
                    continue
                for task_type in ("ping", "knock", "shake", "dns", "http"):
                    if task_type in task["task"]:
                        target = task["task"][task_type]["target"]
                        break
                else:
                    target = h["dstIp"]
                    task_type = h["taskType"]
                e = dict(
                    time=h["overallHealth"]["time"],
                    agent_id=agent["agent"]["id"],
                    agent_addr=agent["agent"]["ip"],
                    task_type=task_type,
                    loss=f"{h['packetLoss'] * 100}% ({h['packetLossHealth']})",
                    latency=f"{h['avgLatency']/1000}ms ({h['latencyHealth']})",
                    jitter=f"{h['avgJitter']/1000}ms ({h['jitterHealth']})",
                )
                for field in ("data", "status", "size"):
                    if field in h:
                        e[field] = h[field]
                results_by_target[target].append(e)
                if "data" in e:
                    e["data"] = json.loads(e["data"])
    if json_out:
        json.dump(results_by_target, sys.stdout, indent=2)
    else:
        for t, data in results_by_target.items():
            typer.echo(f"target: {t}")
            for e in sorted(data, key=lambda x: x["time"]):
                typer.echo("  {}".format(", ".join(f"{k}: {v}" for k, v in e.items())))


def print_test(test: SynTest, indent_level=0) -> None:
    d = test.to_dict()["test"]
    if not test.deployed:
        del d["status"]
    print_dict(d, indent_level=indent_level)
    typer.echo("")


def print_agent(agent: dict, indent_level=0) -> None:
    a = agent.copy()
    del a["id"]
    print_dict(a, indent_level=indent_level)


@tests_app.command()
def one_shot(
    test_config: Path = typer.Argument(..., help="Path to test config file"),
    wait_factor: float = typer.Option(1.0, help="Multiplier for test period for computing wait time for test results"),
    retries: int = typer.Option(3, help="Number retries waiting for test results"),
    raw_out: str = typer.Option("", help="Path to file to store raw test results in JSON format"),
    failing: bool = typer.Option(False, help="Print only failing results"),
    delete: bool = typer.Option(True, help="Delete test after retrieving results"),
    print_config: bool = typer.Option(False, help="Print complete test configuration"),
    json_out: bool = typer.Option(False, "--json", help="Print output in JSON format"),
) -> None:
    test = load_test(api, test_config, fail)
    if print_config:
        print_test(test)
    health = run_one_shot(api, test, wait_factor=wait_factor, retries=retries, delete=delete)

    if not health:
        fail("Test did not produce any health data")

    print_health(health, raw_out=raw_out, failing_only=failing, json_out=json_out)


@tests_app.command("create")
def create_test(
    test_config: Path = typer.Argument(..., help="Path to test config file"),
    dry_run: bool = typer.Option(False, help="Only construct and print test data"),
) -> None:
    test = load_test(api, test_config, fail)
    if dry_run:
        print_test(test)
    else:
        test = api.syn.create_test(test)
        typer.echo(f"Created new test: id {test.id}")
        print_test(test)


@tests_app.command("delete")
def delete_test(test_id: str = typer.Argument(..., help="ID of the test to delete")) -> None:
    api.syn.delete_test(test_id)
    typer.echo(f"Deleted test: id: {test_id}")


@tests_app.command("list")
def list_tests(brief: bool = typer.Option(False, help="Print only id, name and type")) -> None:
    for t in api.syn.tests:
        if brief:
            typer.echo(f"id: {t.id} name: {t.name} type: {t.type.value}")
        else:
            typer.echo(f"id: {t.id}")
            print_test(t, indent_level=1)


@tests_app.command("get")
def get_test(test_ids: List[str]) -> None:
    for i in test_ids:
        t = api.syn.test(i)
        print_test(t)


@tests_app.command("pause")
def pause_test(test_id: str) -> None:
    api.syn.set_test_status(test_id, TestStatus.paused)
    typer.echo(f"test id: {test_id} has been paused")


@tests_app.command("resume")
def resume_test(test_id: str) -> None:
    api.syn.set_test_status(test_id, TestStatus.active)
    typer.echo(f"test id: {test_id} has been resumed")


@tests_app.command("results")
def get_test_health(
    test_id: str,
    raw_out: str = typer.Option("", help="Path to file to store raw test results in JSON format"),
    json_out: bool = typer.Option(False, "--json", help="Print output in JSON format"),
    failing: bool = typer.Option(False, help="Print only failing results"),
    periods: int = typer.Option(3, help="Number of test periods to request"),
) -> None:
    t = api.syn.test(test_id)
    health = api.syn.results(t, periods=periods)

    if not health:
        fail(f"Test '{test_id}' did not produce any health data")

    print_health(health[0], raw_out=raw_out, failing_only=failing, json_out=json_out)


@agents_app.command("list")
def list_agents() -> None:
    for a in api.syn.agents:
        typer.echo(f"id: {a['id']}")
        print_agent(a, indent_level=1)
        typer.echo("")


@agents_app.command("get")
def get_agent(agent_ids: List[str]) -> None:
    for i in agent_ids:
        typer.echo(f"id: {i}")
        a = api.syn.agent(i)
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
    Tool for manipulating Kentik synthetic tests
    """
    global api

    if debug:
        log.setLevel(logging.DEBUG)
        log.debug("Debug output enabled")
    if proxy:
        log.debug("Using proxy: %s", proxy)
    log.debug("Monitoring credential profile: %s", profile)
    if target_profile is None:
        target_profile = profile

    api = APIs(mgmt_profile=target_profile, syn_profile=profile, proxy=proxy)


if __name__ == "__main__":
    app()
