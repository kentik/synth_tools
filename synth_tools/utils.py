import json
import os
from typing import Any, Callable, Dict, List, Optional, Tuple

import inflection
import typer
import yaml
from texttable import Texttable

from kentik_synth_client import KentikAPIRequestError
from kentik_synth_client.synth_tests import SynTest
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


def transform_dict_keys(d: Dict[str, Any], fn: Callable[[str], str]) -> Dict[str, Any]:
    out: Dict[str, Any] = dict()
    for k, v in d.items():
        if type(v) == dict:
            out[fn(k)] = transform_dict_keys(v, fn)
        elif type(v) == list:
            out_value = []
            for e in v:
                if type(e) == dict:
                    out_value.append(transform_dict_keys(e, fn))
                else:
                    out_value.append(e)
            out[fn(k)] = out_value
        else:
            out[fn(k)] = v
    return out


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
    d = transform_dict_keys(test.to_dict()["test"], camel_to_snake)
    d["id"] = test.id
    d["created"] = test.cdate
    d["modified"] = test.edate
    d["created_by"] = test.created_by
    d["last_updated_by"] = test.last_updated_by
    return d


NON_COMPARABLE_TEST_ATTRS = [
    "created",
    "modified",
    "created_by",
]


INTERNAL_TEST_SETTINGS = [
    "tasks",
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
                        "print_test: test: '%s' does not have internal attr '%s'",
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
                        t["name"],
                        attr,
                    )
                    break


def print_test(
    test: SynTest,
    indent_level: int = 0,
    show_all: bool = False,
    attributes: Optional[str] = None,
) -> None:
    d = test_to_dict(test)
    if not show_all:
        if not test.deployed:
            del d["status"]
        _filter_test_attrs(d, INTERNAL_TEST_SETTINGS)
    if attributes:
        attr_list = attributes.split(",")
    else:
        attr_list = []
    print_struct(filter_dict(d, attr_list), indent_level=indent_level)


def print_tests_brief(tests: List[SynTest]) -> None:
    # typer.echo(f"id: {test.id} name: {test.name} type: {test.type.value}")
    table = Texttable(max_width=os.get_terminal_size()[0])
    for t in tests:
        table.add_row([f"{x[0]}: {x[1]}" for x in (("id", t.id), ("name", t.name), ("type", t.type.value))])
    table.set_deco(Texttable.HEADER | Texttable.VLINES)
    typer.echo(table.draw())


def print_test_diff(first: SynTest, second: SynTest, show_all=False, labels: Tuple[str, str] = ("FIRST", "SECOND")):
    o = transform_dict_keys(first.to_dict()["test"], camel_to_snake)
    n = transform_dict_keys(second.to_dict()["test"], camel_to_snake)
    if not show_all:
        del o["status"]
        del n["status"]
        _filter_test_attrs(o, INTERNAL_TEST_SETTINGS + NON_COMPARABLE_TEST_ATTRS)
        _filter_test_attrs(n, INTERNAL_TEST_SETTINGS + NON_COMPARABLE_TEST_ATTRS)
    diffs = dict_compare(o, n)
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
    print_struct(transform_dict_keys(results, camel_to_snake))


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
