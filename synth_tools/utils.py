import json
import os
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple

import inflection
import typer
import yaml
from texttable import Texttable

from kentik_synth_client import KentikAPIRequestError
from kentik_synth_client.synth_tests import FlowTestSubType, SynTest, TestType
from kentik_synth_client.utils import dict_compare
from synth_tools import log
from synth_tools.apis import APIs


def sort_id(id_str: str) -> str:
    try:
        d = int(id_str)
        return f"{d:010}"
    except ValueError:
        return id_str


def camel_to_snake(name: str) -> str:
    if "-" in name:
        return "-".join(inflection.underscore(s) for s in name.split("-"))
    else:
        return inflection.underscore(name)


def snake_to_camel(name: str) -> str:
    return inflection.camelize(name, False)


def transform_dict_keys(data: Any, fn: Callable[[str], str]) -> Any:
    if type(data) == dict:
        return {fn(k): transform_dict_keys(v, fn) for k, v in data.items()}
    elif type(data) == list:
        return [transform_dict_keys(e, fn) for e in data]
    else:
        return data


def fail(msg: str) -> None:
    typer.echo(f"FAILED: {msg}", err=True)
    raise typer.Exit(1)


def get_api(ctx: typer.Context) -> APIs:
    api = ctx.find_object(APIs)
    if not api:
        raise RuntimeError("Cannot find APIs in context")
    return api


def api_request(req: Callable, name: str, *args, **kwargs) -> Any:
    try:
        return req(*args, **kwargs)
    except KentikAPIRequestError as exc:
        fail(f"API {name} request failed - {exc}")


def filter_dict(data: dict, attr_list: Optional[List[str]] = None) -> Dict[str, Any]:
    out: Dict[str, Any] = dict()
    if attr_list is None:
        attr_list = []
    match_attrs = [a.split(".")[0] for a in attr_list]
    for _k, v in data.items():
        k = camel_to_snake(_k)
        if match_attrs and k not in match_attrs:
            continue
        if type(v) == dict:
            out[k] = filter_dict(v, attr_list=[a.split(".", maxsplit=1)[1] for a in attr_list if a.startswith(f"{k}.")])
        else:
            out[k] = v
    return out


def print_struct(data: Any, indent_level=0):
    indent = "  " * indent_level
    s = yaml.dump(data, default_flow_style=False, sort_keys=False)
    for line in s.split("\n"):
        typer.echo(f"{indent}{line}")


def dict_to_json(filename: str, data: Dict[str, Any]) -> None:
    try:
        with open(filename, "w") as f:
            json.dump(data, f, indent=2)
    except OSError as ex:
        fail(f"Cannot write to file '{filename}' ({ex})")


def test_to_dict(test: SynTest) -> Dict[str, Any]:
    d: Dict[str, Any] = dict(id=test.id)
    d.update(transform_dict_keys(test.to_dict()["test"], camel_to_snake))
    d["created"] = test.created
    d["modified"] = test.modified
    d["created_by"] = test.created_by
    d["last_updated_by"] = test.last_updated_by
    return d


NON_COMPARABLE_TEST_ATTRS = [
    "created",
    "modified",
    "created_by",
]


def _filter_test_attrs(t: dict, attrs: List[str]) -> None:
    for attr in attrs:
        keys = attr.split(".")
        item = t["settings"]
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
                        "print_test: test does not have internal attr '%s'",
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
                        "print_test: test does not have internal attr '%s'",
                        attr,
                    )
                    break


def print_test(
    test: SynTest,
    indent_level: int = 0,
    attributes: Optional[str] = None,
    json_format=False,
) -> None:
    d = test_to_dict(test)
    if not test.deployed:
        del d["status"]
    if attributes:
        attr_list = attributes.split(",")
    else:
        attr_list = []
    if json_format:
        json.dump(filter_dict(d, attr_list), sys.stdout, default=str, indent=2)
    else:
        print_struct(filter_dict(d, attr_list), indent_level=indent_level)


