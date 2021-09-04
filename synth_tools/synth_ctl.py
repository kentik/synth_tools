#!/usr/bin/python3
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

import typer

# noinspection Mypy
from kentik_api import KentikAPI

# noinspection Mypy
from kentik_api.utils import get_credentials

logging.basicConfig(level=logging.INFO)
log = logging.getLogger()


def main(
    profile: str = typer.Argument("default", help="Credential profile"),
    debug: bool = typer.Option(False, "-d", "--debug", help="Debug output"),
    proxy: Optional[str] = typer.Option(None, "--proxy", help="Proxy to use to connect to Kentik API"),
) -> None:
    if debug:
        log.setLevel(logging.DEBUG)
        log.debug("Debug output enabled")
    if proxy:
        log.debug("Using proxy: %s", proxy)
    log.debug("using credential profile: %s", profile)

    api = KentikAPI(*get_credentials(profile), proxy=proxy)
    log.debug("api: %s", api)

    print("Nothing implemented yet. Please, come back later.")


if __name__ == "__main__":
    typer.run(main)
