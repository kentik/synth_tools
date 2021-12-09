import json
from typing import Any, Callable, Dict, List, Optional

import inflection
import typer
import yaml

from kentik_synth_client import SynTest
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


INTERNAL_TEST_SETTINGS = (
    "tasks",
    "monitoringSettings",
    "rollupLevel",
    "ping.period",
    "trace.period",
    "http.period",
)


def test_to_dict(test: SynTest) -> Dict[str, Any]:
    d = test.to_dict()["test"]
    d["id"] = test.id
    d["created"] = test.cdate
    d["modified"] = test.edate
    if test.created_by:
        d["created_by"] = test.created_by
    return d


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
    print_struct(filter_dict(d, attr_list), indent_level=indent_level)


def print_test_brief(test: SynTest) -> None:
    typer.echo(f"id: {test.id} name: {test.name} type: {test.type.value}")


def print_test_results(results: Dict[str, Any]):
    print_struct(transform_dict_keys(results, camel_to_snake))


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
