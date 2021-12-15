import json
from typing import Any, Callable, Dict, List, Optional, Tuple

import inflection
import typer
import yaml

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


def print_test_brief(test: SynTest) -> None:
    typer.echo(f"id: {test.id} name: {test.name} type: {test.type.value}")


def print_test_diff(old: SynTest, new: SynTest, show_all=False):
    o = transform_dict_keys(old.to_dict()["test"], camel_to_snake)
    n = transform_dict_keys(new.to_dict()["test"], camel_to_snake)
    if not show_all:
        del o["status"]
        del n["status"]
        _filter_test_attrs(o, INTERNAL_TEST_SETTINGS + NON_COMPARABLE_TEST_ATTRS)
        _filter_test_attrs(n, INTERNAL_TEST_SETTINGS + NON_COMPARABLE_TEST_ATTRS)
    diffs = dict_compare(o, n)
    if diffs:
        typer.echo("Configuration differences:")
        for d in diffs:
            if not d[1]:
                old_val = "<not in existing>"
            else:
                old_val = d[1]
            if not d[2]:
                new_val = "<not in new>"
            else:
                new_val = d[2]
            typer.echo(f"  {d[0]}: {old_val} -> {new_val}")
    else:
        typer.echo("Existing and new configuration are identical")


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


def print_agent_brief(agent: dict) -> None:
    typer.echo(f"id: {agent['id']} name: {agent['name']} alias: {agent['alias']} type: {agent['type']}")