def print_test_config(
    test: SynTest,
) -> None:
    cfg: Dict[str, Any] = dict(test=dict(), agents=dict())
    cfg["test"]["name"] = test.name
    cfg["test"]["type"] = test.type.value
    settings = transform_dict_keys(test.settings.to_dict(), camel_to_snake)
    test_settings = settings.get(test.type.value)
    if test_settings:
        for attr in ["target", "targets", "type"]:
            if attr in test_settings:
                del test_settings[attr]
        cfg["test"].update(test_settings)
        if test.type == TestType.flow:
            target_type = test_settings.get("type", FlowTestSubType.asn.value)
            if target_type:
                cfg["test"]["target_type"] = target_type

    to_delete = ["notification_channels", "tasks", "agent_ids", test.type.value]
    to_delete.extend([_t for _t in ("ping", "trace") if _t in settings and _t not in test.configured_tasks])
    for attr in to_delete:
        if attr in settings:
            del settings[attr]
    cfg["test"].update(settings)
    cfg["agents"]["use"] = test.settings.agentIds
    targets = test.targets
    if targets:
        cfg["targets"] = dict(use=targets)
    typer.echo(f"# id: {test.id}")
    yaml.dump(cfg, sys.stdout, default_flow_style=False, sort_keys=False)


def print_tests(tests: List[SynTest], attributes: Optional[str] = None, json_format=False) -> None:
    if json_format:
        if attributes:
            attr_list = attributes.split(",")
        else:
            attr_list = []
        out: List[Any] = []
        for t in sorted(tests, key=lambda x: sort_id(x.id)):
            if attributes == "id":
                out.append(t.id)
            else:
                d = test_to_dict(t)
                if not t.deployed:
                    del d["status"]
                out.append(filter_dict(d, attr_list))
        json.dump(out, sys.stdout, default=str, indent=2)
        typer.echo()
    else:
        print_id = len(tests) > 1 and (not attributes or "id" not in attributes.split(","))
        for t in sorted(tests, key=lambda x: sort_id(x.id)):
            if attributes == "id":
                typer.echo(t.id)
            else:
                if print_id:
                    typer.echo(f"id: {t.id}")
                print_test(t, indent_level=1, attributes=attributes)


def print_tests_brief(tests: List[SynTest]) -> None:
    table = Texttable(max_width=os.get_terminal_size()[0])
    for t in sorted(tests, key=lambda x: sort_id(x.id)):
        table.add_row([f"{x[0]}: {x[1]}" for x in (("id", t.id), ("name", t.name), ("type", t.type.value))])
    table.set_deco(Texttable.HEADER | Texttable.VLINES)
    typer.echo(table.draw())


def _remove_unused_test_settings(test: dict):
    for task, cfg in (("ping", "ping"), ("traceroute", "trace")):
        if task not in test["settings"]["tasks"] and cfg in test["settings"]:
            del test["settings"][cfg]


def print_test_diff(first: SynTest, second: SynTest, labels: Tuple[str, str] = ("FIRST", "SECOND")):
    f = transform_dict_keys(first.to_dict()["test"], camel_to_snake)
    s = transform_dict_keys(second.to_dict()["test"], camel_to_snake)
    del f["status"]
    del s["status"]
    _remove_unused_test_settings(f)
    _remove_unused_test_settings(s)
    _filter_test_attrs(f, NON_COMPARABLE_TEST_ATTRS)
    _filter_test_attrs(s, NON_COMPARABLE_TEST_ATTRS)
    diffs = dict_compare(f, s)
    if diffs:
        table = Texttable(max_width=os.get_terminal_size()[0])
        table.add_rows([["Attribute", f"{labels[0]}", f"{labels[1]}"]], header=True)
        table.add_rows(rows=[[d[0], d[1], d[2]] for d in diffs], header=False)
        typer.echo(f"Configuration differences:")
        table.set_deco(Texttable.HEADER | Texttable.VLINES)
        typer.echo(table.draw())
    else:
        typer.echo(f"Configurations of {labels[0]} and {labels[1]} are identical")
        raise typer.Exit(0)


def print_test_results(results: Dict[str, Any]):
    print_struct(results)


def agent_to_dict(agent: dict) -> Dict[str, Any]:
    return transform_dict_keys(agent, camel_to_snake)


def print_agent(agent: dict, indent_level=0, attributes: Optional[str] = None) -> None:
    a = agent.copy()
    del a["id"]
    if attributes:
        attr_list = attributes.split(",")
    else:
        attr_list = []
    print_struct(filter_dict(a, attr_list), indent_level=indent_level)


def print_agents_brief(agents: List[Dict[str, Any]]) -> None:
    table = Texttable(max_width=os.get_terminal_size()[0])
    for agent in agents:
        a = agent_to_dict(agent)
        table.add_row(
            [
                f"{k}: {v}"
                for k, v in (
                    ("id", a["id"]),
                    ("site_name", a["site_name"]),
                    ("alias", a["alias"]),
                    ("type", a["type"]),
                    ("nr_tests", len(a["test_ids"])),
                )
            ]
        )
    table.set_deco(Texttable.HEADER | Texttable.VLINES)
    typer.echo(table.draw())
