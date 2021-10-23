from typing import List, Optional

import typer

from synth_tools.apis import APIs
from synth_tools.commands.utils import all_matcher_from_rules, get_api, print_agent, print_agent_brief

agents_app = typer.Typer()


@agents_app.command("list")
def list_agents(
    ctx: typer.Context,
    brief: bool = typer.Option(False, help="Print only id, name, alias and type"),
    attributes: Optional[str] = typer.Option(None, help="Config attributes to print"),
) -> None:
    """
    List all agents
    """
    api = get_api(ctx)
    for a in api.syn.agents:
        if brief:
            print_agent_brief(a)
        else:
            typer.echo(f"id: {a['id']}")
            print_agent(a, indent_level=1, attributes=attributes)
            typer.echo("")


@agents_app.command("get")
def get_agent(
    ctx: typer.Context,
    agent_ids: List[str],
    attributes: Optional[str] = typer.Option(None, help="Config attributes to print"),
) -> None:
    """
    Print agent configuration
    """
    api = get_api(ctx)
    for i in agent_ids:
        typer.echo(f"id: {i}")
        a = api.syn.agent(i)
        print_agent(a, indent_level=1, attributes=attributes)
        typer.echo("")


@agents_app.command("match")
def match_agent(
    ctx: typer.Context,
    rules: List[str],
    brief: bool = typer.Option(False, help="Print only id, name and type"),
    attributes: Optional[str] = typer.Option(None, help="Config attributes to print"),
) -> None:
    """
    Print configuration of agents matching specified rules
    """
    api = get_api(ctx)
    matcher = all_matcher_from_rules(rules)
    matching = [a for a in api.syn.agents if matcher.match(a)]
    if not matching:
        typer.echo("No agent matches specified rules")
    else:
        for a in matching:
            if brief:
                print_agent_brief(a)
            else:
                typer.echo(f"id: {a['id']}")
                print_agent(a, indent_level=1, attributes=attributes)
                typer.echo("")


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
        a = api.syn.agent(i)
        if a["status"] != "AGENT_STATUS_WAIT":
            typer.echo(f"id: {i} agent not pending (status: {a['status']})")
        else:
            a["status"] = "AGENT_STATUS_OK"
            del a["name"]
            a = api.syn.patch_agent(i, a, "agent.status")
            if a["status"] != "AGENT_STATUS_OK":
                typer.echo(f"id: {i} FAILED to activate (status: {a['status']}")
            else:
                typer.echo(f"id: {i} agent activated")


@agents_app.command("deactivate")
def deactivate_agent(
    ctx: typer.Context,
    agent_ids: List[str],
) -> None:
    """
    Dectivate an active agent
    """
    api = get_api(ctx)
    for i in agent_ids:
        a = api.syn.agent(i)
        if a["status"] != "AGENT_STATUS_OK":
            typer.echo(f"id: {i} agent is not active (status: {a['status']})")
        else:
            a["status"] = "AGENT_STATUS_WAIT"
            del a["name"]
            a = api.syn.patch_agent(i, a, "agent.status")
            if a["status"] != "AGENT_STATUS_WAIT":
                typer.echo(f"id: {i} FAILED to deactivate (status: {a['status']}")
            else:
                typer.echo(f"id: {i} agent deactivated")


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
        api.syn.delete_agent(i)
        typer.echo(f"Deleted agent: id: {i}")
