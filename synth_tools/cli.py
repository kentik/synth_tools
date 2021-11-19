import logging
from typing import Optional

import typer

from synth_tools import log
from synth_tools.apis import APIs
from synth_tools.commands import commands_registry
from synth_tools.utils import fail

app = typer.Typer(add_completion=False)

for name, command in commands_registry.items():
    app.add_typer(command, name=name)


def version_callback(value: bool) -> None:
    if value:
        from pkg_resources import get_distribution

        typer.echo(get_distribution("kentik-synth-tools"))
        raise typer.Exit()


# noinspection PyUnusedLocal
@app.callback(no_args_is_help=True)
def main(
    ctx: typer.Context,
    profile: str = typer.Option(
        "default",
        "-p",
        "--profile",
        help="Credential profile for the monitoring account",
    ),
    target_profile: Optional[str] = typer.Option(
        None,
        "-t",
        "--target-profile",
        help="Credential profile for the target account (default: same as profile)",
    ),
    debug: bool = typer.Option(False, "-d", "--debug", help="Debug output"),
    proxy: Optional[str] = typer.Option(None, "--proxy", help="Proxy to use to connect to Kentik API"),
    api_url: Optional[str] = typer.Option(None, "--api-url", help="Base URL for Kentik API (default:  api.kentik.com)"),
    version: Optional[bool] = typer.Option(
        None, "--version", callback=version_callback, is_eager=True, help="Show version and exit"
    ),
) -> None:
    """
    Tool for manipulating Kentik synthetic tests
    """
    if debug:
        log.setLevel(logging.DEBUG)
        log.debug("Debug output enabled")
    if target_profile is None:
        target_profile = profile

    ctx.obj = APIs(
        mgmt_profile=target_profile,
        syn_profile=profile,
        api_url=api_url,
        proxy=proxy,
        fail=fail,
    )


def run():
    app()


if __name__ == "__main__":
    app()
