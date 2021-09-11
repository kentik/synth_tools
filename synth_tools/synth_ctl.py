#!/usr/bin/python3
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional
from time import sleep

import typer

from synth_tools import (
    AgentTest,
    DNSGridTest,
    DNSTest,
    HostnameTest,
    IPFamily,
    IPTest,
    KentikAPIRequestError,
    KentikSynthClient,
    MeshTest,
    NetworkGridTest,
    PageLoadTest,
    Protocol,
    SynTest,
    TestStatus,
    TestType,
    UrlTest,
)

# noinspection Mypy
from kentik_api import KentikAPI

# noinspection Mypy
from kentik_api.utils import get_credentials

logging.basicConfig(level=logging.INFO)
log = logging.getLogger()


def one_shot(
    client: KentikSynthClient, test: SynTest, wait_factor: int = 3, retries: int = 3, output: Optional[Path] = None
) -> bool:
    def delete_test(tst: SynTest):
        log.debug("Deleting test '%s' (id: %s)", tst.name, tst.id)
        try:
            client.delete_test(tst.id)
        except KentikAPIRequestError as ex:
            log.error("Failed to delete test '%s' (id: %s) (%s)", tst.name, tst.id, ex)

    create_test = not test.deployed
    if create_test:
        log.debug("creating test '%s'", test.name)
        try:
            t = client.create_test(test)
        except KentikAPIRequestError as ex:
            log.error("Failed to create test '%s' (%s)", test.name, ex)
            return False
        log.info("Created test '%s' (id: %s)", t.name, t.id)
    else:
        t = test
    if t.status != TestStatus.active:
        log.info("Activating test '%s'", t.name)
        try:
            client.set_test_status(t.id, TestStatus.active)
        except KentikAPIRequestError as ex:
            log.error("Failed to activate test '%s' (id: %s) (%s)", t.name, t.id, ex)
            if create_test:
                delete_test(t)
            return False

    wait_time = max(0, t.max_period * wait_factor - int((datetime.now(tz=timezone.utc) - t.edate).total_seconds()))
    start = datetime.now(tz=timezone.utc)
    while retries:
        if wait_time > 0:
            log.info("Waiting for %s seconds for '%s' test to accumulate results", wait_time, t.name)
            sleep(wait_time)
        wait_time = t.max_period
        now = datetime.now(tz=timezone.utc)
        try:
            health = client.health([t.id], start=now - timedelta(seconds=t.max_period * wait_factor), end=now)
        except KentikAPIRequestError as ex:
            log.error("Failed to retrieve '%s' test health (%s). Retrying ...", t.name, ex)
            retries -= 1
            continue
        if len(health) < 1:
            log.debug("Health not available after %s seconds", (now - start).total_seconds())
            retries -= 1
            continue
        health_ts = datetime.fromisoformat(health[0]["overallHealth"]["time"].replace("Z", "+00:00"))
        if (health_ts - now).total_seconds() > t.max_period * wait_factor:
            log.info(
                "Stale health data after %s second (timestamp: %s)",
                (now - start).total_seconds(),
                health_ts.isoformat(),
            )
            retries -= 1
            continue
        log.debug("Test '%s' is %s at %s", t.name, health[0]["overallHealth"]["health"], health_ts.isoformat())
        if output:
            log.debug("Writing health data to '%s'", output.name)
            with output.open("w") as f:
                json.dump(health, f, indent=2)
        ret = True
        break
    else:
        log.fatal("Failed to get valid health data for '%s'", t.name)
        ret = False

    if create_test:
        delete_test(t)

    return ret


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
