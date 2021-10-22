import json
import sys
from typing import Optional, List, Dict

import typer

from kentik_synth_client import SynTest
from synth_tools.commands import log
from synth_tools.matchers import AllMatcher


def fail(msg: str) -> None:
    typer.echo(f"FAILED: {msg}", err=True)
    raise typer.Exit(1)


def print_dict(d: dict, indent_level=0, attr_list: Optional[List[str]] = None) -> None:
    indent = "  " * indent_level
    if attr_list is None:
        attr_list = []
    match_attrs = [a.split(".")[0] for a in attr_list]
    for k, v in d.items():
        if match_attrs and k not in match_attrs:
            continue
        typer.echo(f"{indent}{k}: ", nl=False)
        if type(v) == dict:
            typer.echo("")
            print_dict(
                v,
                indent_level + 1,
                attr_list=[a.split(".", maxsplit=1)[1] for a in attr_list if a.startswith(f"{k}.")],
            )
        else:
            typer.echo(f"{v}")


def print_health(
    health: dict,
    raw_out: Optional[str] = None,
    failing_only: bool = False,
    json_out: bool = False,
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


INTERNAL_TEST_SETTINGS = (
    "tasks",
    "monitoringSettings",
    "rollupLevel",
    "ping.period",
    "trace.period",
    "http.period",
)

def print_test(
    test: SynTest,
    indent_level: int = 0,
    show_all: bool = False,
    attributes: Optional[str] = None,
) -> None:
    d = test.to_dict()["test"]
    if not show_all:
        if not test.deployed:
            del d["status"]
        del d["deviceId"]
        for attr in INTERNAL_TEST_SETTINGS:
            keys = attr.split(".")
            item = d["settings"]
            while keys:
                k = keys.pop(0)
                if not keys:
                    try:
                        log.debug(
                            "print_test: deleting k: '%s' item: '%s' attr: '%s'",
                            k,
                            item,
                            attr,
                        )
                        del item[k]
                    except KeyError:
                        log.debug(
                            "print_test: test: '%s' does not have internal attr '%s'",
                            test.name,
                            attr,
                        )
                        break
                else:
                    try:
                        item = item[k]
                        if not item:
                            break
                    except KeyError:
                        log.debug(
                            "print_test: test: '%s' does not have internal attr '%s'",
                            test.name,
                            attr,
                        )
                        break

    if attributes:
        attr_list = attributes.split(",")
    else:
        attr_list = []
    print_dict(d, indent_level=indent_level, attr_list=attr_list)
    typer.echo("")


def print_test_brief(test: SynTest) -> None:
    typer.echo(f"id: {test.id} name: {test.name} type: {test.type.value}")


def print_agent(agent: dict, indent_level=0, attributes: Optional[str] = None) -> None:
    a = agent.copy()
    del a["id"]
    if attributes:
        attr_list = attributes.split(",")
    else:
        attr_list = []
    print_dict(a, indent_level=indent_level, attr_list=attr_list)


def print_agent_brief(agent: dict) -> None:
    typer.echo(f"id: {agent['id']} name: {agent['name']} alias: {agent['alias']} type: {agent['type']}")


def all_matcher_from_rules(rules: List[str]) -> AllMatcher:
    matchers: List[Dict] = []
    for r in rules:
        parts = r.split(":")
        if len(parts) < 2:
            fail(f"Invalid match spec: {r} (must have format: '<property>:<value>')")
        matchers.append({parts[0]: parts[1]})
    return AllMatcher(matchers)
