#!/usr/bin/python3
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

import typer

from kentik_synth_client import SynTest, TestStatus
from synth_tools.apis import APIs
from synth_tools.core import load_test, run_one_shot
from synth_tools.matchers import AllMatcher

app = typer.Typer()
tests_app = typer.Typer()
app.add_typer(tests_app, name="test")
agents_app = typer.Typer()
app.add_typer(agents_app, name="agent")

api: APIs

logging.basicConfig(level=logging.INFO)
log = logging.getLogger()















@app.callback(no_args_is_help=True)
def main(
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
    global api

    if debug:
        log.setLevel(logging.DEBUG)
        log.debug("Debug output enabled")
    if target_profile is None:
        target_profile = profile

    api = APIs(
        mgmt_profile=target_profile,
        syn_profile=profile,
        api_url=api_url,
        proxy=proxy,
        fail=fail,
    )


if __name__ == "__main__":
    app()
