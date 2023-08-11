import json
from typing import List, Optional

import typer

from kentik_synth_client import KentikAPIRequestError, KentikSynthClient
from synth_tools.matchers import all_matcher_from_rules
from synth_tools.utils import agent_to_dict, api_request, fail, get_api, print_agent, print_agents_brief, sort_id

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


def _get_agents_by_alias(api: KentikSynthClient, agent_alias: str) -> List[dict]:
    try:
        matches = []
        agents = api.agents
        for a in agents:
            if a["alias"] == agent_alias:
                matches.append(a)
        return matches
    except KentikAPIRequestError as exc:
        fail(f"{exc}")
    return []


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
    agents = api_request(api.syn.list_agents, "AgentsList")
    if brief:
        print_agents_brief(sorted(agents, key=lambda x: sort_id(x["id"])))
    else:
        for a in sorted(agents, key=lambda x: sort_id(x["id"])):
            if fields == "id":
                typer.echo(a["id"])
            else:
                typer.echo(f"id: {a['id']}")
                print_agent(a, indent_level=1, attributes=fields)


@agents_app.command("get")
def get_agent(
    ctx: typer.Context,
    agent_ids: List[str],
    brief: bool = typer.Option(False, "-b", "--brief", help="Print only id, name, alias and type"),
    fields: Optional[str] = typer.Option(None, "-f", "--fields", help="Config attributes to print"),
) -> None:
    """
    Print agent configuration
    """
    api = get_api(ctx)
    agents = [_get_agent_by_id(api.syn, i) for i in agent_ids]
    if brief:
        print_agents_brief(agents)
    else:
        for a in agents:
            typer.echo(f"id: {a['id']}")
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
    agents = api_request(api.syn.list_agents, "AgentsList")
    matching = [a for a in agents if matcher.match(agent_to_dict(a))]
    if not matching:
        typer.echo("No agent matches specified rules")
    else:
        matching.sort(key=lambda x: sort_id(x["id"]))
        if brief:
            print_agents_brief(matching)
        else:
            for a in matching:
                if fields == "id":
                    typer.echo(a["id"])
                else:
                    typer.echo(f"id: {a['id']}")
                    print_agent(a, indent_level=1, attributes=fields)


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
        a = api_request(api.syn.update_agent, "AgentUpdate", i, a)
        if a["status"] != "AGENT_STATUS_OK":
            typer.echo(f"id: {i} FAILED to activate (status: {a['status']}")
        else:
            typer.echo(f"id: {i} agent activated")


@agents_app.command("activate-details")
def activate_agent_details(
        ctx: typer.Context,
        agent_alias: str,
        site_id: str,
        private_ips: List[str],
) -> None:
    """
    Activate pending agent
    """
    api = get_api(ctx)
    agents = _get_agents_by_alias(api.syn, agent_alias)
    if not len(agents):
        fail(f"Agent alias {agent_alias} not found")
    elif len(agents) > 1:
        fail(f"Agent alias {agent_alias} matches multiple agents: {agents}")
    agent = agents[0]
    if agent["status"] != "AGENT_STATUS_WAIT":
        typer.echo(f"agent not pending (status: {agent['status']}), continuing anyway")
    agent["status"] = "AGENT_STATUS_OK"
    agent["siteId"] = site_id
    md = agent["metadata"]
    md["privateIpv4Addresses"] = []
    md["privateIpv6Addresses"] = []
    for ip in private_ips:
        if ":" in ip:
            md["privateIpv6Addresses"].append({"value": ip})
        else:
            md["privateIpv4Addresses"].append({"value": ip})
    md.pop("publicIpv4Addresses", None)
    md.pop("publicIpv6Addresses", None)
    typer.echo(json.dumps({"agent":agent}))
    a = api_request(api.syn.update_agent, "AgentUpdate", agent["id"], agent)
    if a["status"] != "AGENT_STATUS_OK":
        fail(f"FAILED to activate agent (status: {agent['status']}")
    typer.echo(f"agent activated!")


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
        a = api_request(api.syn.update_agent, "AgentUpdate", i, a)
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
        try:
            api.syn.delete_agent(i)
            typer.echo(f"Deleted agent: id: {i}")
        except KentikAPIRequestError as exc:
            if exc.response.status_code == 404:
                fail(f"Agent with id '{i}' not found")
            else:
                fail(f"API request AgentDelete failed - {exc}")
