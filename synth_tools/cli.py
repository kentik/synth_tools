import logging
from typing import Optional

import typer

from synth_tools.apis import APIs
from synth_tools.commands import log, commands_registry
from synth_tools.commands.utils import fail

app = typer.Typer()

for name, command in commands_registry.items():
    app.add_typer(command, name=name)


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
