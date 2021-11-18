from typing import List, Optional

import typer

from kentik_synth_client import KentikAPIRequestError, KentikSynthClient
from synth_tools.matchers import all_matcher_from_rules
from synth_tools.utils import fail, get_api, print_agent, print_agent_brief

agents_app = typer.Typer()


def _get_agent_by_id(api: KentikSynthClient, agent_id: str) -> dict:
    try:
        return api.agent(agent_id)
    except KentikAPIRequestError as exc:
        if exc.response.status_code == 404:
            fail(f"Agent with id '{agent_id}' does not exist")
        else:
            fail(f"{exc}")
    return {}  # never reached, because fail function (or other exception) terminates the app


@agents_app.command("list")
def list_agents(
    ctx: typer.Context,
    brief: bool = typer.Option(False, "-b", "--brief", help="Print only id, name, alias and type"),
    fields: Optional[str] = typer.Option(None, "-f", "--fields", help="Config attributes to print"),
) -> None:
    """
    List all agents
    """
    api = get_api(ctx)
    try:
        for a in api.syn.agents:
            if brief:
                print_agent_brief(a)
            else:
                if fields == "id":
                    typer.echo(a["id"])
                else:
                    typer.echo(f"id: {a['id']}")
                    print_agent(a, indent_level=1, attributes=fields)
    except KentikAPIRequestError as exc:
        fail(f"{exc}")


@agents_app.command("get")
def get_agent(
    ctx: typer.Context,
    agent_ids: List[str],
    fields: Optional[str] = typer.Option(None, "-f", "--fields", help="Config attributes to print"),
) -> None:
    """
    Print agent configuration
    """
    api = get_api(ctx)
    for i in agent_ids:
        a = _get_agent_by_id(api.syn, i)
        typer.echo(f"id: {i}")
        print_agent(a, indent_level=1, attributes=fields)


@agents_app.command("match")
def match_agent(
    ctx: typer.Context,
    rules: List[str],
    brief: bool = typer.Option(False, "-b", "--brief", help="Print only id, name and type"),
    fields: Optional[str] = typer.Option(None, "-f", "--fields", help="Config attributes to print"),
) -> None:
    """
    Print configuration of agents matching specified rules
    """
    api = get_api(ctx)
    matcher = all_matcher_from_rules(rules)
    try:
        matching = [a for a in api.syn.agents if matcher.match(a)]
        if not matching:
            typer.echo("No agent matches specified rules")
        else:
            for a in matching:
                if brief:
                    print_agent_brief(a)
                else:
                    if fields == "id":
                        typer.echo(a["id"])
                    else:
                        typer.echo(f"id: {a['id']}")
                        print_agent(a, indent_level=1, attributes=fields)
    except KentikAPIRequestError as exc:
        fail(f"{exc}")


@agents_app.command("activate")
def activate_agent(
    ctx: typer.Context,
    agent_ids: List[str],
) -> None:
    """
    Activate pending agent
    """
    api = get_api(ctx)
    for i in agent_ids:
        a = _get_agent_by_id(api.syn, i)
        if a["status"] != "AGENT_STATUS_WAIT":
            typer.echo(f"id: {i} agent not pending (status: {a['status']})")
            continue
        a["status"] = "AGENT_STATUS_OK"
        del a["name"]
        try:
            a = api.syn.patch_agent(i, a, "agent.status")
            if a["status"] != "AGENT_STATUS_OK":
                typer.echo(f"id: {i} FAILED to activate (status: {a['status']}")
            else:
                typer.echo(f"id: {i} agent activated")
        except KentikAPIRequestError as exc:
            fail(f"{exc}")


@agents_app.command("deactivate")
def deactivate_agent(
    ctx: typer.Context,
    agent_ids: List[str],
) -> None:
    """
    Deactivate an active agent
    """
    api = get_api(ctx)
    for i in agent_ids:
        a = _get_agent_by_id(api.syn, i)
        if a["status"] != "AGENT_STATUS_OK":
            typer.echo(f"id: {i} agent is not active (status: {a['status']})")
            continue
        a["status"] = "AGENT_STATUS_WAIT"
        del a["name"]
        try:
            a = api.syn.patch_agent(i, a, "agent.status")
            if a["status"] != "AGENT_STATUS_WAIT":
                typer.echo(f"id: {i} FAILED to deactivate (status: {a['status']}")
            else:
                typer.echo(f"id: {i} agent deactivated")
        except KentikAPIRequestError as exc:
            fail(f"{exc}")


@agents_app.command("delete")
def delete_agent(
    ctx: typer.Context,
    agent_ids: List[str],
) -> None:
    """
    Delete an agent
    """
    api = get_api(ctx)
    for i in agent_ids:
        try:
            api.syn.delete_agent(i)
            typer.echo(f"Deleted agent: id: {i}")
        except KentikAPIRequestError as exc:
            if exc.response.status_code == 404:
                fail(f"Agent with id '{i}' not found")
            else:
                fail(f"{exc}")
