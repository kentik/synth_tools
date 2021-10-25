from typing import List, Optional

import typer

from kentik_synth_client import KentikAPIRequestError
from synth_tools.apis import APIs
from synth_tools.commands.utils import all_matcher_from_rules, print_agent, print_agent_brief

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
    api = ctx.find_object(APIs)
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
    api = ctx.find_object(APIs)
    for i in agent_ids:
        try:
            a = api.syn.agent(i)
        except KentikAPIRequestError as e:
            if e.response.status_code == 404:
                typer.echo(f"Agent {i} does not exists")
            else:
                typer.echo(f"Got unexpected response from API:\n{e.response.text}")
            continue

        typer.echo(f"id: {i}")
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
    api = ctx.find_object(APIs)
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
