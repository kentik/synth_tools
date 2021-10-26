from typing import List, Optional

import typer

from kentik_synth_client import KentikAPIRequestError
from synth_tools.apis import APIs
from synth_tools.commands.utils import all_matcher_from_rules, fail, get_api, print_agent, print_agent_brief

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
        try:
            a = api.syn.agent(i)
        except KentikAPIRequestError as e:
            if e.response.status_code == 404:
                fail(f"Agent {i} does not exist")
            else:
                fail(f"Got unexpected response from API:\n{e}")

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
