from typing import Optional, List

import typer

from synth_tools.apis import APIs
from synth_tools.commands.utils import print_agent_brief, print_agent, all_matcher_from_rules

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
